"""Run the expert bot on GoToObj and write one jsonl line per step.

Usage: python -m probe.dump_demos --seeds 0-999 --out data/demos_train.jsonl
Line: seed, step, mission, image (7x7x3 nested list), direction, action, action_name, text.
Seeds: train 0-999, eval 10000-10299 — never mix (README).
"""
from __future__ import annotations

import argparse
import json
import pathlib

import gymnasium as gym
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.obs_text import ACTIONS, obs_to_text

ENV_ID = "BabyAI-GoToObj-v0"


def seed_range(s: str) -> range:
    lo, hi = s.split("-")
    return range(int(lo), int(hi) + 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0-999")
    ap.add_argument("--out", default="data/demos_train.jsonl")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_lines = fails = 0
    with open(out, "w", encoding="utf-8") as f:
        for seed in seed_range(a.seeds):
            env = gym.make(ENV_ID)
            obs, _ = env.reset(seed=seed)
            bot = BabyAIBot(env.unwrapped)
            term = trunc = False
            reward, step = 0.0, 0
            while not (term or trunc):
                act = int(bot.replan())
                if act not in ACTIONS:
                    raise SystemExit(f"seed {seed} step {step}: bot used action {act} outside the 3 choices")
                f.write(json.dumps({
                    "seed": seed, "step": step, "mission": obs["mission"],
                    "image": obs["image"].tolist(), "direction": int(obs["direction"]),
                    "action": act, "action_name": ACTIONS[act],
                    "text": obs_to_text(obs["image"], obs["direction"]),
                }) + "\n")
                n_lines += 1
                step += 1
                obs, reward, term, trunc, _ = env.step(act)
            fails += not (term and reward > 0)
            env.close()
    print(f"{out}: {n_lines} steps, {len(seed_range(a.seeds))} episodes, bot failures {fails}")


if __name__ == "__main__":
    main()
