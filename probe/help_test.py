"""Help test (reports/help_test_prereg.md): on the dev rooms Laya fails, does 1-3 helps at the moment it gets stuck
rescue the room? Stuck = back at an (x, y, heading) already visited in this room. One help = one action put in instead
of the model's. A: the expert bot's action. B: the best of the three actions (search, an upper bound).
Usage (Windows venv, CPU): python -m probe.help_test --model <dir> --onnx <laya_fp32.onnx> [--out reports/help_test.json]
"""
from __future__ import annotations

import argparse
import json
import time

import gymnasium as gym

from probe.correct_loop import ENV_ID, NAME_TO_ACT, bot_choice, clone
from probe.laya_model import OnnxChooser
from probe.obs_text import CHOICES, obs_to_text

SEEDS = range(10000, 10300)


class Laya:
    """Model choice per input text, cached (the model is deterministic and has no memory)."""

    def __init__(self, chooser):
        self.ch, self.cache = chooser, {}

    def __call__(self, obs) -> str:
        text = obs_to_text(obs["image"], obs["direction"])
        k = (text, obs["mission"])
        if k not in self.cache:
            self.cache[k] = self.ch.choose_batch([text], [obs["mission"]])[0][0]
        return self.cache[k]


def key(env):
    u = env.unwrapped
    return int(u.agent_pos[0]), int(u.agent_pos[1]), int(u.agent_dir)


def go(env, obs, visited, laya, helps_left, mode, log):
    """Run the model from here. Returns (result, steps_taken_total, helps_used, help_actions) of the best branch.
    result: "success" / "timeout" / "stuck" (no help left) / "wander" (64 steps, never back at a visited state)."""
    while True:
        k = key(env)
        if k in visited:
            if helps_left == 0:
                return "stuck", env.unwrapped.step_count, 0, []
            if mode == "bot":
                a = bot_choice(env)
                if a not in NAME_TO_ACT:
                    return "stuck", env.unwrapped.step_count, 0, []
                options = [a]
            else:
                options = list(CHOICES)
            log["helped"] = True
            best = None
            for a in options:
                e2 = env if len(options) == 1 else clone(env)
                obs2, r, term, trunc, _ = e2.step(NAME_TO_ACT[a])
                if term or trunc:
                    res = ("success" if term and r > 0 else "timeout", e2.unwrapped.step_count, 1, [a])
                else:
                    sub = go(e2, obs2, set(visited) | {k}, laya, helps_left - 1, mode, log)
                    res = (sub[0], sub[1], sub[2] + 1, [a] + sub[3])
                if best is None or (res[0] == "success" and (best[0] != "success" or res[2] < best[2])):
                    best = res
                if best[0] == "success" and best[2] == 1:
                    break
            return best
        visited.add(k)
        obs, r, term, trunc, _ = env.step(NAME_TO_ACT[laya(obs)])
        if term or trunc:
            if term and r > 0:
                return "success", env.unwrapped.step_count, 0, []
            return "timeout" if log.get("helped") else "wander", env.unwrapped.step_count, 0, []


def play(seed, laya, helps, mode):
    env = gym.make(ENV_ID)
    obs, _ = env.reset(seed=seed)
    return go(env, obs, set(), laya, helps, mode, {})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--out", default="reports/help_test.json")
    a = ap.parse_args()
    laya = Laya(OnnxChooser(a.model, a.onnx))
    t0 = time.time()
    base = {s: play(s, laya, 0, "bot") for s in SEEDS}
    failed = [s for s in SEEDS if base[s][0] != "success"]
    print(f"no help: {300 - len(failed)}/300 success, failed {len(failed)} ({time.time() - t0:.0f} s)", flush=True)
    rows = []
    for s in failed:
        row = {"seed": s, "no_help": base[s][0], "no_help_steps": base[s][1]}
        for mode in ("bot", "best"):
            for h in (1, 2, 3):
                res, steps, used, acts = play(s, laya, h, mode)
                row[f"{mode}_{h}"] = {"result": res, "steps": steps, "helps_used": used, "helps": acts}
        rows.append(row)
        print(s, row["no_help"], " ".join(f"{m}{h}:{row[f'{m}_{h}']['result'][0]}" for m in ("bot", "best") for h in (1, 2, 3)),
              f"({time.time() - t0:.0f} s)", flush=True)
    recorded = json.load(open("reports/stage3_5/model-s0.json", encoding="utf-8"))
    rec_failed = sorted(int(k) for k, v in recorded["per_episode"].items() if not v[0])
    n = len(failed)
    summary = {"failed": n, "same_as_stage3_5": rec_failed == failed, "stage3_5_failed": rec_failed,
               "stuck_rooms": sum(r["no_help"] == "stuck" for r in rows), "wander_rooms": sum(r["no_help"] == "wander" for r in rows)}
    for mode in ("bot", "best"):
        for h in (1, 2, 3):
            summary[f"{mode}_{h}_saved"] = sum(r[f"{mode}_{h}"]["result"] == "success" for r in rows)
    summary["verdict_1_help_works"] = summary["bot_1_saved"] * 3 >= n
    summary["verdict_3_helps_mostly"] = summary["bot_3_saved"] * 3 >= 2 * n
    out = {"prereg": "reports/help_test_prereg.md", "model": "babyai-laya-ft/gotolocal-s0 (ONNX fp32, CPU)",
           "seeds": "10000-10299", "summary": summary, "rooms": rows, "seconds": round(time.time() - t0)}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
