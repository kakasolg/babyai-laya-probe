"""Run the expert bot and write one jsonl line per step.

Usage: python -m probe.dump_demos --seeds 0-999 --out data/gotolocal_train.jsonl [--env BabyAI-GoToLocal-v0]
Line: seed, step, mission, target (type/color from the instruction), n_matching (objects in the room
that satisfy the mission), image (7x7x3 nested list), direction, action, action_name, text.
An episode in which the bot uses an action outside the 3 choices is dropped whole and counted.
Seeds: train 0-999, eval 10000-10299 — never mix (README).
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib

import gymnasium as gym
import minigrid  # noqa: F401 — registers the BabyAI envs
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.obs_text import ACTIONS, obs_to_text

ENV_ID = "BabyAI-GoToLocal-v0"


def seed_range(s: str) -> range:
    lo, hi = s.split("-")
    return range(int(lo), int(hi) + 1)


def episode(env_id: str, seed: int):
    """Bot episode -> (lines, success, all_actions)."""
    env = gym.make(env_id)
    obs, _ = env.reset(seed=seed)
    u = env.unwrapped
    desc = u.instrs.desc
    target = {"type": desc.type, "color": desc.color}
    n_matching = len(desc.obj_poss)
    bot = BabyAIBot(u)
    lines, acts = [], []
    term = trunc = False
    reward, step = 0.0, 0
    while not (term or trunc):
        act = int(bot.replan())
        acts.append(act)
        lines.append({
            "seed": seed, "step": step, "mission": obs["mission"], "target": target, "n_matching": n_matching,
            "image": obs["image"].tolist(), "direction": int(obs["direction"]),
            "action": act, "action_name": ACTIONS.get(act, f"other:{act}"),
            "text": obs_to_text(obs["image"], obs["direction"]),
        })
        step += 1
        obs, reward, term, trunc, _ = env.step(act)
    env.close()
    return lines, term and reward > 0, acts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=ENV_ID)
    ap.add_argument("--seeds", default="0-999")
    ap.add_argument("--out", default="data/gotolocal_train.jsonl")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_lines = fails = 0
    dropped, all_acts, lengths = [], collections.Counter(), []
    with open(out, "w", encoding="utf-8") as f:
        for seed in seed_range(a.seeds):
            lines, ok, acts = episode(a.env, seed)
            fails += not ok
            all_acts.update(acts)
            lengths.append(len(acts))
            if any(x not in ACTIONS for x in acts):
                dropped.append({"seed": seed, "actions": [x for x in acts if x not in ACTIONS]})
                continue
            for ln in lines:
                f.write(json.dumps(ln) + "\n")
            n_lines += len(lines)
    summary = {"env": a.env, "seeds": a.seeds, "episodes": len(lengths), "bot_success": len(lengths) - fails,
               "mean_steps": round(sum(lengths) / len(lengths), 2), "max_steps_taken": max(lengths),
               "actions_used": dict(sorted(all_acts.items())), "dropped_episodes": dropped,
               "kept_episodes": len(lengths) - len(dropped), "kept_steps": n_lines}
    pathlib.Path(str(out) + ".summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
