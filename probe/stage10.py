"""Stage 10 (board c7d1bc74, 11-16, MoKa): BabyAI-PutNextLocal-v0 — pick the first object up, put it down next to the
second. Five choices (stage-8 four + drop) and one extra state line "carrying: ...". Env code unchanged.

Usage (WSL, repo root, PY=~/babyai-laya-venv/bin/python, HF_HUB_OFFLINE=1):
  $PY -m probe.stage10 stats                                          # 10a: bot on train + dev, text check, samples
  $PY -m probe.stage10 loop --scorer bot|random --name bot
  $PY -m probe.stage10 loop --scorer fixed [--policy reset --base reports/stage10/fixed.json] --name fixed
  $PY -m probe.stage10 dump                                           # 10b: bot demos of train seeds 0-999
  $PY -m probe.stage10 train --seed 0 [--no-carry]                    # -> ~/babyai-laya-ft/putnext[-nocarry]-s0
  $PY -m probe.stage10 stepeval --model ~/babyai-laya-ft/putnext-s0 --name s0 [--no-carry]
  $PY -m probe.stage10 loop --scorer laya --model ~/babyai-laya-ft/putnext-s0 --name laya-s0 [--policy reset --base ...]

Fixed by the board (11-16):
  choices turn left / turn right / forward / pick up / drop (this order; ties -> this order), step limit 128 (env).
  state = "mission: ..." + "carrying: <color> <type>|nothing" + GoToLocal obs text; the carried object is read from the
  observation itself (image[3][6], the agent's own cell), never from the env.
  10d (--no-carry): the same, without the carrying line (one seed).
  R-reset as stages 5/8: key = the state text given to the model without the mission line; all five tried -> clear
  that key only, take rank 1.  Model-free control: forward 0.30 > left 0.25 > right 0.20 > pick up 0.15 > drop 0.10.
  seeds: train 0-999, dev 10000-10299; final 70000-70299 refused (20000/30000/60000 ranges stay locked).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import random
import re
import statistics
import time

import gymnasium as gym
import minigrid  # noqa: F401
import numpy as np
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.dump_demos import guarded_seeds
from probe.laya_rows import CHOICES_PUTNEXT, QID, question_putnext, state_text
from probe.obs_text import AX, AY, IDX_TO_COLOR, IDX_TO_OBJECT, obs_to_text

ENV = "BabyAI-PutNextLocal-v0"
ACT = {0: "turn left", 1: "turn right", 2: "forward", 3: "pick up", 4: "drop"}
NAME_TO_ACT = {v: k for k, v in ACT.items()}
CH = CHOICES_PUTNEXT
assert CH == list(ACT.values())
FIXED = {"forward": 0.30, "turn left": 0.25, "turn right": 0.20, "pick up": 0.15, "drop": 0.10}
OUT = pathlib.Path("reports/stage10")
DEV = "10000-10299"
LOCKED = [range(60000, 60300), range(70000, 70300)]
TRAIN_DUMP = "data/putnext_train.jsonl"
PHASES = ("before pickup", "pickup", "carrying", "drop")


def seeds_of(s: str):
    r = guarded_seeds(s)
    if any(x in rg for rg in LOCKED for x in r):
        raise SystemExit("60000-60299 (stage 9, kept closed) and 70000-70299 (used once for 10e on 11-16) are locked")
    return r


# ---------------------------------------------------------------- text

def carried(image) -> str | None:
    o = np.asarray(image)[AX, AY]
    t = IDX_TO_OBJECT[int(o[0])]
    return f"{IDX_TO_COLOR[int(o[1])]} {t}" if t in ("ball", "key", "box") else None


def obs_text(image, direction, carry: bool = True) -> str:
    t = obs_to_text(image, direction)
    return f"carrying: {carried(image) or 'nothing'}\n{t}" if carry else t


def descs(u):
    i = u.instrs
    return ({"type": i.desc_move.type, "color": i.desc_move.color},
            {"type": i.desc_fixed.type, "color": i.desc_fixed.color})


def is_move(o, move) -> bool:
    return o is not None and o.type == move["type"] and o.color == move["color"]


def phase(carrying: bool, act: int) -> str:
    if act == 3:
        return "pickup"
    if act == 4:
        return "drop"
    return "carrying" if carrying else "before pickup"


# ---------------------------------------------------------------- bot

def bot_episode(seed: int):
    env = gym.make(ENV)
    obs, _ = env.reset(seed=seed)
    u = env.unwrapped
    move, fixed = descs(u)
    bot = BabyAIBot(u)
    rows, term, trunc, reward = [], False, False, 0.0
    while not (term or trunc):
        a = int(bot.replan())
        carrying = u.carrying is not None
        rows.append({"seed": seed, "step": len(rows), "mission": obs["mission"], "move": move, "fixed": fixed,
                     "image": obs["image"].tolist(), "direction": int(obs["direction"]),
                     "carrying_env": f"{u.carrying.color} {u.carrying.type}" if carrying else None,
                     "action": a, "action_name": ACT.get(a, f"other:{a}"), "phase": phase(carrying, a),
                     "text": obs_text(obs["image"], obs["direction"]),
                     "text_nocarry": obs_text(obs["image"], obs["direction"], carry=False)})
        obs, reward, term, trunc, _ = env.step(a)
    env.close()
    return rows, bool(term and reward > 0), u.max_steps


def bot_stats(seeds):
    eps = {s: bot_episode(s) for s in seeds}
    lens = [len(r) for r, _, _ in eps.values()]
    acts = collections.Counter(x["action_name"] for r, _, _ in eps.values() for x in r)
    picks = collections.Counter(sum(x["action"] == 3 for x in r) for r, _, _ in eps.values())
    first_pick = [next(i for i, x in enumerate(r) if x["action"] == 3) for r, _, _ in eps.values()
                  if any(x["action"] == 3 for x in r)]
    q = sorted(lens)
    return eps, {"episodes": len(eps), "success": sum(ok for _, ok, _ in eps.values()),
                 "max_steps_env": sorted({m for _, _, m in eps.values()}), "actions": dict(acts),
                 "episodes_with_other_actions": sorted(s for s, (r, _, _) in eps.items()
                                                       if any(x["action"] not in ACT for x in r)),
                 "steps_mean": round(statistics.mean(lens), 2), "steps_median": statistics.median(lens),
                 "steps_p90": q[int(0.9 * (len(q) - 1))], "steps_max": max(lens),
                 "first_pickup_step_mean": round(statistics.mean(first_pick), 2),
                 "pickups_per_episode": dict(sorted(picks.items())),
                 "multi_pickup_seeds": sorted(s for s, (r, _, _) in eps.items() if sum(x["action"] == 3 for x in r) > 1)}


# ---------------------------------------------------------------- closed loop

class Ep:
    def __init__(self, seed: int, bot_n: int, carry: bool = True):
        self.seed, self.bot_n, self.carry = seed, bot_n, carry
        self.env = gym.make(ENV)
        self.obs, _ = self.env.reset(seed=seed)
        self.u = self.env.unwrapped
        self.move, self.fixed = descs(self.u)
        self.done, self.end, self.steps, self.tried, self.n_interv = False, None, [], {}, 0
        self.rng = random.Random(seed)
        self.bot = BabyAIBot(self.u)
        self.picked_move = self.picked_any = False
        self.wrong_picks = self.repicks = self.drops = 0
        self.null = collections.Counter()

    def text(self):
        return obs_text(self.obs["image"], self.obs["direction"], self.carry)

    def step(self, act: int, choice: str, top: str, interv: bool, probs: dict):
        u = self.u
        front = u.grid.get(*u.front_pos)
        carrying = u.carrying is not None
        pos = tuple(int(x) for x in u.agent_pos)
        kind = None
        if act == 3:
            if carrying or front is None or not front.can_pickup():
                kind = "null pickup"
            else:
                kind = "pickup move" if is_move(front, self.move) else "pickup wrong"
        elif act == 4:
            kind = "drop" if carrying and front is None else "null drop"
        self.steps.append({"policy": choice, "top": top, "intervened": interv, "kind": kind,
                           "phase": phase(carrying, act), "p": {k: round(v, 3) for k, v in probs.items()}})
        self.obs, reward, term, trunc, _ = self.env.step(act)
        self.steps[-1]["moved"] = tuple(int(x) for x in u.agent_pos) != pos
        if kind in ("pickup move", "pickup wrong"):
            if self.drops:
                self.repicks += 1
            self.picked_any = True
            if kind == "pickup move":
                self.picked_move = True
            else:
                self.wrong_picks += 1
        elif kind == "drop":
            self.drops += 1
        elif kind:
            self.null[kind] += 1
        if term or trunc:
            self.done = True
            self.end = "success" if term and reward > 0 else "timeout"
            self.env.close()

    def reached(self) -> str:
        if self.end == "success":
            return "4 success"
        if self.picked_move:
            return "3 picked the right object, never put it right"
        return "2 picked only wrong objects" if self.picked_any else "1 never picked anything up"


def ranked(p: dict) -> list[str]:
    return sorted(CH, key=lambda c: -p.get(c, 0.0))  # stable: ties keep the fixed option order


class FixedScorer:
    def __call__(self, states):
        return [dict(FIXED) for _ in states]


class Scorer:
    def __init__(self, path: str):
        import laya
        self.agent = laya.load(path, device="cuda")

    def __call__(self, states, choices=CH):
        if not states:
            return []
        res = self.agent.predict_batch(states, question_putnext(choices), batch_size=128)
        return [r["answers"][QID].get("probabilities") or {} for r in res]


def run_loop(policy: str, scorer=None, seeds=None, carry: bool = True):
    seeds = list(seeds)
    bot_n = {s: len(bot_episode(s)[0]) for s in seeds}
    eps = [Ep(s, bot_n[s], carry) for s in seeds]
    while True:
        live = [e for e in eps if not e.done]
        if not live:
            break
        if policy == "bot":
            for e in live:
                a = int(e.bot.replan())
                e.step(a, ACT.get(a, f"other:{a}"), "", False, {})
            continue
        if policy == "random":
            for e in live:
                c = e.rng.choice(CH)
                e.step(NAME_TO_ACT[c], c, "", False, {})
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
            e.step(NAME_TO_ACT[c], c, order[0], interv, p)
    return eps


def summarize(eps, name, policy, base=None):
    ok = [e for e in eps if e.end == "success"]
    steps = [s for e in eps for s in e.steps]
    blocked = sum(s["policy"] == "forward" and not s["moved"] for s in steps)
    res = {"name": name, "policy": policy, "episodes": len(eps),
           "all": {"n": len(eps), "success": len(ok), "within_2x_bot": sum(len(e.steps) <= 2 * e.bot_n for e in ok)},
           "timeout": sum(e.end == "timeout" for e in eps),
           "reached": dict(sorted(collections.Counter(e.reached() for e in eps).items())),
           "wrong_pickups": sum(e.wrong_picks for e in eps),
           "episodes_with_wrong_pickup": sum(e.wrong_picks > 0 for e in eps),
           "repickups_after_a_drop": sum(e.repicks for e in eps),
           "null_actions": dict(sum((e.null for e in eps), collections.Counter())),
           "blocked_forward_steps": blocked, "steps_total": len(steps),
           "blocked_forward_rate": round(blocked / max(len(steps), 1), 4),
           "mean_steps_success": round(statistics.mean(len(e.steps) for e in ok), 2) if ok else None,
           "bot_mean_steps_same_eps": round(statistics.mean(e.bot_n for e in ok), 2) if ok else None,
           "actions": dict(collections.Counter(s["policy"] for s in steps)),
           "per_episode": {e.seed: {"end": e.end, "steps": len(e.steps), "bot": e.bot_n, "reached": e.reached(),
                                    "wrong_picks": e.wrong_picks, "interventions": e.n_interv} for e in eps}}
    if policy == "reset":
        res["episodes_with_intervention"] = sum(e.n_interv > 0 for e in eps)
        res["interventions"] = sum(e.n_interv for e in eps)
        res["rule_chosen_kinds"] = dict(collections.Counter(s["kind"] or s["policy"] for s in steps if s["intervened"]))
    if base is not None:
        b = {int(k): v["end"] == "success" for k, v in base["per_episode"].items()}
        saved = [e for e in eps if e.end == "success" and not b[e.seed]]
        broken = [e for e in eps if e.end != "success" and b[e.seed]]
        res["vs_no_rule"] = {
            "saved": sorted(e.seed for e in saved),
            "saved_within_2x_bot": sum(len(e.steps) <= 2 * e.bot_n for e in saved),
            "broken": sorted(e.seed for e in broken),
            "broken_with_rule_chosen_pickup_or_drop": sorted(
                e.seed for e in broken if any(s["intervened"] and s["policy"] in ("pick up", "drop") for s in e.steps))}
    return res


def loop(a) -> None:
    seeds = seeds_of(a.seeds)
    model = a.model and os.path.expanduser(a.model)
    if a.scorer in ("bot", "random"):
        eps = run_loop(a.scorer, None, seeds)
        policy = a.scorer
    else:
        sc = FixedScorer() if a.scorer == "fixed" else Scorer(model)
        eps = run_loop(a.policy, sc, seeds, carry=not a.no_carry)
        policy = a.policy
    base = json.load(open(a.base, encoding="utf-8")) if a.base else None
    res = summarize(eps, a.name, policy, base)
    res["env"], res["seeds"], res["carry_line"] = ENV, a.seeds, not a.no_carry
    res["model"] = (f"babyai-laya-ft/{os.path.basename(model.rstrip('/'))}" if model else
                    "none (fixed scores)" if a.scorer == "fixed" else None)
    # 10e (70000-70299, reports/stage10/final/) ran once with a --use-final-seeds flag that was removed afterwards
    out = OUT
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.name}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res.get(k) for k in ("name", "all", "timeout", "reached", "wrong_pickups", "null_actions",
                                              "blocked_forward_rate")}
                     | ({"vs": {k: (len(v) if isinstance(v, list) else v) for k, v in res["vs_no_rule"].items()}}
                        if base else {}), default=str))


# ---------------------------------------------------------------- 10a stats

def stats() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"env": ENV, "minigrid": minigrid.__version__, "choices": CH, "fixed_control": FIXED}
    train, res["bot_train_0_999"] = bot_stats(seeds_of("0-999"))
    dev, res["bot_dev_10000_10299"] = bot_stats(seeds_of(DEV))
    rows = [x for r, _, _ in list(train.values()) + list(dev.values()) for x in r]
    pat = re.compile(r"^put the (\w+) (ball|key|box) next to the (\w+) (ball|key|box)$")
    res["missions"] = {"steps": len(rows), "match_one_form": sum(bool(pat.match(r["mission"])) for r in rows),
                       "examples": sorted({r["mission"] for r in rows})[:6]}
    envs = gym.make(ENV)
    envs.reset(seed=10000)
    res["objects_in_room"] = sum(1 for o in envs.unwrapped.grid.grid if o is not None and o.type not in ("wall", "door"))
    envs.close()
    # the carrying line is read from the observation; check it against the env on every bot step
    res["carry_check"] = {"steps": len(rows),
                          "obs_equals_env": sum(carried(r["image"]) == r["carrying_env"] for r in rows),
                          "steps_carrying": sum(r["carrying_env"] is not None for r in rows)}
    res["phase_steps"] = dict(collections.Counter(r["phase"] for r in rows if r["seed"] >= 10000))
    samples = []
    for want in ("before pickup", "pickup", "carrying", "drop"):
        r = next(x for x in rows if x["seed"] >= 10000 and x["phase"] == want)
        samples.append({"phase": want, "seed": r["seed"], "step": r["step"], "bot": r["action_name"],
                        "state": state_text(r["text"], r["mission"])})
    res["samples"] = samples
    res["question"] = question_putnext()
    (OUT / "stats.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("samples", "question")}, default=str))


# ---------------------------------------------------------------- 10b

def dump() -> None:
    out = pathlib.Path(TRAIN_DUMP)
    out.parent.mkdir(parents=True, exist_ok=True)
    kept, steps, dropped = 0, 0, []
    with open(out, "w", encoding="utf-8") as f:
        for s in seeds_of("0-999"):
            rows, ok, _ = bot_episode(s)
            if not ok or any(r["action"] not in ACT for r in rows):
                dropped.append({"seed": s, "bot_success": ok})
                continue
            for r in rows:
                f.write(json.dumps(r) + "\n")
            kept += 1
            steps += len(rows)
    res = {"env": ENV, "seeds": "0-999", "kept_episodes": kept, "kept_steps": steps, "dropped": dropped}
    pathlib.Path(TRAIN_DUMP + ".summary.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res))


def train(seed: int, no_carry: bool) -> None:
    import torch
    from laya.train import TrainConfig, finetune

    from probe.laya_model import BASE_REV, FT_ROOT, base_dir
    tag = "putnext-nocarry" if no_carry else "putnext"
    rows_path = f"data/laya_rows_{tag}_train.jsonl"
    rows = [json.loads(l) for l in open(TRAIN_DUMP, encoding="utf-8")]
    q = question_putnext()
    with open(rows_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"state": state_text(r["text_nocarry" if no_carry else "text"], r["mission"]),
                                "questions": q, "expected": {QID: r["action_name"]}}) + "\n")
    name = f"{tag}-s{seed}"
    out = os.path.join(FT_ROOT, name)
    cfg = TrainConfig(shuffle_options=("choice",), seed=seed)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    rep = finetune(rows_path, base_dir(), out, cfg)
    summary = {"name": name, "checkpoint": f"babyai-laya-ft/{name}", "base": f"convaiinnovations/laya@{BASE_REV}",
               "carry_line": not no_carry, "episodes": len({r["seed"] for r in rows}), "rows": len(rows),
               "action_rows": dict(collections.Counter(r["action_name"] for r in rows)),
               "config": {k: str(v) for k, v in cfg.__dict__.items()},
               "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0)),
               "train_minutes": round((time.time() - t0) / 60, 2),
               "gpu_peak_alloc_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               "gpu_peak_reserved_gb": round(torch.cuda.max_memory_reserved() / 2**30, 2),
               "gpu": torch.cuda.get_device_name(0),
               **{k: rep.get(k) for k in ("train_items", "calibration_items", "temperature", "epoch_loss", "calibration")}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"train-{name}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("name", "rows", "train_minutes", "gpu_peak_alloc_gb", "epoch_loss")},
                     default=str))


def stepeval(model: str, name: str, no_carry: bool) -> None:
    rows = [x for s in seeds_of(DEV) for x in bot_episode(s)[0] if x["action_name"] in CH]
    sc = Scorer(model)
    key = "text_nocarry" if no_carry else "text"
    states = [state_text(r[key], r["mission"]) for r in rows]
    fwd, rev = sc(states), sc(states, list(reversed(CH)))
    for r, p, q in zip(rows, fwd, rev):
        r["m"] = ranked(p)[0]
        r["r"] = max(reversed(CH), key=lambda c: q.get(c, 0.0))

    def acc(sub):
        return {"n": len(sub), "agree": round(sum(r["m"] == r["action_name"] for r in sub) / max(len(sub), 1), 4)}

    res = {"model": f"babyai-laya-ft/{os.path.basename(model.rstrip('/'))}", "carry_line": not no_carry,
           "steps": len(rows), "all": acc(rows), "by_phase": {ph: acc([r for r in rows if r["phase"] == ph]) for ph in PHASES},
           "order_flip_rate": round(sum(r["m"] != r["r"] for r in rows) / len(rows), 4),
           "confusion_bot_to_model": {b: dict(collections.Counter(r["m"] for r in rows if r["action_name"] == b)) for b in CH},
           "model_choice_share": dict(collections.Counter(r["m"] for r in rows))}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"stepeval-{name}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("model", "steps", "all", "by_phase", "order_flip_rate")}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["stats", "loop", "dump", "train", "stepeval"])
    ap.add_argument("--scorer", default="laya", choices=["laya", "fixed", "bot", "random"])
    ap.add_argument("--policy", default="none", choices=["none", "reset"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--base", default=None)
    ap.add_argument("--seeds", default=DEV)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-carry", action="store_true", help="10d: state text without the carrying line")
    a = ap.parse_args()
    if a.mode == "stats":
        return stats()
    if a.mode == "loop":
        return loop(a)
    if a.mode == "dump":
        return dump()
    if a.mode == "train":
        return train(a.seed, a.no_carry)
    return stepeval(os.path.expanduser(a.model), a.name, a.no_carry)


if __name__ == "__main__":
    main()
