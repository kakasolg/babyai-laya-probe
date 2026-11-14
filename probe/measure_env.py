"""Re-measure the numbers the cloud session reported (README "1단계 재측정").

Usage: python -m probe.measure_env [--out reports/env_check.json]
CPU only, no model.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import platform
import sys

import gymnasium as gym
import minigrid
import numpy as np
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.obs_text import rel

ENVS = ["BabyAI-GoToRedBallGrey-v0", "BabyAI-GoToObj-v0", "BabyAI-GoToLocal-v0", "BabyAI-Open-v0"]


def run_bot(env_id: str, seed: int):
    """One bot episode. Returns (success, steps, actions, records) — records = per-step (image, dir, mission, action)."""
    env = gym.make(env_id)
    obs, _ = env.reset(seed=seed)
    bot = BabyAIBot(env.unwrapped)
    recs, acts = [], []
    reward, term, trunc = 0.0, False, False
    while not (term or trunc):
        a = int(bot.replan())
        recs.append((obs["image"].copy(), int(obs["direction"]), obs["mission"], a))
        acts.append(a)
        obs, reward, term, trunc, _ = env.step(a)
    info = {"room": [env.unwrapped.width, env.unwrapped.height], "max_steps": env.unwrapped.max_steps,
            "n_rooms": getattr(env.unwrapped, "num_rows", 1) * getattr(env.unwrapped, "num_cols", 1)}
    env.close()
    return term and reward > 0, len(acts), acts, recs, info


def check_view_coords(n: int = 200) -> int:
    """obs_text.rel() must agree with MiniGrid's own world->view mapping. Returns mismatch count."""
    bad = 0
    for s in range(n):
        env = gym.make("BabyAI-GoToObj-v0")
        env.reset(seed=s)
        u = env.unwrapped
        o = next(o for o in u.grid.grid if o is not None and o.type not in ("wall",))
        vc = u.get_view_coords(*o.cur_pos)
        ax, ay = u.agent_pos
        dx, dy = o.cur_pos[0] - ax, o.cur_pos[1] - ay
        # world offset -> (ahead, right) using the facing vector
        fx, fy = u.dir_vec
        rx, ry = u.right_vec
        want = (dx * fx + dy * fy, dx * rx + dy * ry)
        got = rel(int(vc[0]), int(vc[1]))
        bad += want != got
        env.close()
    return bad


def ambiguity(keys_actions):
    """keys_actions: list of (key, action). Returns (share of steps whose key has >1 action,
    share of steps a memoryless majority-vote policy gets wrong = best-case step error)."""
    by = collections.defaultdict(collections.Counter)
    for k, a in keys_actions:
        by[k][a] += 1
    n = len(keys_actions)
    split = sum(sum(c.values()) for c in by.values() if len(c) > 1)
    wrong = sum(sum(c.values()) - max(c.values()) for c in by.values())
    return {"steps": n, "distinct_keys": len(by), "split_step_share": round(split / n, 4),
            "majority_error": round(wrong / n, 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/env_check.json")
    a = ap.parse_args()
    res = {"python": platform.python_version(), "minigrid": minigrid.__version__, "gymnasium": gym.__version__,
           "numpy": np.__version__}

    res["bot_seed0_299"] = {}
    for env_id in ENVS:
        ok = exc = 0
        steps, acts = [], collections.Counter()
        info = None
        for s in range(300):
            try:
                succ, n, aa, _, info = run_bot(env_id, s)
            except Exception as e:  # noqa: BLE001 — counting bot failures is the point
                exc += 1
                print(f"{env_id} seed {s}: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            ok += succ
            steps.append(n)
            acts.update(aa)
        res["bot_seed0_299"][env_id] = {"success": ok, "exceptions": exc, "mean_steps": round(float(np.mean(steps)), 2),
                                       "max_steps_taken": int(max(steps)), "actions_used": dict(sorted(acts.items())),
                                       **(info or {})}
        print(env_id, res["bot_seed0_299"][env_id], flush=True)

    # GoToObj detail over the training seeds
    missions, recs_all, acts = set(), [], collections.Counter()
    env = gym.make("BabyAI-GoToObj-v0")
    res["gotoobj_spaces"] = {"image": list(env.observation_space["image"].shape), "action_space": str(env.action_space)}
    env.close()
    for s in range(1000):
        _, _, aa, recs, _ = run_bot("BabyAI-GoToObj-v0", s)
        for img, d, m, act in recs:
            missions.add(m)
            recs_all.append((img.tobytes(), d, m, act))
        acts.update(aa)
    res["gotoobj_seed0_999"] = {
        "steps": len(recs_all), "missions": len(missions), "actions_used": dict(sorted(acts.items())),
        "ambiguity_image_mission": ambiguity([((i, m), a) for i, d, m, a in recs_all]),
        "ambiguity_image_dir_mission": ambiguity([((i, d, m), a) for i, d, m, a in recs_all]),
    }
    res["view_coord_mismatch_of_200"] = check_view_coords()
    print(json.dumps(res["gotoobj_seed0_999"], indent=1), "view mismatch", res["view_coord_mismatch_of_200"])
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
