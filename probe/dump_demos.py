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


FINAL_SEEDS = range(20000, 20300)


def seed_range(s: str) -> range:
    lo, hi = s.split("-")
    return range(int(lo), int(hi) + 1)


def guarded_seeds(s: str, use_final: bool = False) -> range:
    """Seeds 20000-20299 only with the explicit stage-6 flag (board 11-15: one final run, then locked again)."""
    r = seed_range(s)
    if any(x in FINAL_SEEDS for x in r) and not use_final:
        raise SystemExit("20000-20299 are reserved for the final check (README)")
    return r


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
    # Eval seeds keep every episode (MoKa 11-14); only the train dump drops 3/4 episodes.
    ap.add_argument("--keep-all", action="store_true")
    ap.add_argument("--use-final-seeds", action="store_true", help="stage 6 only: allow 20000-20299")
    a = ap.parse_args()
    seeds = guarded_seeds(a.seeds, a.use_final_seeds)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_lines = fails = 0
    dropped, all_acts, lengths = [], collections.Counter(), []
    with open(out, "w", encoding="utf-8") as f:
        for seed in seeds:
            lines, ok, acts = episode(a.env, seed)
            fails += not ok
            all_acts.update(acts)
            lengths.append(len(acts))
            if any(x not in ACTIONS for x in acts):
                dropped.append({"seed": seed, "actions": [x for x in acts if x not in ACTIONS]})
                if not a.keep_all:
                    continue
            for ln in lines:
                f.write(json.dumps(ln) + "\n")
            n_lines += len(lines)
    summary = {"env": a.env, "seeds": a.seeds, "episodes": len(lengths), "bot_success": len(lengths) - fails,
               "mean_steps": round(sum(lengths) / len(lengths), 2), "max_steps_taken": max(lengths),
               "actions_used": dict(sorted(all_acts.items())), "episodes_with_other_actions": dropped,
               "kept_all": a.keep_all,
               "kept_episodes": len(lengths) - (0 if a.keep_all else len(dropped)), "kept_steps": n_lines}
    pathlib.Path(str(out) + ".summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
