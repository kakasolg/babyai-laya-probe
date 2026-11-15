"""Stage 8a (board 11-15): next task BabyAI-PickupDist-v0, no training. Measure, look, stop.

Usage (WSL, repo root): python -m probe.stage8a [--tokenizer-alias english]
Writes reports/stage8a/stage8a.json, data/pickupdist_train.jsonl (git-ignored, every bot step of seeds 0-999),
data/laya_rows_pickupdist_train.jsonl (rows with the 4-choice question, a draft at 8a, confirmed 11-15; 8b trains on this file).

Fixed by the board (11-15):
  choices turn left / turn right / forward / pick up (this order), partial view 7x7, env unchanged.
  seeds: train 0-999, dev 10000-10299, final 30000-30299 (refused here), 20000-20299 never.
  control: no model, fixed scores forward 0.4 > left 0.3 > right 0.2 > pick up 0.1, no rule and R-reset
           (R-reset exactly as stage 5: key = obs text; all four tried -> clear that key only, take rank 1).
The state text is GoToLocal's obs_to_text unchanged; what may need changing is only written down (report §3).
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics

import gymnasium as gym
import minigrid  # noqa: F401
import numpy as np
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.dump_demos import guarded_seeds
from probe.laya_rows import question_pickup, state_text
from probe.measure_env import ambiguity
from probe.obs_text import AX, AY, IDX_TO_COLOR, IDX_TO_OBJECT, _SKIP, obs_to_text, rel

ENV = "BabyAI-PickupDist-v0"
ACTIONS4 = {0: "turn left", 1: "turn right", 2: "forward", 3: "pick up"}
CHOICES4 = list(ACTIONS4.values())
NAME_TO_ACT4 = {v: k for k, v in ACTIONS4.items()}
FIXED = {"forward": 0.4, "turn left": 0.3, "turn right": 0.2, "pick up": 0.1}
OUT = pathlib.Path("reports/stage8a")

# The question was a draft at 8a and was confirmed unchanged (MoKa 11-15 12:09): probe/laya_rows.py.


def matches(typ: str, color: str, target: dict) -> bool:
    return (target["type"] is None or typ == target["type"]) and (target["color"] is None or color == target["color"])


def visible(image):
    img = np.asarray(image)
    out = []
    for i in range(7):
        for j in range(7):
            o = int(img[i, j, 0])
            if o in _SKIP or (i, j) == (AX, AY):
                continue
            ahead, side = rel(i, j)
            out.append((ahead + abs(side), IDX_TO_OBJECT[o], IDX_TO_COLOR[int(img[i, j, 1])], ahead, side))
    return out


def categorize(r: dict) -> dict:
    vis = visible(r["image"])
    m = [v for v in vis if matches(v[1], v[2], r["target"])]
    other = [v for v in vis if v not in m]
    return {"target_unseen": not m,
            "distractor_closer": bool(m) and bool(other) and min(o[0] for o in other) < min(x[0] for x in m),
            "two_matching": r["n_matching"] >= 2, "pickup_step": r["action"] == 3,
            "target_ahead": any(v[3] == 1 and v[4] == 0 for v in m)}


def mission_kind(t: dict) -> str:
    return "both" if t["type"] and t["color"] else "color only" if t["color"] else "type only"


def bot_episode(seed: int):
    env = gym.make(ENV)
    obs, _ = env.reset(seed=seed)
    u = env.unwrapped
    d = u.instrs.desc
    target = {"type": d.type, "color": d.color}
    bot = BabyAIBot(u)
    # env obj_poss also counts grey WALL cells for "the/a grey object" (ObjDesc with type None) -> count objects only
    n_obj = sum(matches(o.type, o.color, target) for o in u.grid.grid if o is not None and o.type not in ("wall", "door"))
    rows, term, trunc, reward = [], False, False, 0.0
    while not (term or trunc):
        a = int(bot.replan())  # same call as probe/dump_demos.py (the GoToLocal training dump)
        rows.append({"seed": seed, "step": len(rows), "mission": obs["mission"], "target": target,
                     "n_matching": n_obj, "n_matching_env": len(d.obj_poss), "image": obs["image"].tolist(), "direction": int(obs["direction"]),
                     "action": a, "action_name": ACTIONS4.get(a, f"other:{a}"),
                     "text": obs_to_text(obs["image"], obs["direction"])})
        obs, reward, term, trunc, _ = env.step(a)
    env.close()
    return rows, bool(term and reward > 0), u.max_steps


def bot_stats(seeds):
    eps = {s: bot_episode(s) for s in seeds}
    lens = [len(r) for r, _, _ in eps.values()]
    acts = collections.Counter(x["action_name"] for r, _, _ in eps.values() for x in r)
    other = [s for s, (r, _, _) in eps.items() if any(x["action"] not in ACTIONS4 for x in r)]
    return eps, {"episodes": len(eps), "success": sum(ok for _, ok, _ in eps.values()),
                 "max_steps_env": sorted({m for _, _, m in eps.values()}),
                 "steps_mean": round(statistics.mean(lens), 2), "steps_median": statistics.median(lens),
                 "steps_max": max(lens), "actions": dict(acts), "episodes_with_other_actions": len(other),
                 "other_action_seeds": other}


# ---------------------------------------------------------------- model-free control (closed loop)

def control(seeds, policy: str, bot_n: dict):
    res = {}
    order = sorted(CHOICES4, key=lambda c: -FIXED[c])
    for s in seeds:
        env = gym.make(ENV)
        obs, _ = env.reset(seed=s)
        u = env.unwrapped
        t = {"type": u.instrs.desc.type, "color": u.instrs.desc.color}
        vis0 = any(matches(v[1], v[2], t) for v in visible(obs["image"]))
        tried, steps, interv, term, trunc, reward, wrong = {}, 0, 0, False, False, 0.0, False
        while not (term or trunc):
            text = obs_to_text(obs["image"], obs["direction"])
            c = order[0]
            if policy == "reset":
                tr = tried.setdefault(text, set())
                left = [o for o in order if o not in tr]
                if not left:
                    tr.clear()
                    left = order
                c = left[0]
                tr.add(c)
                interv += c != order[0]
            obs, reward, term, trunc, _ = env.step(NAME_TO_ACT4[c])
            steps += 1
            if u.carrying is not None and not (term and reward > 0):
                wrong = True
        ok = bool(term and reward > 0)
        res[s] = {"end": "success" if ok else "timeout", "steps": steps, "bot": bot_n[s], "visible_at_start": vis0,
                  "wrong_pickup": wrong, "interventions": interv}
        env.close()
    return res


def summarize_control(res, base=None):
    v = list(res.values())
    ok = lambda e: e["end"] == "success"  # noqa: E731
    out = {"success": sum(map(ok, v)), "within_2x_bot": sum(ok(e) and e["steps"] <= 2 * e["bot"] for e in v),
           "timeout": sum(e["end"] == "timeout" for e in v),
           "wrong_pickup_episodes": sum(e["wrong_pickup"] for e in v),
           "visible_at_start": f"{sum(ok(e) for e in v if e['visible_at_start'])}/{sum(e['visible_at_start'] for e in v)}",
           "unseen_at_start": f"{sum(ok(e) for e in v if not e['visible_at_start'])}/"
                              f"{sum(not e['visible_at_start'] for e in v)}",
           "steps_sum": sum(e["steps"] for e in v), "episodes_with_intervention": sum(e["interventions"] > 0 for e in v)}
    if base:
        out["saved"] = sorted(s for s in res if ok(res[s]) and not ok(base[s]))
        out["broken"] = sorted(s for s in res if not ok(res[s]) and ok(base[s]))
    return out


# ---------------------------------------------------------------- samples

def pick_samples(rows):
    rows = sorted(rows, key=lambda r: (r["seed"], r["step"]))
    want = [("pick up is correct", lambda r: r["cat"]["pickup_step"], 3),
            ("target not in view", lambda r: r["cat"]["target_unseen"], 2),
            ("color-only mission", lambda r: mission_kind(r["target"]) == "color only" and not r["cat"]["pickup_step"], 2),
            ("two or more matching objects", lambda r: r["cat"]["two_matching"] and not r["cat"]["target_unseen"], 2),
            ("distractor nearer than target", lambda r: r["cat"]["distractor_closer"], 1)]
    out, used = [], set()
    for label, f, n in want:
        for r in rows:
            if n == 0:
                break
            if r["seed"] in used or not f(r):
                continue
            used.add(r["seed"])
            out.append({"why": label, "seed": r["seed"], "step": r["step"], "bot": r["action_name"],
                        "state": state_text(r["text"], r["mission"])})
            n -= 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer-alias", default="english")
    ap.add_argument("--skip-dryrun", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"env": ENV, "minigrid": minigrid.__version__, "choices": CHOICES4}

    train, res["bot_train_0_999"] = bot_stats(guarded_seeds("0-999"))
    res["bot_0_199_for_cloud_check"] = {
        "success": sum(train[s][1] for s in range(200)), "steps_mean": round(statistics.mean(len(train[s][0]) for s in range(200)), 2),
        "actions": dict(collections.Counter(x["action_name"] for s in range(200) for x in train[s][0]))}
    dev, res["bot_dev_10000_10299"] = bot_stats(guarded_seeds("10000-10299"))

    rows = [x for r, _, _ in train.values() for x in r]
    with open("data/pickupdist_train.jsonl", "w", encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x) + "\n")
    for r in rows:
        r["cat"] = categorize(r)
    first = [r[0] for r, _, _ in train.values()]
    res["missions"] = {
        "distinct": len({r["mission"] for r in rows}),
        "kind_episodes": dict(collections.Counter(mission_kind(r["target"]) for r in first)),
        "article_episodes": dict(collections.Counter(r["mission"].split()[2] for r in first)),
        "two_or_more_matching_episodes": sum(r["n_matching"] >= 2 for r in first),
        "n_matching_hist": dict(sorted(collections.Counter(r["n_matching"] for r in first).items())),
        "n_matching_env_counts_walls": {
            "episodes": sum(r["n_matching_env"] != r["n_matching"] for r in first),
            "missions": sorted({r["mission"] for r in first if r["n_matching_env"] != r["n_matching"]}),
            "article_a_with_one_object": sum(r["n_matching"] == 1 and r["mission"].split()[2] == "a" for r in first)},
        "examples": sorted({r["mission"] for r in rows})[:12]}
    n = len(rows)
    res["step_categories"] = {"steps": n, **{k: round(sum(r["cat"][k] for r in rows) / n, 4)
                                             for k in ("pickup_step", "target_unseen", "distractor_closer",
                                                       "two_matching", "target_ahead")}}
    # pickup only when the target is directly ahead?  and is "target ahead" always pickup?
    res["pickup_vs_target_ahead"] = {
        "pickup_steps": sum(r["cat"]["pickup_step"] for r in rows),
        "pickup_with_target_1_ahead": sum(r["cat"]["pickup_step"] and r["cat"]["target_ahead"] for r in rows),
        "target_1_ahead_steps": sum(r["cat"]["target_ahead"] for r in rows),
        "target_1_ahead_not_pickup": dict(collections.Counter(r["action_name"] for r in rows
                                                              if r["cat"]["target_ahead"] and not r["cat"]["pickup_step"]))}
    res["text_check"] = {
        "object_types_seen": sorted({v[1] for r in rows for v in visible(r["image"])}),
        "agent_cell_nonempty_steps": sum(int(np.asarray(r["image"])[AX, AY, 0]) not in _SKIP for r in rows),
        "ambiguity_text+mission": ambiguity([((r["text"], r["mission"]), r["action"]) for r in rows]),
        "ambiguity_image+mission": ambiguity([((json.dumps(r["image"]), r["mission"]), r["action"]) for r in rows])}
    res["samples"] = pick_samples(rows)

    if not a.skip_dryrun:
        from probe.laya_dryrun import measure
        rows_path = "data/laya_rows_pickupdist_train.jsonl"
        q = question_pickup()
        with open(rows_path, "w", encoding="utf-8") as f:
            for r in rows:
                if r["action"] in ACTIONS4:
                    f.write(json.dumps({"state": state_text(r["text"], r["mission"]), "questions": q,
                                        "expected": {"action": r["action_name"]}}) + "\n")
        m = measure(rows_path, a.tokenizer_alias)
        m.pop("dir", None)
        res["laya_dryrun_draft_question"] = m

    bot_n = {s: len(dev[s][0]) for s in dev}
    seeds = list(guarded_seeds("10000-10299"))
    none = control(seeds, "none", bot_n)
    reset = control(seeds, "reset", bot_n)
    res["control_dev"] = {"fixed_probs": FIXED, "none": summarize_control(none),
                          "reset": summarize_control(reset, none)}
    res["control_dev_per_episode"] = {"none": none, "reset": reset}
    (OUT / "stage8a.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("samples", "control_dev_per_episode")}, default=str))


if __name__ == "__main__":
    main()
