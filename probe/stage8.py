"""Stage 8b/8c (board 11-15 12:09): BabyAI-PickupDist-v0 with four choices — train, step eval, closed loop.

Usage (WSL, repo root, after `python -m probe.stage8a` wrote data/pickupdist_train.jsonl):
  python -m probe.stage8 train --seed 0                     # -> ~/babyai-laya-ft/pickupdist-s0
  python -m probe.stage8 stepeval --model ~/babyai-laya-ft/pickupdist-s0 --name s0
  python -m probe.stage8 loop --policy none|reset --model ~/babyai-laya-ft/pickupdist-s0 --name laya-s0 [--base ...]
  python -m probe.stage8 loop --policy bot|random --name bot

Fixed (board): Laya english 55cf4c4 by path, loss rlcd, shuffle_options ('choice',), default epochs, seeds 0/1/2.
Training rows: bot demos of seeds 0-999 minus every episode in which the bot used an action outside the four.
Question: probe/laya_rows.py question_pickup(). State text: GoToLocal obs_to_text unchanged (no carrying line).
Closed loop: dev seeds 10000-10299, all 300, env step limit 49, deterministic (highest score, ties -> fixed order).
R-reset as stage 5 with four actions: key = obs text (mission line left out); all four tried -> clear that key, rank 1.
A wrong pickup does not end the episode (env unchanged); it is counted as its own failure kind 'wrong_pickup'.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import random
import statistics
import time

import gymnasium as gym
import minigrid  # noqa: F401
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.closed_loop import find_loop
from probe.dump_demos import guarded_seeds
from probe.laya_rows import CHOICES_PICKUP, QID, question_pickup, state_text
from probe.obs_text import obs_to_text
from probe.stage8a import ENV, NAME_TO_ACT4, bot_episode, categorize, matches, mission_kind, visible

CH = CHOICES_PICKUP
OUT = pathlib.Path("reports/stage8")
DEV = "10000-10299"
TRAIN_DUMP = "data/pickupdist_train.jsonl"
ROWS = "data/laya_rows_pickupdist_train_8b.jsonl"


def ranked(p: dict) -> list[str]:
    return sorted(CH, key=lambda c: -p.get(c, 0.0))  # stable: ties keep the fixed option order


class Scorer:
    def __init__(self, path: str):
        import laya
        self.agent = laya.load(path, device="cuda")

    def __call__(self, states, choices=CH):
        if not states:
            return []
        res = self.agent.predict_batch(states, question_pickup(choices), batch_size=128)
        return [r["answers"][QID].get("probabilities") or {} for r in res]


# ---------------------------------------------------------------- 8b

def train(seed: int) -> None:
    import torch
    from laya.train import TrainConfig, finetune

    from probe.laya_model import BASE_REV, FT_ROOT, base_dir
    rows = [json.loads(l) for l in open(TRAIN_DUMP, encoding="utf-8")]
    bad = sorted({r["seed"] for r in rows if r["action_name"] not in CH})
    keep = [r for r in rows if r["seed"] not in set(bad)]
    with open(ROWS, "w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps({"state": state_text(r["text"], r["mission"]), "questions": question_pickup(),
                                "expected": {QID: r["action_name"]}}) + "\n")
    name = f"pickupdist-s{seed}"
    out = os.path.join(FT_ROOT, name)
    cfg = TrainConfig(shuffle_options=("choice",), seed=seed)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    rep = finetune(ROWS, base_dir(), out, cfg)
    summary = {"name": name, "checkpoint": f"babyai-laya-ft/{name}", "base": f"convaiinnovations/laya@{BASE_REV}",
               "dropped_episodes": bad, "episodes": len({r['seed'] for r in keep}), "rows": len(keep),
               "action_rows": dict(collections.Counter(r["action_name"] for r in keep)),
               "config": {k: str(v) for k, v in cfg.__dict__.items()}, "train_minutes": round((time.time() - t0) / 60, 2),
               "gpu_peak_alloc_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               "gpu_peak_reserved_gb": round(torch.cuda.max_memory_reserved() / 2**30, 2),
               "gpu": torch.cuda.get_device_name(0),
               **{k: rep.get(k) for k in ("train_items", "calibration_items", "temperature", "epoch_loss", "calibration")}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"train-s{seed}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("rows", "train_minutes", "gpu_peak_alloc_gb", "epoch_loss")}, default=str))


def stepeval(model: str, name: str) -> None:
    rows = [x for s in guarded_seeds(DEV) for x in bot_episode(s)[0] if x["action_name"] in CH]
    sc = Scorer(model)
    states = [state_text(r["text"], r["mission"]) for r in rows]
    fwd, rev = sc(states), sc(states, list(reversed(CH)))
    for r, p, q in zip(rows, fwd, rev):
        r["m"] = ranked(p)[0]
        r["r"] = max(reversed(CH), key=lambda c: q.get(c, 0.0))
        r["cat"] = categorize(r)
        r["kind"] = mission_kind(r["target"])

    def acc(sub):
        return {"n": len(sub), "agree": round(sum(r["m"] == r["action_name"] for r in sub) / max(len(sub), 1), 4)}

    res = {"model": f"babyai-laya-ft/{os.path.basename(model.rstrip('/'))}", "steps": len(rows), "all": acc(rows),
           "pickup_is_correct": acc([r for r in rows if r["cat"]["pickup_step"]]),
           "target_unseen": acc([r for r in rows if r["cat"]["target_unseen"]]),
           "distractor_closer": acc([r for r in rows if r["cat"]["distractor_closer"]]),
           "two_matching": acc([r for r in rows if r["cat"]["two_matching"]]),
           "mission_kind": {k: acc([r for r in rows if r["kind"] == k]) for k in ("color only", "type only", "both")},
           "order_flip_rate": round(sum(r["m"] != r["r"] for r in rows) / len(rows), 4),
           "reversed_order_agree": round(sum(r["r"] == r["action_name"] for r in rows) / len(rows), 4),
           "confusion_bot_to_model": {b: dict(collections.Counter(r["m"] for r in rows if r["action_name"] == b)) for b in CH},
           "model_choice_share": dict(collections.Counter(r["m"] for r in rows))}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"stepeval-{name}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res))


# ---------------------------------------------------------------- 8c

class Ep:
    def __init__(self, seed: int, bot_n: int):
        self.seed, self.bot_n = seed, bot_n
        self.env = gym.make(ENV)
        self.obs, _ = self.env.reset(seed=seed)
        u = self.u = self.env.unwrapped
        d = u.instrs.desc
        self.target = {"type": d.type, "color": d.color}
        self.kind = mission_kind(self.target)
        n_obj = sum(matches(o.type, o.color, self.target) for o in u.grid.grid
                    if o is not None and o.type not in ("wall", "door"))
        self.grey_wall = len(d.obj_poss) != n_obj  # env counts grey walls for "grey object"
        self.visible0 = any(matches(v[1], v[2], self.target) for v in visible(self.obs["image"]))
        self.done, self.end, self.steps, self.tried, self.n_interv = False, None, [], {}, 0
        self.wrong_step = None
        self.rng = random.Random(seed)
        self.bot = BabyAIBot(u)

    def text(self):
        return obs_to_text(self.obs["image"], self.obs["direction"])

    def pick_kind(self):
        if self.u.carrying is not None:
            return "while carrying"
        fc = self.u.grid.get(*self.u.front_pos)
        if fc is None or fc.type in ("wall", "door"):
            return "nothing ahead"
        return "matching" if matches(fc.type, fc.color, self.target) else "wrong object"

    def step(self, act: int, choice: str, top: str, interv: bool, probs: dict):
        pk = self.pick_kind() if choice == "pick up" else None
        self.steps.append({"text": self.text(), "policy": choice, "top": top, "intervened": interv, "pick": pk,
                           "p": {k: round(v, 3) for k, v in probs.items()}})
        self.obs, reward, term, trunc, _ = self.env.step(act)
        if pk == "wrong object" and self.wrong_step is None:
            self.wrong_step = len(self.steps) - 1
        if term or trunc:
            self.done = True
            self.end = "success" if term and reward > 0 else "wrong_pickup" if self.wrong_step is not None else "timeout"
            self.env.close()


def run_loop(policy: str, scorer=None):
    seeds = list(guarded_seeds(DEV))
    bot_n = {s: len(bot_episode(s)[0]) for s in seeds}
    eps = [Ep(s, bot_n[s]) for s in seeds]
    while True:
        live = [e for e in eps if not e.done]
        if not live:
            break
        if policy == "bot":
            for e in live:
                a = int(e.bot.replan())
                e.step(a, {v: k for k, v in NAME_TO_ACT4.items()}.get(a, f"other:{a}"), "", False, {})
            continue
        if policy == "random":
            for e in live:
                c = e.rng.choice(CH)
                e.step(NAME_TO_ACT4[c], c, "", False, {})
            continue
        probs = scorer([state_text(e.text(), e.obs["mission"]) for e in live])
        for e, p in zip(live, probs):
            order = ranked(p)
            c, interv = order[0], False
            if policy == "reset":
                tr = e.tried.setdefault(e.text(), set())
                left = [o for o in order if o not in tr]
                if not left:
                    tr.clear()
                    left = order
                c = left[0]
                tr.add(c)
                interv = c != order[0]
                e.n_interv += interv
            e.step(NAME_TO_ACT4[c], c, order[0], interv, p)
    return eps


def first_bot_choice(seed: int, actions) -> str:
    """Fresh bot asked at the state reached by `actions` (stage-4 style)."""
    env = gym.make(ENV)
    env.reset(seed=seed)
    for a in actions:
        env.step(a)
    try:
        a = int(BabyAIBot(env.unwrapped).replan())
        return {v: k for k, v in NAME_TO_ACT4.items()}.get(a, f"other:{a}")
    except Exception as x:  # noqa: BLE001
        return f"bot_error:{type(x).__name__}"
    finally:
        env.close()


def failures(eps, n=5):
    out = []
    fails = [e for e in eps if e.end != "success"]
    picks = [e for e in fails if e.end == "wrong_pickup"][:3]
    rest = [e for e in fails if e.end != "wrong_pickup"][: n - len(picks)]
    for e in sorted(picks + rest, key=lambda e: e.seed):
        if e.end == "wrong_pickup":
            k, why = e.wrong_step, "wrong pickup"
        else:
            lp = find_loop([(s["text"], s["policy"]) for s in e.steps])
            k, why = (lp[0], f"repeat, period {lp[1]}") if lp else (max(len(e.steps) - 10, 0), "no repeat, last 10")
        s = e.steps[k]
        out.append({"seed": e.seed, "end": e.end, "step": k, "why": why, "mission": e.obs["mission"],
                    "text": s["text"], "model": s["policy"], "scores": s["p"],
                    "bot": first_bot_choice(e.seed, [NAME_TO_ACT4[x["policy"]] for x in e.steps[:k]])})
    return out


def summarize(eps, name, policy, base=None):
    ok = [e for e in eps if e.end == "success"]

    def rate(sub):
        s = [e for e in sub if e.end == "success"]
        return {"n": len(sub), "success": len(s), "within_2x_bot": sum(len(e.steps) <= 2 * e.bot_n for e in s)}

    picks = collections.Counter(st["pick"] for e in eps for st in e.steps if st["pick"])
    res = {"name": name, "policy": policy, "episodes": len(eps), "all": rate(eps),
           "timeout": sum(e.end == "timeout" for e in eps), "wrong_pickup": sum(e.end == "wrong_pickup" for e in eps),
           "target_visible_at_start": rate([e for e in eps if e.visible0]),
           "target_unseen_at_start": rate([e for e in eps if not e.visible0]),
           "mission_kind": {k: rate([e for e in eps if e.kind == k]) for k in ("color only", "type only", "both")},
           "grey_wall_episodes": rate([e for e in eps if e.grey_wall]),
           "mean_steps_success": round(statistics.mean(len(e.steps) for e in ok), 2) if ok else None,
           "bot_mean_steps_same_eps": round(statistics.mean(e.bot_n for e in ok), 2) if ok else None,
           "steps_sum_all": sum(len(e.steps) for e in eps),
           "steps_sum_without_wrong_pickup": sum(len(e.steps) for e in eps if e.end != "wrong_pickup"),
           "pickup_choices": dict(picks),
           "per_episode": {e.seed: {"end": e.end, "steps": len(e.steps), "bot": e.bot_n, "interventions": e.n_interv,
                                    "wrong_step": e.wrong_step} for e in eps}}
    if policy == "reset":
        res["episodes_with_intervention"] = sum(e.n_interv > 0 for e in eps)
        res["interventions"] = sum(e.n_interv for e in eps)
        res["pickup_choices_by_rule"] = dict(collections.Counter(st["pick"] for e in eps for st in e.steps
                                                                 if st["pick"] and st["intervened"]))
    if base is not None:
        b = {int(k): v["end"] == "success" for k, v in base["per_episode"].items()}
        broken = [e for e in eps if e.end != "success" and b[e.seed]]
        res["vs_no_rule"] = {
            "saved": sorted(e.seed for e in eps if e.end == "success" and not b[e.seed]),
            "broken": sorted(e.seed for e in broken),
            "broken_by_rule_chosen_wrong_pickup": sorted(
                e.seed for e in broken if e.wrong_step is not None and e.steps[e.wrong_step]["intervened"])}
    if policy in ("none", "reset"):
        res["representative_failures"] = failures(eps)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["train", "stepeval", "loop"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--model", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--policy", default="none", choices=["none", "reset", "bot", "random"])
    ap.add_argument("--base", default=None)
    a = ap.parse_args()
    model = a.model and os.path.expanduser(a.model)
    if a.mode == "train":
        return train(a.seed)
    if a.mode == "stepeval":
        return stepeval(model, a.name)
    OUT.mkdir(parents=True, exist_ok=True)
    eps = run_loop(a.policy, Scorer(model) if a.policy in ("none", "reset") else None)
    base = json.load(open(a.base, encoding="utf-8")) if a.base else None
    res = summarize(eps, a.name, a.policy, base)
    if model:
        res["model"] = f"babyai-laya-ft/{os.path.basename(model.rstrip('/'))}"
    (OUT / f"{a.name}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("name", "all", "timeout", "wrong_pickup", "pickup_choices")}
                     | ({"vs": res["vs_no_rule"]} if base else {}), default=str))


if __name__ == "__main__":
    main()
