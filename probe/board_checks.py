"""Stage 3.5 supplement (board request 11-14): checks only, no model runs, no retraining.

1. Mission swap: is success judged at the swapped target's position? (instrs.desc.obj_poss after the swap,
   and where the bot actually ends when it walks the swapped mission)
2. Mean steps on the same episodes: bot mean over the episodes each model (seed 0/1/2) won.
4. Swap difficulty: bot steps to the original vs the swapped target on the same 197 episodes,
   split by whether that target is visible at step 0.
Writes reports/stage3_5/board_checks.json. Dev seeds 10000-10299 only.
"""
from __future__ import annotations

import json
import pathlib
import statistics as st

from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.closed_loop import make_env
from probe.text_stats import categorize

SEEDS = range(10000, 10300)


def visible(obs, u) -> bool:
    d = u.instrs.desc
    return not categorize({"image": obs["image"], "target": {"type": d.type, "color": d.color},
                           "n_matching": len(d.obj_poss)})["target_unseen"]


def walk_bot(env):
    """Bot plays to the end; returns (steps, success, front cell at the end)."""
    u = env.unwrapped
    bot, last, n = BabyAIBot(u), None, 0
    while True:
        a = int(bot.replan(last))
        _, r, term, trunc, _ = env.step(a)
        last, n = a, n + 1
        if term or trunc:
            return n, bool(term and r > 0), tuple(int(v) for v in u.front_pos)


def summary(xs):
    return {"n": len(xs), "mean": round(st.mean(xs), 2), "median": st.median(xs)} if xs else {"n": 0}


def main() -> None:
    out = {}

    # 1 + 4
    rows = []
    for s in SEEDS:
        made = make_env(s, swap=True)
        if made is None:
            continue
        env, obs, orig = made
        u = env.unwrapped
        new_poss = [tuple(int(v) for v in p) for p in u.instrs.desc.obj_poss]
        new_obj = u.grid.get(*new_poss[0])
        sw_vis = visible(obs, u)
        sw_steps, sw_ok, sw_front = walk_bot(env)
        env.close()
        env0, obs0, _ = make_env(s, swap=False)
        or_vis = visible(obs0, env0.unwrapped)
        or_steps, or_ok, _ = walk_bot(env0)
        env0.close()
        rows.append({"seed": s, "orig_pos": list(orig["pos"]), "new_pos": list(new_poss[0]),
                     "new_matches_desc": len(new_poss) == 1 and (new_obj.type, new_obj.color) == (u.instrs.desc.type, u.instrs.desc.color),
                     "new_differs_from_orig": tuple(orig["pos"]) != new_poss[0],
                     "bot_swap_success": sw_ok, "bot_swap_ended_facing_new": sw_front == new_poss[0],
                     "bot_swap_ended_facing_orig": sw_front == tuple(orig["pos"]),
                     "orig_visible": or_vis, "swap_visible": sw_vis, "bot_orig_steps": or_steps, "bot_swap_steps": sw_steps,
                     "bot_orig_success": or_ok})
    n = len(rows)
    out["1_swap_check"] = {
        "episodes": n,
        "obj_poss_is_the_new_object": sum(r["new_matches_desc"] for r in rows),
        "new_target_differs_from_original": sum(r["new_differs_from_orig"] for r in rows),
        "bot_success_on_swapped_mission": sum(r["bot_swap_success"] for r in rows),
        "bot_ended_facing_new_target": sum(r["bot_swap_ended_facing_new"] for r in rows),
        "bot_ended_facing_original_target": sum(r["bot_swap_ended_facing_orig"] for r in rows),
    }
    o = [r["bot_orig_steps"] for r in rows]
    w = [r["bot_swap_steps"] for r in rows]
    out["4_swap_difficulty"] = {
        "original_target": summary(o),
        "swapped_target": summary(w),
        "original_target_visible_at_start": summary([r["bot_orig_steps"] for r in rows if r["orig_visible"]]),
        "original_target_unseen_at_start": summary([r["bot_orig_steps"] for r in rows if not r["orig_visible"]]),
        "swapped_target_visible_at_start": summary([r["bot_swap_steps"] for r in rows if r["swap_visible"]]),
        "swapped_target_unseen_at_start": summary([r["bot_swap_steps"] for r in rows if not r["swap_visible"]]),
        "swap_longer_episodes": sum(b > a for a, b in zip(o, w)),
        "swap_shorter_episodes": sum(b < a for a, b in zip(o, w)),
        "same_length_episodes": sum(b == a for a, b in zip(o, w)),
    }

    # 2: per_episode = [success, steps, bot_steps]
    same = {}
    for k in range(3):
        pe = json.load(open(f"reports/stage3_5/model-s{k}.json", encoding="utf-8"))["per_episode"]
        won = [v for v in pe.values() if v[0]]
        same[f"seed{k}"] = {"model_won": len(won), "model_mean_steps_on_won": round(st.mean(v[1] for v in won), 2),
                            "bot_mean_steps_on_same_won": round(st.mean(v[2] for v in won), 2),
                            "bot_mean_steps_all_300": round(st.mean(v[2] for v in pe.values()), 2)}
    out["2_mean_steps_same_episodes"] = same

    pathlib.Path("reports/stage3_5/board_checks.json").write_text(
        json.dumps({**out, "per_episode_swap": rows}, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
