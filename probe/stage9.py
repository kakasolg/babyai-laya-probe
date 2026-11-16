"""Stage 9 (board c7d1bc74, 11-16, MoKa): GoToLocal with 16 objects instead of 8 — env code unchanged, only
`gym.make("BabyAI-GoToLocal-v0", num_dists=16)`. Everything else is stage 5/6 letter for letter (state text,
question, three choices in the order turn left / turn right / forward, R-reset, step limit 64 = env default).

Usage (WSL, repo root, PY=~/babyai-laya-venv/bin/python, HF_HUB_OFFLINE=1):
  $PY -m probe.stage9 botstats --seeds 10000-10299 --name bot-dev     # what to write down first (9a)
  $PY -m probe.stage9 loop --scorer laya --model ~/babyai-laya-ft/gotolocal-s0 --name a-laya-s0 [--policy reset --base ...]
  $PY -m probe.stage9 loop --scorer fixed --name fixed [--policy reset --base ...]
  $PY -m probe.stage9 loop --scorer bot|random --name bot
  $PY -m probe.stage9 stepeval --model ~/babyai-laya-ft/gotolocal-s0 --name a-s0
  $PY -m probe.stage9 dump                                            # 9b: bot demos of train seeds 0-999
  $PY -m probe.stage9 train --seed 0                                  # -> ~/babyai-laya-ft/gotolocal16-s0

Seeds: train 0-999, dev 10000-10299. 60000-60299 are kept for a possible final check and refused here;
20000-20299 and 30000-30299 stay locked (dump_demos.guarded_seeds).
Fixed before any run (reports/stage9_prereg.md): every dev episode is kept; an episode in which the bot uses an action
outside the three is kept in the evaluation (its bot step count is the bot's own count) and dropped whole from training.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import statistics
import time
from collections import deque

import gymnasium as gym
import minigrid  # noqa: F401

from probe import closed_loop
from probe.dump_demos import episode as dump_episode
from probe.dump_demos import guarded_seeds
from probe.laya_rows import state_text, write_rows
from probe.obs_text import ACTIONS, CHOICES
from probe.text_stats import categorize

ENV = "BabyAI-GoToLocal-v0"
KW = {"num_dists": 16}
closed_loop.ENV_KWARGS.update(KW)  # Ep / bot_steps in closed_loop now build the 16-object room

from probe import stage5  # noqa: E402  (after the kwargs are set; stage5 builds its episodes through closed_loop)

OUT = pathlib.Path("reports/stage9")
DEV = "10000-10299"
FINAL9 = range(60000, 60300)
TRAIN_DUMP = "data/gotolocal16_train.jsonl"
ROWS = "data/laya_rows_gotolocal16_train.jsonl"
DV = [(1, 0), (0, 1), (-1, 0), (0, -1)]  # minigrid agent_dir 0 right, 1 down, 2 left, 3 up


def seeds_of(s: str):
    r = guarded_seeds(s)
    if any(x in FINAL9 for x in r):
        raise SystemExit("60000-60299 are kept for the stage-9 final check (board 11-16) and are not opened here")
    return r


# ---------------------------------------------------------------- what to write down first

def shortest(u, target, ignore_others: bool):
    """Fewest actions until a matching object is directly ahead (BFS over x, y, heading).
    ignore_others: objects that do not match the mission are treated as empty floor (walls and matches still block)."""
    def match(o):
        return o is not None and o.type not in ("wall", "door") and o.type == target["type"] and \
            (target["color"] is None or o.color == target["color"])

    def free(x, y):
        o = u.grid.get(x, y)
        if o is None:
            return True
        return ignore_others and o.type not in ("wall", "door") and not match(o)

    def done(x, y, d):
        return match(u.grid.get(x + DV[d][0], y + DV[d][1]))

    s0 = (int(u.agent_pos[0]), int(u.agent_pos[1]), int(u.agent_dir))
    if done(*s0):
        return 0
    seen, q = {s0: 0}, deque([s0])
    while q:
        x, y, d = q.popleft()
        n = seen[(x, y, d)]
        nxt = [(x, y, (d + 3) % 4), (x, y, (d + 1) % 4)]
        fx, fy = x + DV[d][0], y + DV[d][1]
        if free(fx, fy):
            nxt.append((fx, fy, d))
        for s in nxt:
            if s not in seen:
                seen[s] = n + 1
                if done(*s):
                    return n + 1
                q.append(s)
    return None


def botstats(seeds, name: str) -> None:
    eps = []
    acts = collections.Counter()
    for s in seeds:
        lines, ok, a = dump_episode(ENV, s, KW)
        env = gym.make(ENV, **KW)
        env.reset(seed=s)
        u = env.unwrapped
        t = {"type": u.instrs.desc.type, "color": u.instrs.desc.color}
        n_obj = sum(1 for o in u.grid.grid if o is not None and o.type not in ("wall", "door"))
        sp, sp_free = shortest(u, t, False), shortest(u, t, True)
        env.close()
        r0 = lines[0]
        acts.update(a)
        eps.append({"seed": s, "ok": ok, "n": len(a), "other": [x for x in a if x not in ACTIONS], "objects": n_obj,
                    "visible0": not categorize(r0)["target_unseen"], "n_matching": r0["n_matching"],
                    "shortest": sp, "shortest_ignoring_others": sp_free})
    lens = [e["n"] for e in eps]
    det = [e for e in eps if e["shortest"] is not None and e["shortest_ignoring_others"] is not None
           and e["shortest"] > e["shortest_ignoring_others"]]
    res = {"env": ENV, "kwargs": KW, "seeds": f"{seeds[0]}-{seeds[-1]}", "episodes": len(eps),
           "bot_success": sum(e["ok"] for e in eps),
           "objects_in_room": dict(collections.Counter(e["objects"] for e in eps)),
           "actions": {ACTIONS.get(k, f"other:{k}"): v for k, v in sorted(acts.items())},
           "episodes_with_other_actions": [{"seed": e["seed"], "actions": e["other"]} for e in eps if e["other"]],
           "bot_steps": {"mean": round(statistics.mean(lens), 2), "median": statistics.median(lens), "max": max(lens),
                         "hist": dict(sorted(collections.Counter(min(n, 20) for n in lens).items()))},
           "target_visible_at_start": sum(e["visible0"] for e in eps),
           "two_or_more_matching": sum(e["n_matching"] >= 2 for e in eps),
           "shortest_mean": round(statistics.mean(e["shortest"] for e in eps if e["shortest"] is not None), 2),
           "shortest_ignoring_others_mean": round(statistics.mean(
               e["shortest_ignoring_others"] for e in eps if e["shortest_ignoring_others"] is not None), 2),
           "unreachable": [e["seed"] for e in eps if e["shortest"] is None],
           "detour_episodes": len(det), "detour_extra_steps_mean": round(statistics.mean(
               e["shortest"] - e["shortest_ignoring_others"] for e in det), 2) if det else 0,
           "bot_above_shortest": sum(e["shortest"] is not None and e["n"] > e["shortest"] for e in eps),
           "per_episode": {e["seed"]: {k: e[k] for k in ("n", "shortest", "shortest_ignoring_others", "visible0",
                                                         "n_matching", "objects")} for e in eps}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "per_episode"}))


# ---------------------------------------------------------------- closed loop

def simple_summary(eps, name, policy):
    steps = [s for e in eps for s in e.steps]
    blocked = sum(s["policy"] == "forward" and not s["moved"] for s in steps)
    return {"name": name, "policy": policy, "episodes": len(eps), "all": stage5.rate(eps),
            "timeout": sum(e.timeout for e in eps),
            "target_visible_at_start": stage5.rate([e for e in eps if e.visible_at_start]),
            "target_unseen_at_start": stage5.rate([e for e in eps if not e.visible_at_start]),
            "blocked_forward_steps": blocked, "steps_total": len(steps),
            "actions": dict(collections.Counter(s["policy"] for s in steps)),
            "per_episode": {e.seed: {"end": "success" if e.success else "timeout" if e.timeout else "unfinished",
                                     "steps": len(e.steps), "bot": e.bot_n} for e in eps}}


def loop(a) -> None:
    seeds = list(seeds_of(a.seeds))
    if a.scorer in ("bot", "random"):
        eps, _ = closed_loop.run(a.scorer, seeds)
        res = simple_summary(eps, a.name, a.scorer)
    else:
        sc = stage5.make_scorer(a.scorer, a.model and os.path.expanduser(a.model))
        eps, aborted = stage5.run_loop(sc, a.policy, seeds)
        base = json.load(open(a.base, encoding="utf-8")) if a.base else None
        res = stage5.summarize(eps, a.name, sc, a.policy, aborted, base)
        res.pop("all_fail_12_solved", None)  # stage-5 list of 8-object seeds, meaningless here
        res["model"] = a.model if a.scorer == "laya" else "none (fixed scores)"
    res["blocked_forward_rate"] = round(res["blocked_forward_steps"] / max(res["steps_total"], 1), 4)
    res["env"], res["kwargs"], res["seeds"] = ENV, KW, a.seeds
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.name}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res.get(k) for k in ("name", "all", "timeout", "blocked_forward_rate", "vs_no_rule")},
                     default=str))


# ---------------------------------------------------------------- step eval (bot trajectories of the dev seeds)

def stepeval(model: str, name: str) -> None:
    from probe.laya_model import Chooser
    rows = [x for s in seeds_of(DEV) for x in dump_episode(ENV, s, KW)[0] if x["action_name"] in CHOICES]
    ch = Chooser(model)
    texts, missions = [r["text"] for r in rows], [r["mission"] for r in rows]
    fwd = ch.choose_batch(texts, missions)
    rev = ch.choose_batch(texts, missions, choices=list(reversed(CHOICES)))
    for r, (c, _), (rc, _) in zip(rows, fwd, rev):
        r["m"], r["r"], r["cat"] = c, rc, categorize(r)

    def acc(sub):
        return {"n": len(sub), "agree": round(sum(r["m"] == r["action_name"] for r in sub) / max(len(sub), 1), 4)}

    res = {"model": f"babyai-laya-ft/{os.path.basename(model.rstrip('/'))}", "env": ENV, "kwargs": KW,
           "steps": len(rows), "all": acc(rows),
           "target_visible": acc([r for r in rows if not r["cat"]["target_unseen"]]),
           "target_unseen": acc([r for r in rows if r["cat"]["target_unseen"]]),
           "distractor_closer": acc([r for r in rows if r["cat"]["distractor_closer"]]),
           "two_matching": acc([r for r in rows if r["cat"]["two_matching"]]),
           "order_flip_rate": round(sum(r["m"] != r["r"] for r in rows) / len(rows), 4),
           "confusion_bot_to_model": {b: dict(collections.Counter(r["m"] for r in rows if r["action_name"] == b))
                                      for b in CHOICES}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"stepeval-{name}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res))


# ---------------------------------------------------------------- 9b

def dump() -> None:
    out = pathlib.Path(TRAIN_DUMP)
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = steps = 0
    dropped, lens = [], []
    with open(out, "w", encoding="utf-8") as f:
        for s in seeds_of("0-999"):
            lines, ok, a = dump_episode(ENV, s, KW)
            lens.append(len(a))
            if not ok or any(x not in ACTIONS for x in a):
                dropped.append({"seed": s, "bot_success": ok, "actions": [x for x in a if x not in ACTIONS]})
                continue
            for ln in lines:
                f.write(json.dumps(ln) + "\n")
            kept += 1
            steps += len(lines)
    res = {"env": ENV, "kwargs": KW, "seeds": "0-999", "kept_episodes": kept, "kept_steps": steps,
           "dropped": dropped, "bot_mean_steps": round(statistics.mean(lens), 2)}
    pathlib.Path(TRAIN_DUMP + ".summary.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res))


def train(seed: int) -> None:
    import torch
    from laya.train import TrainConfig, finetune

    from probe.laya_model import BASE_REV, FT_ROOT, base_dir
    n = write_rows(TRAIN_DUMP, ROWS)
    name = f"gotolocal16-s{seed}"
    out = os.path.join(FT_ROOT, name)
    cfg = TrainConfig(shuffle_options=("choice",), seed=seed)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    rep = finetune(ROWS, base_dir(), out, cfg)
    summary = {"name": name, "checkpoint": f"babyai-laya-ft/{name}", "base": f"convaiinnovations/laya@{BASE_REV}",
               "rows": n, "config": {k: str(v) for k, v in cfg.__dict__.items()},
               "train_minutes": round((time.time() - t0) / 60, 2),
               "gpu_peak_alloc_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               "gpu_peak_reserved_gb": round(torch.cuda.max_memory_reserved() / 2**30, 2),
               "gpu": torch.cuda.get_device_name(0),
               **{k: rep.get(k) for k in ("train_items", "calibration_items", "temperature", "epoch_loss", "calibration")}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"train-s{seed}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("rows", "train_minutes", "gpu_peak_alloc_gb", "epoch_loss")}, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["botstats", "loop", "stepeval", "dump", "train"])
    ap.add_argument("--scorer", default="laya", choices=["laya", "fixed", "bot", "random"])
    ap.add_argument("--policy", default="none", choices=["none", "reset"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--base", default=None)
    ap.add_argument("--seeds", default=DEV)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.mode == "botstats":
        return botstats(list(seeds_of(a.seeds)), a.name)
    if a.mode == "loop":
        return loop(a)
    if a.mode == "stepeval":
        return stepeval(os.path.expanduser(a.model), a.name)
    if a.mode == "dump":
        return dump()
    return train(a.seed)


if __name__ == "__main__":
    main()
