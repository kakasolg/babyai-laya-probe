"""Precision check (reports/precision_prereg.md): along the fp32 path of every dev room, score each distinct step with
fp32, bf16 one at a time and bf16 in batches of 128, and count near-ties and flipped top choices.
Usage (WSL venv, GPU): python -m probe.precision_check --model ~/babyai-laya-ft/gotolocal-s0 [--out reports/precision_check.json]
"""
from __future__ import annotations

import argparse
import json
import os
import time

import gymnasium as gym

from probe.correct_loop import ENV_ID, NAME_TO_ACT
from probe.laya_model import Chooser
from probe.laya_rows import question, state_text
from probe.laya_model import QID
from probe.obs_text import CHOICES, obs_to_text

SEEDS = range(10000, 10300)
MAX_STEPS = 64


def gap(p):
    v = sorted((p[c] for c in CHOICES), reverse=True)
    return v[0] - v[1]


def top(p):
    return max(CHOICES, key=lambda c: p[c])


def batched(ch, texts, missions):
    """bf16 in batches of 128 rows (the batch the stage-3.5 runs used)."""
    states = [state_text(t, m) for t, m in zip(texts, missions)]
    res = ch.agent.predict_batch(states, question(CHOICES), batch_size=128)
    return [{c: float(r["answers"][QID]["probabilities"][c]) for c in CHOICES} for r in res]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", default="reports/precision_check.json")
    a = ap.parse_args()
    t0 = time.time()
    assert not os.environ.get("LAYA_CUDA_AMP"), "start with LAYA_CUDA_AMP unset (the bf16 agent loads first)"
    bf = Chooser(a.model, device="cuda")
    os.environ["LAYA_CUDA_AMP"] = "fp32"
    fp = Chooser(a.model, device="cuda")

    rows = []
    for seed in SEEDS:
        assert 10000 <= seed < 10300
        env = gym.make(ENV_ID)
        obs, _ = env.reset(seed=seed)
        seen, result = set(), "timeout"
        for step in range(MAX_STEPS):
            u = env.unwrapped
            k = (int(u.agent_pos[0]), int(u.agent_pos[1]), int(u.agent_dir))
            if k in seen:
                result = "stuck"
                break
            seen.add(k)
            text = obs_to_text(obs["image"], obs["direction"])
            c, p = fp.choose_batch([text], [obs["mission"]])[0]
            rows.append({"seed": seed, "step": step, "text": text, "mission": obs["mission"],
                         "fp32": {x: float(p[x]) for x in CHOICES}})
            obs, r, term, trunc, _ = env.step(NAME_TO_ACT[c])
            if term or trunc:
                result = "success" if r > 0 else "timeout"
                break
        for row in rows:
            if row["seed"] == seed:
                row["room_result"] = result
    t_fp = time.time()
    for row in rows:
        _, p = bf.choose_batch([row["text"]], [row["mission"]])[0]
        row["bf16_one"] = {x: float(p[x]) for x in CHOICES}
    for row, p in zip(rows, batched(bf, [r["text"] for r in rows], [r["mission"] for r in rows])):
        row["bf16_batch"] = p

    n = len(rows)
    out = {"steps": n, "rooms": len(SEEDS),
           "room_results": {}, "fp32_gap_under": {}, "flips": {}, "prob_diff": {}, "seconds": round(time.time() - t0, 1)}
    res_by_seed = {r["seed"]: r["room_result"] for r in rows}
    for v in res_by_seed.values():
        out["room_results"][v] = out["room_results"].get(v, 0) + 1
    for th in (0.01, 0.02, 0.05):
        out["fp32_gap_under"][str(th)] = sum(gap(r["fp32"]) < th for r in rows)
    for name in ("bf16_one", "bf16_batch"):
        fl = [r for r in rows if top(r[name]) != top(r["fp32"])]
        out["flips"][name] = {
            "steps": len(fl), "rooms": len({r["seed"] for r in fl}),
            "list": [{"seed": r["seed"], "step": r["step"], "fp32_top": top(r["fp32"]), name + "_top": top(r[name]),
                      "fp32_gap": round(gap(r["fp32"]), 4), "room_result": r["room_result"]} for r in fl]}
        d = [abs(r[name][c] - r["fp32"][c]) for r in rows for c in CHOICES]
        out["prob_diff"][name] = {"mean": round(sum(d) / len(d), 5), "max": round(max(d), 4)}
    d = [abs(r["bf16_one"][c] - r["bf16_batch"][c]) for r in rows for c in CHOICES]
    out["prob_diff"]["one_vs_batch"] = {"mean": round(sum(d) / len(d), 5), "max": round(max(d), 4)}
    out["one_vs_batch_top_differs"] = sum(top(r["bf16_one"]) != top(r["bf16_batch"]) for r in rows)
    out["fp32_path_seconds"] = round(t_fp - t0, 1)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "flips"}, ensure_ascii=False))
    for name, v in out["flips"].items():
        print(name, v["steps"], "steps in", v["rooms"], "rooms")
        for x in v["list"]:
            print("  ", x)


if __name__ == "__main__":
    main()
