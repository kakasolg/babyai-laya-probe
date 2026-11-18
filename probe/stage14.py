"""Stage 14 (reports/stage14_prereg.md): rule variants V0-V7 on existing checkpoints, no training.

Usage (WSL, repo root, PY=~/babyai-laya-venv/bin/python, HF_HUB_OFFLINE=1):
  $PY -m probe.stage14 run --task gotolocal --ckpt gotolocal-s0      # all variants for one checkpoint
  $PY -m probe.stage14 run --task putnext --ckpt putnext-s0

`Rule` holds the whole rule definition and needs neither laya nor the environment, so the same variants can be
run on other policies (the small CNN on the board).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import random

OUT = pathlib.Path("reports/stage14")
DEV = "10000-10299"
# (variant, random seed) in run order; V0 first because every other run is compared with it
RUNS = [("V0", None), ("V1", None), ("V2", 0), ("V2", 1), ("V2", 2), ("V3", None), ("V4", None), ("V5", None),
        ("V6", None), ("V7", 0), ("V7", 1), ("V7", 2)]
EPS_V7 = 0.1
MEM_V5 = 8


class Rule:
    """One episode's rule state. choose(order, key, choices) -> (action, rule_triggered).

    order: the model's choices, best first (ties already in the fixed option order).
    key: the observation text (V6: the true agent state). A rule is 'triggered' when the key was seen before
    in this episode (V3: when it equals the previous step's key; V5: when it is in the last 8 steps)."""

    def __init__(self, variant: str, rng: random.Random | None = None):
        self.v, self.rng = variant, rng
        self.tried: dict = {}          # V1 V2 V4 V6: key -> actions tried
        self.full: set = set()         # V4: keys where every action was tried
        self.run_key, self.run_tried = None, set()  # V3
        self.hist = collections.deque(maxlen=MEM_V5)  # V5: (key, action) of the last 8 steps
        self.resets = self.exhausted = 0

    def choose(self, order: list[str], key, choices: list[str]):
        v = self.v
        if v == "V0":
            return order[0], False
        if v == "V7":
            if self.rng.random() < EPS_V7:
                return self.rng.choice(choices), False
            return order[0], False
        if v in ("V1", "V2", "V6"):
            trig = key in self.tried
            tr = self.tried.setdefault(key, set())
            left = [o for o in order if o not in tr]
            if not left:
                tr.clear()
                self.resets += 1
                c = order[0]
            elif v == "V2" and trig:
                c = self.rng.choice(left)
            else:
                c = left[0]
            tr.add(c)
            return c, trig
        if v == "V3":
            trig = key == self.run_key
            if not trig:
                self.run_key, self.run_tried = key, set()
            left = [o for o in order if o not in self.run_tried]
            if not left:
                self.run_tried.clear()
                self.resets += 1
                c = order[0]
            else:
                c = left[0]
            self.run_tried.add(c)
            return c, trig
        if v == "V4":
            trig = key in self.tried
            if key in self.full:
                return order[0], trig
            tr = self.tried.setdefault(key, set())
            left = [o for o in order if o not in tr]
            if not left:
                self.full.add(key)
                self.exhausted += 1
                return order[0], trig
            c = left[0]
            tr.add(c)
            return c, trig
        if v == "V5":
            tr = {a for k, a in self.hist if k == key}
            trig = bool(tr)
            left = [o for o in order if o not in tr]
            if not left:
                self.hist = collections.deque(((k, a) for k, a in self.hist if k != key), maxlen=MEM_V5)
                self.resets += 1
                c = order[0]
            else:
                c = left[0]
            self.hist.append((key, c))
            return c, trig
        raise ValueError(v)


# ---------------------------------------------------------------- environment side

def true_state(u):
    """(agent key, full state): agent key = (x, y, dir, carried object); full adds the object layout."""
    car = (u.carrying.type, u.carrying.color) if u.carrying is not None else None
    agent = (int(u.agent_pos[0]), int(u.agent_pos[1]), int(u.agent_dir), car)
    return agent, (agent, u.grid.encode().tobytes())


class Task:
    def __init__(self, task: str, path: str):
        self.task = task
        if task == "gotolocal":
            from probe.dump_demos import guarded_seeds
            from probe.obs_text import CHOICES
            from probe.stage5 import LayaScorer
            self.scorer, self.choices, self.seeds = LayaScorer(path), list(CHOICES), list(guarded_seeds(DEV))
        else:
            import probe.stage10 as s10
            self.scorer, self.choices, self.seeds = s10.Scorer(path), list(s10.CH), list(s10.seeds_of(DEV))
            self.bot_n = {s: len(s10.bot_episode(s)[0]) for s in self.seeds}

    def new_eps(self):
        if self.task == "gotolocal":
            from probe.closed_loop import Ep
            return [Ep(s, shadow_bot=False, swap=False) for s in self.seeds]
        import probe.stage10 as s10
        return [s10.Ep(s, self.bot_n[s], True) for s in self.seeds]

    def score(self, eps):
        from probe.laya_rows import state_text
        states = [state_text(e.text(), e.obs["mission"]) for e in eps]
        if self.task == "gotolocal":
            sc = self.scorer.score(states)
            return [s.get("probs") or {} for s in sc], [bool(s.get("format_error")) for s in sc]
        return self.scorer(states), [False] * len(eps)

    def ranked(self, p):
        return sorted(self.choices, key=lambda c: -p.get(c, 0.0))  # stable: ties keep the fixed option order

    def step(self, e, c, top, interv, p, fmt):
        if self.task == "gotolocal":
            from probe.closed_loop import NAME_TO_ACT
            e.step(NAME_TO_ACT[c], choice=c, intervened=interv)
            e.steps[-1].update({"probs": p, "top": top, "top_p": p.get(top), "format_error": fmt})
        else:
            import probe.stage10 as s10
            e.step(s10.NAME_TO_ACT[c], c, top, interv, p)

    def env(self, e):
        return e.env.unwrapped if self.task == "gotolocal" else e.u

    def success(self, e) -> bool:
        return e.success if self.task == "gotolocal" else e.end == "success"


def run(t: Task, variant: str, rseed):
    eps = t.new_eps()
    for e in eps:
        rng = random.Random(f"{variant}|r{rseed}|{e.seed}") if variant in ("V2", "V7") else None
        e.rule = Rule(variant, rng)
        e.n_interv, e.resets, e.gave_up, e.triggers = 0, 0, False, 0
        e.vis_full, e.vis_agent = set(), set()
        e.occ = collections.Counter()
    while True:
        live = [e for e in eps if not e.done]
        if not live:
            break
        probs, fmts = t.score(live)
        for e, p, fmt in zip(live, probs, fmts):
            order = t.ranked(p)
            agent, full = true_state(t.env(e))
            key = agent if variant == "V6" else e.text()
            c, trig = e.rule.choose(order, key, t.choices)
            interv = c != order[0]
            e.n_interv += interv
            e.triggers += trig
            if variant == "V1" and trig:
                if full not in e.vis_full:
                    e.occ["agent" if agent not in e.vis_agent else "layout_only"] += 1
                    e.occ["interventions"] += interv
                e.occ["interventions_all"] += interv
            e.vis_full.add(full)
            e.vis_agent.add(agent)
            t.step(e, c, order[0], interv, p, fmt)
    for e in eps:
        e.resets = e.rule.resets
    return eps


def summarize(t: Task, eps, name, variant, rseed, base):
    policy = "none" if variant == "V0" else variant
    if t.task == "gotolocal":
        from probe.stage5 import summarize as s5
        res = s5(eps, name, t.scorer, policy, None, base)
        res.pop("trace", None)
    else:
        import probe.stage10 as s10
        res = s10.summarize(eps, name, policy, base)
    res["variant"], res["rng_seed"], res["seeds"] = variant, rseed, DEV
    res["interventions"] = sum(e.n_interv for e in eps)
    res["interventions_per_episode"] = round(res["interventions"] / len(eps), 3)
    res["episodes_with_intervention"] = sum(e.n_interv > 0 for e in eps)
    res["rule_triggered_steps"] = sum(e.triggers for e in eps)
    res["resets"] = sum(e.resets for e in eps)
    res["v4_keys_exhausted"] = sum(e.rule.exhausted for e in eps)
    res["steps_total"] = sum(len(e.steps) for e in eps)
    for k, e in zip(res["per_episode"], eps):
        res["per_episode"][k].update({"interventions": e.n_interv, "triggers": e.triggers})
    if variant == "V1":
        b = {int(k): v["end"] == "success" for k, v in base["per_episode"].items()}
        occ_eps = [e for e in eps if e.occ["agent"] + e.occ["layout_only"] > 0]
        res["occlusion"] = {
            "rule_triggered_steps": res["rule_triggered_steps"],
            "occluded_steps": sum(e.occ["agent"] + e.occ["layout_only"] for e in eps),
            "occluded_steps_agent_state_new": sum(e.occ["agent"] for e in eps),
            "occluded_steps_layout_only": sum(e.occ["layout_only"] for e in eps),
            "occluded_interventions": sum(e.occ["interventions"] for e in eps),
            "interventions_on_triggered_steps": sum(e.occ["interventions_all"] for e in eps),
            "episodes_with_occlusion": len(occ_eps),
            "those_episodes": {
                "success": sum(t.success(e) for e in occ_eps),
                "fail": sum(not t.success(e) for e in occ_eps),
                "saved_vs_V0": sorted(e.seed for e in occ_eps if t.success(e) and not b[e.seed]),
                "broken_vs_V0": sorted(e.seed for e in occ_eps if not t.success(e) and b[e.seed]),
                "same_as_V0": sum(t.success(e) == b[e.seed] for e in occ_eps)}}
        for k, e in zip(res["per_episode"], eps):
            res["per_episode"][k]["occluded_steps"] = e.occ["agent"] + e.occ["layout_only"]
    return res


def cmd_run(a):
    from probe.laya_model import FT_ROOT
    path = os.path.join(FT_ROOT, a.ckpt)
    assert os.path.isdir(path), path
    t = Task(a.task, path)
    if a.limit:  # smoke test only, writes to --out
        t.seeds = t.seeds[:a.limit]
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = None
    for variant, rseed in RUNS:
        tag = f"{a.ckpt}-{variant}" + ("" if rseed is None else f"-r{rseed}")
        eps = run(t, variant, rseed)
        res = summarize(t, eps, tag, variant, rseed, base)
        res["model"] = f"babyai-laya-ft/{a.ckpt}"
        (out / f"{tag}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        if variant == "V0":
            base = res
        vs = res.get("vs_no_rule") or {}
        print(json.dumps({"name": tag, "all": {k: res["all"][k] for k in ("success", "within_2x_bot")},
                          "timeout": res["timeout"], "interventions": res["interventions"],
                          "saved": len(vs.get("saved", [])), "broken": len(vs.get("broken", []))}
                         | ({"occlusion": {k: v for k, v in res["occlusion"].items() if k != "those_episodes"}}
                            if variant == "V1" else {})), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--task", choices=["gotolocal", "putnext"], required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    cmd_run(a)


if __name__ == "__main__":
    main()
