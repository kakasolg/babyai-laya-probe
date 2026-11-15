"""Closed loop on the dev eval seeds. The policy walks; the env decides success.

Usage:
  python -m probe.closed_loop --policy random|forward|bot --name <tag>
  python -m probe.closed_loop --policy model --model <ckpt> --name <tag> [--mask] [--escape] [--swap]
  [--seeds 10000-10299]   (dev seeds; 20000-20299 are reserved for the final check — do not use)

All episodes run in lockstep, so a model policy is one batched forward pass per step.
For model policies a shadow bot (replan(action_taken=last action)) records what the bot would do.

Counted per policy:
  success, success_within_2x_bot (steps <= 2 x the bot's own steps on the same episode),
  split by "target visible at step 0", timeouts, failure classes A/B/C (see classify()).

--escape (stage 3.5, evaluation-only, rule fixed before running):
  if the previous action was forward and the text now equals the text before it (= did not move),
  drop forward and take the higher-scoring of the other two; otherwise keep the model's choice.
--swap (stage 3.5): replace the instruction with another object in the room. Only episodes where the
  original target and the new one are each unique in colour+type; the env judges the new instruction.
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
from minigrid.envs.babyai.core.verifier import GoToInstr, ObjDesc
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.dump_demos import guarded_seeds
from probe.obs_text import ACTIONS, CHOICES, obs_to_text
from probe.text_stats import categorize

ENV_ID = "BabyAI-GoToLocal-v0"
NAME_TO_ACT = {v: k for k, v in ACTIONS.items()}


def room_objects(u):
    return [o for o in u.grid.grid if o is not None and o.type not in ("wall", "door")]


def swap_target(u):
    """(type, color) of a different object that is unique in the room, or None. Original must be unique too."""
    d = u.instrs.desc
    if len(d.obj_poss) != 1:
        return None
    count = collections.Counter((o.type, o.color) for o in room_objects(u))
    objs = sorted(room_objects(u), key=lambda o: (o.cur_pos[1], o.cur_pos[0]))  # grid scan order
    for o in objs:
        key = (o.type, o.color)
        if count[key] == 1 and key != (d.type, d.color):
            return key
    return None


def make_env(seed: int, swap: bool):
    env = gym.make(ENV_ID)
    obs, _ = env.reset(seed=seed)
    u = env.unwrapped
    orig = None
    if swap:
        new = swap_target(u)
        if new is None:
            env.close()
            return None
        orig = {"type": u.instrs.desc.type, "color": u.instrs.desc.color, "pos": tuple(u.instrs.desc.obj_poss[0])}
        instr = GoToInstr(ObjDesc(new[0], new[1]))
        instr.reset_verifier(u)
        u.instrs = instr
        u.mission = instr.surface(u)
        obs["mission"] = u.mission
    return env, obs, orig


def bot_steps(seed: int, swap: bool) -> int:
    env, obs, _ = make_env(seed, swap)
    bot = BabyAIBot(env.unwrapped)
    n, done, last = 0, False, None
    while not done:
        a = int(bot.replan(last))
        _, _, term, trunc, _ = env.step(a)
        last, n, done = a, n + 1, term or trunc
    env.close()
    return n


class SkipEp(Exception):
    pass


class Ep:
    def __init__(self, seed: int, shadow_bot: bool, swap: bool):
        self.seed = seed
        made = make_env(seed, swap)
        if made is None:
            raise SkipEp(seed)
        self.env, self.obs, self.orig = made
        u = self.env.unwrapped
        d = u.instrs.desc
        self.target = {"type": d.type, "color": d.color}
        self.n_matching = len(d.obj_poss)
        self.bot = BabyAIBot(u) if shadow_bot else None
        self.last_act = None
        self.prev_text = None  # text before the last action
        self.done = self.success = self.timeout = False
        self.steps = []
        self.interventions = 0
        self.faced_orig = False
        self.visible_at_start = self.target_visible()
        self.bot_n = bot_steps(seed, swap)

    def text(self) -> str:
        return obs_to_text(self.obs["image"], self.obs["direction"])

    def target_visible(self) -> bool:
        return not categorize({"image": self.obs["image"], "target": self.target,
                               "n_matching": self.n_matching})["target_unseen"]

    def stuck_after_forward(self) -> bool:
        return self.last_act == 2 and self.prev_text is not None and self.text() == self.prev_text

    def bot_suggest(self):
        try:
            return int(self.bot.replan(self.last_act))
        except Exception as e:  # noqa: BLE001
            return f"bot_error:{type(e).__name__}"

    def step(self, act: int, choice=None, bot_choice=None, intervened=False):
        u = self.env.unwrapped
        pos = tuple(int(x) for x in u.agent_pos)
        text = self.text()
        self.steps.append({"text": text, "policy": choice or ACTIONS.get(act, act), "intervened": intervened,
                           "bot": ACTIONS.get(bot_choice, bot_choice) if bot_choice is not None else None,
                           "target_visible": self.target_visible(), "pos": pos, "dir": int(u.agent_dir)})
        self.prev_text = text
        self.obs, reward, term, trunc, _ = self.env.step(act)
        self.steps[-1]["moved"] = tuple(int(x) for x in u.agent_pos) != pos
        if self.orig is not None and tuple(int(x) for x in u.front_pos) == self.orig["pos"]:
            self.faced_orig = True
        self.last_act = act
        if term or trunc:
            self.done = True
            self.success = bool(term and reward > 0)
            self.timeout = bool(trunc and not term)
            self.env.close()


def find_loop(seq):
    """(start, period) of the terminal repetition of `seq`, period <= 4, repeated at least twice; else None."""
    n, best = len(seq), None
    for p in range(1, 5):
        t = n - p
        while t - 1 >= 0 and t - 1 + p < n and seq[t - 1] == seq[t - 1 + p]:
            t -= 1
        if n - t >= 2 * p and (best is None or t < best[0]):
            best = (t, p)
    return best


def classify(e: Ep) -> dict:
    """Failure classes (rules fixed before looking at stage-3.5 results):
    A  judgeable from the current input: inside the loop the agent chose forward and did not move
       (a blocker is shown as `1 ahead`), or a matching object is visible in every loop state.
    B  searching while the target is not visible (memory shortfall possible, not asserted): no matching object is visible in any loop state (and not A).
       sub: target seen earlier in the episode, or never seen.
    C  the rest (target visible in some loop states, no blocked forward)."""
    seq = [(s["text"], s["policy"]) for s in e.steps]
    lp = find_loop(seq)
    start, period = lp if lp else (max(len(seq) - 10, 0), None)
    loop = e.steps[start:]
    blocked = any(s["policy"] == "forward" and not s["moved"] for s in loop)
    vis = [s["target_visible"] for s in loop]
    if blocked or all(vis):
        cls, why = "A", "blocked forward" if blocked else "target visible in every loop state"
    elif not any(vis):
        seen_before = any(s["target_visible"] for s in e.steps[:start])
        cls, why = "B", "target seen earlier, lost" if seen_before else "target never seen"
    else:
        cls, why = "C", "target visible in some loop states"
    s0 = e.steps[start]
    return {"seed": e.seed, "class": cls, "why": why, "loop_start": start, "period": period,
            "loop_start_text": s0["text"], "loop_start_choice": s0["policy"], "loop_start_bot": s0["bot"],
            "mission": e.obs["mission"]}


def run(policy: str, seeds, model=None, mask=False, escape=False, swap=False):
    eps, skipped = [], []
    for s in seeds:
        try:
            eps.append(Ep(s, shadow_bot=policy in ("model", "bot"), swap=swap))
        except SkipEp:  # swap not possible for this episode
            skipped.append(s)
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
            for e, (c, probs) in zip(live, picks):
                intervened = False
                if escape and c == "forward" and e.stuck_after_forward():
                    c = max(("turn left", "turn right"), key=lambda k: probs.get(k, 0.0))
                    intervened = True
                    e.interventions += 1
                e.step(NAME_TO_ACT[c], choice=c, bot_choice=e.bot_suggest(), intervened=intervened)
        elif policy == "bot":
            for e in live:
                e.step(e.bot_suggest())
        elif policy == "random":
            for e in live:
                e.step(rngs[e.seed].choice([0, 1, 2]))
        elif policy == "forward":
            for e in live:
                e.step(2)
    return eps, skipped


def rate(sub):
    n = len(sub)
    ok = sum(e.success for e in sub)
    ok2 = sum(e.success and len(e.steps) <= 2 * e.bot_n for e in sub)
    return {"n": n, "success": ok, "rate": round(ok / max(n, 1), 4),
            "within_2x_bot": ok2, "rate_2x": round(ok2 / max(n, 1), 4)}


def summarize(eps, policy, name, skipped):
    fails = [e for e in eps if not e.success]
    steps = sum(len(e.steps) for e in eps)
    res = {"name": name, "policy": policy, "episodes": len(eps), "skipped": skipped, "all": rate(eps),
           "target_visible_at_start": rate([e for e in eps if e.visible_at_start]),
           "target_unseen_at_start": rate([e for e in eps if not e.visible_at_start]),
           "two_matching": rate([e for e in eps if e.n_matching >= 2]),
           "one_matching": rate([e for e in eps if e.n_matching == 1]),
           "timeouts": sum(e.timeout for e in eps),
           "mean_steps_success": round(float(np.mean([len(e.steps) for e in eps if e.success] or [0])), 2),
           "blocked_forward_share": round(sum(s["policy"] == "forward" and not s["moved"]
                                              for e in eps for s in e.steps) / max(steps, 1), 4),
           "actions": dict(collections.Counter(s["policy"] for e in eps for s in e.steps)),
           "per_episode": {e.seed: [int(e.success), len(e.steps), e.bot_n] for e in eps}}
    if policy == "model":
        cls = [classify(e) for e in fails]
        res["failure_classes"] = dict(collections.Counter(c["class"] for c in cls))
        res["failure_whys"] = dict(collections.Counter(f"{c['class']}: {c['why']}" for c in cls))
        res["failures"] = cls
        pairs = [(s["policy"], s["bot"]) for e in eps for s in e.steps if s["bot"] in CHOICES]
        res["shadow_bot_agree"] = round(sum(p == b for p, b in pairs) / max(len(pairs), 1), 4)
        ok = [(s["policy"], s["bot"]) for e in eps if e.success for s in e.steps if s["bot"] in CHOICES]
        res["shadow_bot_agree_success_eps"] = round(sum(p == b for p, b in ok) / max(len(ok), 1), 4)
        res["interventions"] = sum(e.interventions for e in eps)
        res["episodes_with_intervention"] = sum(e.interventions > 0 for e in eps)
        if eps and eps[0].orig is not None:
            res["swap"] = {"faced_original_target_some_step": sum(e.faced_orig for e in eps),
                           "failed_and_faced_original": sum(e.faced_orig for e in fails),
                           "success_and_faced_original_first": sum(e.faced_orig for e in eps if e.success)}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True, choices=["random", "forward", "bot", "model"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--mask", action="store_true", help="replace the mission with a fixed '(hidden)'")
    ap.add_argument("--escape", action="store_true", help="blocked-forward escape (evaluation-only)")
    ap.add_argument("--swap", action="store_true", help="swap the instruction to another unique object")
    ap.add_argument("--name", required=True)
    ap.add_argument("--seeds", default="10000-10299")
    ap.add_argument("--use-final-seeds", action="store_true", help="stage 6 only: allow 20000-20299")
    ap.add_argument("--out", default="reports/stage3_5")
    a = ap.parse_args()
    seeds = list(guarded_seeds(a.seeds, a.use_final_seeds))
    eps, skipped = run(a.policy, seeds, a.model, a.mask, a.escape, a.swap)
    res = summarize(eps, a.policy, a.name, skipped)
    res.update({"mask_mission": a.mask, "escape": a.escape, "swap": a.swap if not res.get("swap") else res["swap"],
                "model": a.model})
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.name}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    brief = {k: res[k] for k in ("all", "target_visible_at_start", "target_unseen_at_start", "timeouts") if k in res}
    for k in ("failure_classes", "interventions", "episodes_with_intervention", "swap", "skipped"):
        if k in res and k != "skipped":
            brief[k] = res[k]
    brief["skipped_n"] = len(skipped)
    print(a.name, json.dumps(brief, default=str))


if __name__ == "__main__":
    main()
