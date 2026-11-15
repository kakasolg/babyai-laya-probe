"""Export model replays for the Godot viewer (godot/). Dev seeds only; 20000-20299 are refused.

For each seed: the room (objects, target), the bot's step count from the start, and the model's walk
step by step (position, facing, input text, three scores, model choice, fresh-bot choice).
Usage (WSL): python -m probe.export_godot [--seeds ...] [--out godot/data/episodes.json]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib

import gymnasium as gym
import minigrid  # noqa: F401

from probe.correct_loop import ENV_ID, NAME_TO_ACT, bot_choice, clone, default_seeds
from probe.laya_model import Chooser
from probe.laya_rows import state_text
from probe.obs_text import obs_to_text
from minigrid.utils.baby_ai_bot import BabyAIBot


def bot_steps(env) -> int | None:
    u = clone(env)
    bot, last, n = BabyAIBot(u), None, 0
    while True:
        a = int(bot.replan(last))
        _, r, term, trunc, _ = u.step(a)
        last, n = a, n + 1
        if term or trunc:
            return n if term and r > 0 else None


def room(u) -> dict:
    objs = []
    for x in range(u.width):
        for y in range(u.height):
            c = u.grid.get(x, y)
            if c is not None and c.type != "wall":
                objs.append({"x": x, "y": y, "type": c.type, "color": c.color})
    d = u.instrs.desc
    return {"width": u.width, "height": u.height, "objects": objs,
            "target": {"type": d.type, "color": d.color, "positions": [[int(p[0]), int(p[1])] for p in d.obj_poss]},
            "start": {"x": int(u.agent_pos[0]), "y": int(u.agent_pos[1]), "dir": int(u.agent_dir)},
            "max_steps": u.max_steps}


def public_model_id(path: str) -> str:
    """Checkpoint identifier for the published recording: the last two path parts, never a local absolute path.
    ~/babyai-laya-ft/gotolocal-s0 -> babyai-laya-ft/gotolocal-s0"""
    parts = [p for p in os.path.normpath(os.path.expanduser(path)).replace("\\", "/").split("/") if p not in ("", ".", "~")]
    return "/".join(parts[-2:])


def recording_json(model_id: str, episodes: list) -> str:
    """The exact text written to the recording file (godot/data/episodes.json is published with the web build)."""
    if os.path.isabs(model_id) or model_id.startswith("~") or ":" in model_id:
        raise ValueError(f"model id must not be a local path: {model_id!r}")
    return json.dumps({"model": model_id, "env": ENV_ID, "episodes": episodes}, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=None, help="comma list; default = 10000-10029 + the 12 all-model failures")
    ap.add_argument("--model", default=os.path.expanduser("~/babyai-laya-ft/gotolocal-s0"))
    ap.add_argument("--model-id", default=None, help="identifier written to the file (default: last two parts of --model)")
    ap.add_argument("--out", default="godot/data/episodes.json")
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else sorted(set(range(10000, 10030)) | set(default_seeds()))
    if any(20000 <= s < 20300 for s in seeds):
        raise SystemExit("20000-20299 are reserved for the final check (README)")
    hard = set(default_seeds())
    ch = Chooser(a.model)
    episodes = []
    for seed in seeds:
        env = gym.make(ENV_ID)
        obs, _ = env.reset(seed=seed)
        u = env.unwrapped
        ep = {"seed": seed, "mission": obs["mission"], "all_models_failed": seed in hard, **room(u),
              "bot_steps": bot_steps(env), "steps": []}
        done = False
        while not done:
            text = obs_to_text(obs["image"], obs["direction"])
            (c, probs), = ch.choose_batch([text], [obs["mission"]])
            ep["steps"].append({"x": int(u.agent_pos[0]), "y": int(u.agent_pos[1]), "dir": int(u.agent_dir),
                                "input": state_text(text, obs["mission"]), "probs": {k: round(v, 3) for k, v in probs.items()},
                                "choice": c, "bot": bot_choice(env)})
            obs, r, term, trunc, _ = env.step(NAME_TO_ACT[c])
            done = term or trunc
        ep["result"] = "success" if term and r > 0 else "timeout"
        ep["end"] = {"x": int(u.agent_pos[0]), "y": int(u.agent_pos[1]), "dir": int(u.agent_dir)}
        episodes.append(ep)
        print(seed, ep["result"], len(ep["steps"]), "bot", ep["bot_steps"], flush=True)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(recording_json(a.model_id or public_model_id(a.model), episodes), encoding="utf-8")
    print("wrote", out, len(episodes))


if __name__ == "__main__":
    main()
