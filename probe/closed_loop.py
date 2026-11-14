"""Stage 3: closed loop on the eval seeds. The policy walks; the env decides success.

Usage: python -m probe.closed_loop --policy random|forward|bot|model --model <ckpt> [--mask] --name <tag>
       [--seeds 10000-10299]
All episodes run in lockstep so a model policy is one batched forward pass per step.
For model policies a shadow bot (replan(action_taken=model action)) records what the bot would do.

Counted per policy:
  success, split by "target (a matching object) visible at step 0"
  timeout       truncated at max_steps (64) — looping/wandering
  wrong_object  failed and, at the end, the cell in front holds a non-matching object
  blocked_forward_share  share of steps that chose forward but did not move
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random

import gymnasium as gym
import minigrid  # noqa: F401
import numpy as np
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.dump_demos import seed_range
from probe.obs_text import ACTIONS, CHOICES, obs_to_text
from probe.text_stats import categorize

ENV_ID = "BabyAI-GoToLocal-v0"
NAME_TO_ACT = {v: k for k, v in ACTIONS.items()}


class Ep:
    def __init__(self, seed: int, shadow_bot: bool):
        self.seed = seed
        self.env = gym.make(ENV_ID)
        self.obs, _ = self.env.reset(seed=seed)
        u = self.env.unwrapped
        d = u.instrs.desc
        self.target = {"type": d.type, "color": d.color}
        self.n_matching = len(d.obj_poss)
        self.bot = BabyAIBot(u) if shadow_bot else None
        self.last_act = None
        self.done = False
        self.success = self.timeout = False
        self.steps = []  # (text, model_choice, bot_choice)
        self.blocked = 0
        self.end_front = None
        cat = categorize({"image": self.obs["image"], "target": self.target, "n_matching": self.n_matching})
        self.visible_at_start = not cat["target_unseen"]

    def text(self) -> str:
        return obs_to_text(self.obs["image"], self.obs["direction"])

    def bot_suggest(self):
        try:
            return int(self.bot.replan(self.last_act))
        except Exception as e:  # noqa: BLE001 — record, do not crash the run
            return f"bot_error:{type(e).__name__}"

    def step(self, act: int, model_choice=None, bot_choice=None):
        u = self.env.unwrapped
        pos = tuple(u.agent_pos)
        self.steps.append({"text": self.text(), "policy": model_choice or ACTIONS.get(act, act),
                           "bot": ACTIONS.get(bot_choice, bot_choice) if bot_choice is not None else None})
        self.obs, reward, term, trunc, _ = self.env.step(act)
        if act == 2 and tuple(u.agent_pos) == pos:
            self.blocked += 1
        self.last_act = act
        if term or trunc:
            self.done = True
            self.success = bool(term and reward > 0)
            self.timeout = bool(trunc and not term)
            front = u.grid.get(*u.front_pos)
            self.end_front = None if front is None else (front.type, front.color)
            self.env.close()

    def wrong_object(self) -> bool:
        if self.success or self.end_front is None or self.end_front[0] in ("wall", "door"):
            return False
        t = self.target
        return not (self.end_front[0] == t["type"] and (t["color"] is None or self.end_front[1] == t["color"]))


def run(policy: str, seeds, model=None, mask=False):
    eps = [Ep(s, shadow_bot=policy in ("model", "bot")) for s in seeds]
    rngs = {e.seed: random.Random(e.seed) for e in eps}
    chooser = None
    if policy == "model":
        from probe.laya_model import Chooser
        chooser = Chooser(model)
    while True:
        live = [e for e in eps if not e.done]
        if not live:
            break
        if policy == "model":
            picks = chooser.choose_batch([e.text() for e in live], [e.obs["mission"] for e in live], mask_mission=mask)
            for e, (c, _) in zip(live, picks):
                e.step(NAME_TO_ACT[c], model_choice=c, bot_choice=e.bot_suggest())
        elif policy == "bot":
            for e in live:
                e.step(e.bot_suggest())
        elif policy == "random":
            for e in live:
                e.step(rngs[e.seed].choice([0, 1, 2]))
        elif policy == "forward":
            for e in live:
                e.step(2)
    return eps


def loop_kind(e: "Ep", k: int = 10) -> str:
    """How a timed-out episode spent its last k steps.
    stuck  = one (text, choice) repeated (e.g. forward into a wall/object)
    cycle  = 2-4 distinct (text, choice) repeating (e.g. left/right oscillation)
    wander = more variety than that."""
    tail = {(s["text"], s["policy"]) for s in e.steps[-k:]}
    return "stuck" if len(tail) == 1 else "cycle" if len(tail) <= 4 else "wander"


def summarize(eps, policy, name):
    def rate(sub):
        return {"n": len(sub), "success": sum(e.success for e in sub),
                "rate": round(sum(e.success for e in sub) / max(len(sub), 1), 4)}
    fails = [e for e in eps if not e.success]
    steps = sum(len(e.steps) for e in eps)
    res = {"name": name, "policy": policy, "episodes": len(eps), "all": rate(eps),
           "target_visible_at_start": rate([e for e in eps if e.visible_at_start]),
           "target_unseen_at_start": rate([e for e in eps if not e.visible_at_start]),
           "two_matching": rate([e for e in eps if e.n_matching >= 2]),
           "one_matching": rate([e for e in eps if e.n_matching == 1]),
           "timeouts": sum(e.timeout for e in eps),
           "wrong_object_at_end": sum(e.wrong_object() for e in fails),
           "mean_steps_success": round(float(np.mean([len(e.steps) for e in eps if e.success] or [0])), 2),
           "blocked_forward_share": round(sum(e.blocked for e in eps) / max(steps, 1), 4),
           "actions": dict(collections.Counter(s["policy"] for e in eps for s in e.steps))}
    res["timeout_kinds"] = dict(collections.Counter(loop_kind(e) for e in eps if e.timeout))
    if eps and eps[0].bot is not None and policy == "model":
        pairs = [(s["policy"], s["bot"]) for e in eps for s in e.steps if s["bot"] in CHOICES]
        res["shadow_bot_agree"] = round(sum(p == b for p, b in pairs) / max(len(pairs), 1), 4)
        # Failed episodes repeat one stuck step dozens of times; agreement on successes is the fairer view.
        ok = [(s["policy"], s["bot"]) for e in eps if e.success for s in e.steps if s["bot"] in CHOICES]
        res["shadow_bot_agree_success_eps"] = round(sum(p == b for p, b in ok) / max(len(ok), 1), 4)
    return res


def pick_failures(eps, k=5):
    fails = [e for e in eps if not e.success]
    buckets = [
        ("timeout, target unseen at start", [e for e in fails if e.timeout and not e.visible_at_start]),
        ("timeout, target visible at start", [e for e in fails if e.timeout and e.visible_at_start]),
        ("ended facing a wrong object", [e for e in fails if e.wrong_object()]),
        ("two matching objects", [e for e in fails if e.n_matching >= 2]),
    ]
    out, used = [], set()
    for label, pool in buckets:
        for e in pool:
            if e.seed not in used:
                out.append((label, e)); used.add(e.seed); break
    for e in fails:
        if len(out) >= k:
            break
        if e.seed not in used:
            out.append(("other failure", e)); used.add(e.seed)
    return [{"why": label, "seed": e.seed, "mission": e.obs["mission"], "n_matching": e.n_matching,
             "visible_at_start": e.visible_at_start, "timeout": e.timeout, "end_front": e.end_front,
             "steps_total": len(e.steps), "steps": e.steps[:16]} for label, e in out[:k]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True, choices=["random", "forward", "bot", "model"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--mask", action="store_true", help="replace the mission with a fixed '(hidden)'")
    ap.add_argument("--name", required=True)
    ap.add_argument("--seeds", default="10000-10299")
    a = ap.parse_args()
    eps = run(a.policy, list(seed_range(a.seeds)), a.model, a.mask)
    res = summarize(eps, a.policy, a.name)
    res["mask_mission"] = a.mask
    res["model"] = a.model
    pathlib.Path("reports/stage3").mkdir(parents=True, exist_ok=True)
    pathlib.Path(f"reports/stage3/{a.name}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    if a.policy == "model":
        pathlib.Path(f"reports/stage3/{a.name}_failures.json").write_text(
            json.dumps(pick_failures(eps), indent=1, default=str), encoding="utf-8")
    print(json.dumps(res))


if __name__ == "__main__":
    main()
