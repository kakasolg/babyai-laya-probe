"""Export Laya replays of the put-next task (BabyAI-PutNextLocal-v0) for the Godot Lab screen. Dev seeds only.

Same idea as probe/export_godot.py (GoToLocal), with five choices and objects that move: every step records
the object list, what the agent carries, the exact text given to the model, its five scores, its choice and
the choice of a fresh expert bot from the same state. Checkpoint: stage 10b putnext-s0, no rule (stage 10c).
Usage (WSL): python -m probe.export_godot_putnext [--seeds ...] [--out godot/data/putnext_episodes.json]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib

import gymnasium as gym
import minigrid  # noqa: F401
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.export_godot import public_model_id
from probe.laya_rows import state_text
from probe.stage10 import ACT, ENV, NAME_TO_ACT, Scorer, obs_text, ranked, seeds_of

# 10000-10029 (three of them fail) plus two "never picked up" and two "picked up, never put down" failures
# of putnext-s0 on the dev seeds (reports/stage10/laya-s0.json)
DEFAULT_SEEDS = list(range(10000, 10030)) + [10040, 10041, 10032, 10043]


def clone(u):
    saved = (getattr(u, "window", None), getattr(u, "clock", None))
    u.window, u.clock = None, None
    try:
        return copy.deepcopy(u)
    finally:
        u.window, u.clock = saved


def bot_choice(u) -> str:
    try:
        return ACT.get(int(BabyAIBot(clone(u)).replan()), "other")
    except Exception as ex:  # noqa: BLE001
        return f"bot_error:{type(ex).__name__}"


def bot_steps(u) -> int | None:
    c = clone(u)
    bot, n = BabyAIBot(c), 0
    while True:
        _, r, term, trunc, _ = c.step(int(bot.replan()))
        n += 1
        if term or trunc:
            return n if term and r > 0 else None


def objects(u) -> list:
    out = []
    for x in range(u.width):
        for y in range(u.height):
            c = u.grid.get(x, y)
            if c is not None and c.type != "wall":
                out.append({"x": x, "y": y, "type": c.type, "color": c.color})
    return out


def carrying(u):
    c = u.carrying
    return None if c is None else {"type": c.type, "color": c.color}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=None, help="comma list (dev seeds only)")
    ap.add_argument("--model", default=os.path.expanduser("~/babyai-laya-ft/putnext-s0"))
    ap.add_argument("--out", default="godot/data/putnext_episodes.json")
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else DEFAULT_SEEDS
    for s in seeds:
        seeds_of(f"{s}-{s}")  # refuses the locked ranges (20000, 30000, 60000, 70000)
    sc = Scorer(a.model)
    episodes = []
    for seed in seeds:
        env = gym.make(ENV)
        obs, _ = env.reset(seed=seed)
        u = env.unwrapped
        d = u.instrs
        ep = {"seed": seed, "mission": obs["mission"], "width": u.width, "height": u.height,
              "move": {"type": d.desc_move.type, "color": d.desc_move.color},
              "fixed": {"type": d.desc_fixed.type, "color": d.desc_fixed.color},
              "max_steps": u.max_steps, "bot_steps": bot_steps(u), "steps": []}
        done = False
        while not done:
            text = obs_text(obs["image"], obs["direction"])
            p = sc([state_text(text, obs["mission"])])[0]
            c = ranked(p)[0]
            ep["steps"].append({"x": int(u.agent_pos[0]), "y": int(u.agent_pos[1]), "dir": int(u.agent_dir),
                                "objects": objects(u), "carrying": carrying(u),
                                "input": state_text(text, obs["mission"]),
                                "probs": {k: round(v, 3) for k, v in p.items()}, "choice": c, "bot": bot_choice(u)})
            obs, r, term, trunc, _ = env.step(NAME_TO_ACT[c])
            done = term or trunc
        ep["result"] = "success" if term and r > 0 else "timeout"
        ep["end"] = {"x": int(u.agent_pos[0]), "y": int(u.agent_pos[1]), "dir": int(u.agent_dir),
                     "objects": objects(u), "carrying": carrying(u)}
        episodes.append(ep)
        print(seed, ep["result"], len(ep["steps"]), "bot", ep["bot_steps"], flush=True)
    model_id = public_model_id(a.model)
    if os.path.isabs(model_id) or ":" in model_id:
        raise SystemExit(f"model id must not be a local path: {model_id!r}")
    out = pathlib.Path(a.out)
    out.write_text(json.dumps({"model": model_id, "env": ENV, "rule": "none", "episodes": episodes}, ensure_ascii=False),
                   encoding="utf-8")
    print("wrote", out, len(episodes))


if __name__ == "__main__":
    main()
