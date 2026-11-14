"""Stage 4 check: is the bot's choice, asked from a state the model walked into, trustworthy?

For each seed, roll the model (no corrections, no escape) to the end; at every step build a fresh bot
on a copy of the env and let it play alone to the end. Reports the share of steps where it succeeds.
Usage: python -m probe.check_fresh_bot [--seeds ...] [--model ~/babyai-laya-ft/gotolocal-s0]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib

import gymnasium as gym

from probe.correct_loop import ENV_ID, NAME_TO_ACT, bot_finishes, default_seeds
from probe.laya_model import Chooser
from probe.obs_text import obs_to_text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=None)
    ap.add_argument("--model", default=os.path.expanduser("~/babyai-laya-ft/gotolocal-s0"))
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else default_seeds()
    ch = Chooser(a.model)
    per, total, ok, ok_full = {}, 0, 0, 0
    for seed in seeds:
        env = gym.make(ENV_ID)
        obs, _ = env.reset(seed=seed)
        n = good = good_full = 0
        done = False
        while not done:
            n += 1
            good += bot_finishes(env)
            good_full += bot_finishes(env, reset_budget=True)
            (c, _), = ch.choose_batch([obs_to_text(obs["image"], obs["direction"])], [obs["mission"]])
            obs, r, term, trunc, _ = env.step(NAME_TO_ACT[c])
            done = term or trunc
        per[seed] = {"steps": n, "bot_finishes": good, "bot_finishes_full_budget": good_full, "model_result": "success" if term and r > 0 else "timeout"}
        total, ok, ok_full = total + n, ok + good, ok_full + good_full
        print(seed, per[seed], flush=True)
    res = {"seeds": seeds, "steps_checked": total, "bot_finishes": ok, "rate": round(ok / total, 4),
           "bot_finishes_full_budget": ok_full, "rate_full_budget": round(ok_full / total, 4), "per_seed": per}
    pathlib.Path("reports/stage4").mkdir(parents=True, exist_ok=True)
    pathlib.Path("reports/stage4/fresh_bot_check.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("steps_checked", "bot_finishes", "rate", "bot_finishes_full_budget", "rate_full_budget")}))


if __name__ == "__main__":
    main()
