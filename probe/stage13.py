"""Stage 13: Apple Foundation Models (on-device or PCC) as an untrained reference on GoToLocal. Prereg:
reports/stage13_prereg.md. The model is reached through the signed Mac probe app of the Kortex repo
(`KortexProbeApp --run "babyai --tier device"`), one JSON line per request on stdin/stdout.

  python -m probe.stage13 stepcheck [--tier device|pcc] [--app <path to KortexProbeApp binary>]
  python -m probe.stage13 loop --seeds 10000-10099 [--tier device|pcc]     (no rule; per-step log in data/)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import threading
import time

from probe import stage5, stage12
from probe.obs_text import CHOICES

EXPLAIN = stage5.EXPLAIN
APP = os.environ.get(
    "KORTEX_PROBE_APP",
    "/Volumes/EXA/devel/Kortex/probe/.build/xcode/Build/Products/Debug/KortexProbeApp.app/Contents/MacOS/KortexProbeApp")


class AfmScorer(stage5.CachedScorer):
    name = "afm"
    workers = 1  # one child process, one request at a time

    def __init__(self, tier: str, app: str):
        super().__init__(f"afm-{tier}")
        stage12._reload(self, f"data/stage13_cache_afm-{tier}.jsonl")
        self.tier, self.app = tier, app
        self.proc = None
        self.lock = threading.Lock()
        self.format_errors = 0
        self.n = 0

    def _start(self):
        self.proc = subprocess.Popen([self.app, "--run", f"babyai --tier {self.tier}"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        assert self._read().get("ready"), "probe app did not start"

    def _read(self) -> dict:
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("probe app closed")
            if line.startswith("@@"):
                return json.loads(line[2:])

    def _ask(self, state: str, options) -> dict:
        if self.proc is None or self.proc.poll() is not None:
            self._start()
        self.n += 1
        self.proc.stdin.write(json.dumps({"id": str(self.n), "instructions": EXPLAIN, "state": state,
                                          "options": list(options)}) + "\n")
        self.proc.stdin.flush()
        return self._read()

    def call(self, state: str, options) -> dict:
        with self.lock:
            t0 = time.time()
            d = self._ask(state, options)
            if "error" in d:
                self.errors += 1
                d = self._ask(state, options)
            if "error" in d and self.tier == "pcc":  # prereg 8: wait and retry, then stop the run (never invent an answer)
                for wait in (5, 30):
                    time.sleep(wait)
                    self.errors += 1
                    d = self._ask(state, options)
                    if "error" not in d:
                        break
                else:
                    raise stage5.ApiAborted(f"pcc failed after retries: {d.get('error')}")
            ms = (time.time() - t0) * 1000
            if d.get("choice") not in options:
                self.format_errors += 1
                return {"probs": {options[0]: 1.0}, "format_error": True, "error": d.get("error"), "ms": ms}
            return {"probs": {o: float(o == d["choice"]) for o in options}, "ms": ms,
                    "usage": {"input_tokens": d.get("in", 0), "output_tokens": d.get("out", 0)}}

    def stats(self):
        return super().stats() | {"format_errors_new_calls": self.format_errors}


def cmd_loop(a):
    from probe.dump_demos import guarded_seeds
    from probe.stage5_blocked import blocked_ahead
    sc = AfmScorer(a.tier, a.app)
    seeds = list(guarded_seeds(a.seeds))
    missions = {}

    def state(e):
        missions[e.seed] = e.obs["mission"]
        return stage5.state_text(e.text(), e.obs["mission"])

    eps, aborted = stage5.run_loop(sc, "none", seeds, state_fn=state)
    name = f"afm-{a.tier}-{len(seeds)}"
    res = stage5.summarize(eps, name, sc, "none", aborted)
    res["seeds"], res["tier"], res["called"] = a.seeds, a.tier, time.strftime("%Y-%m-%d")
    out = pathlib.Path("reports/stage13")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    with open(f"data/stage13_loop_afm-{a.tier}.jsonl", "w", encoding="utf-8") as f:
        for e in eps:
            for i, s in enumerate(e.steps):
                f.write(json.dumps({"seed": e.seed, "step": i, "mission": missions.get(e.seed), "text": s["text"],
                                    "action": s["policy"], "moved": s["moved"], "pos": s["pos"], "dir": s["dir"],
                                    "target_visible": s["target_visible"],
                                    "blocked": blocked_ahead(stage5.state_text(s["text"], missions.get(e.seed, ""))),
                                    "format_error": s["format_error"], "success": e.success, "bot_n": e.bot_n,
                                    "visible_at_start": e.visible_at_start}) + "\n")
    print(json.dumps({k: res[k] for k in ("name", "all", "timeout", "target_visible_at_start", "target_unseen_at_start",
                                           "blocked_forward_steps", "actions", "scorer_stats")}, default=str))


HELP_AT = (20, 40, 60)  # after this many steps without success, the next single action is the bot's


def _clone(env):
    import copy
    u = env.unwrapped
    saved = (getattr(u, "window", None), getattr(u, "clock", None))
    u.window, u.clock = None, None
    try:
        return copy.deepcopy(u)
    finally:
        u.window, u.clock = saved


def _bot_left(env):
    """Steps a fresh bot needs from this state with a fresh step budget; None if it fails."""
    from minigrid.utils.baby_ai_bot import BabyAIBot
    try:
        u = _clone(env)
        u.step_count = 0
        bot, n, last = BabyAIBot(u), 0, None
        while n < 64:
            act = int(bot.replan(last))
            _, r, term, trunc, _ = u.step(act)
            last, n = act, n + 1
            if term:
                return n if r > 0 else None
            if trunc:
                return None
    except Exception:  # noqa: BLE001
        return None
    return None


def _manhattan(env):
    u = env.unwrapped
    ax, ay = (int(v) for v in u.agent_pos)
    return min(abs(ax - int(x)) + abs(ay - int(y)) for x, y in u.instrs.desc.obj_poss)


def cmd_help(a):
    import statistics
    from minigrid.utils.baby_ai_bot import BabyAIBot
    from probe.closed_loop import NAME_TO_ACT, Ep
    from probe.dump_demos import guarded_seeds
    from probe.obs_text import ACTIONS
    sc = AfmScorer(a.tier, a.app)
    seeds = list(guarded_seeds(a.seeds))
    base = json.load(open(f"reports/stage13/afm-{a.tier}-{len(seeds)}.json", encoding="utf-8"))["per_episode"]
    rows, log = [], open(f"data/stage13_help_afm-{a.tier}.jsonl", "w", encoding="utf-8")
    for seed in seeds:
        e = Ep(seed, shadow_bot=False, swap=False)
        mission = e.obs["mission"]
        marks = [{"at": "start", "step": 0, "bot_left": _bot_left(e.env), "manhattan": _manhattan(e.env)}]
        helps, help_skipped, min_md = 0, 0, marks[0]["manhattan"]
        while not e.done:
            n = len(e.steps)
            helped = False
            if n in HELP_AT:
                marks.append({"at": f"before_help_{n}", "step": n, "bot_left": _bot_left(e.env), "manhattan": _manhattan(e.env)})
                try:
                    c = ACTIONS.get(int(BabyAIBot(_clone(e.env)).replan()))
                except Exception:  # noqa: BLE001
                    c = None
                if c in CHOICES:
                    helped, helps = True, helps + 1
                else:
                    help_skipped += 1
            if not helped:
                d = sc.score([stage5.state_text(e.text(), mission)])[0]
                c = stage5.ranked(d.get("probs") or {})[0]
            e.step(NAME_TO_ACT[c], choice=c, intervened=helped)
            if not e.done:
                min_md = min(min_md, _manhattan(e.env))
                if helped:
                    marks.append({"at": f"after_help_{n}", "step": n + 1, "bot_left": _bot_left(e.env),
                                  "manhattan": _manhattan(e.env), "help_action": c})
            s = e.steps[-1]
            log.write(json.dumps({"seed": seed, "step": n, "mission": mission, "text": s["text"], "action": c,
                                  "helped": helped, "moved": s["moved"], "pos": s["pos"], "dir": s["dir"],
                                  "target_visible": s["target_visible"]}) + "\n")
        end = {"at": "end", "step": len(e.steps)}
        if e.success:
            end.update({"bot_left": 0, "manhattan": 1})
            min_md = 1
        else:  # the env is closed but its state is still readable
            end.update({"bot_left": _bot_left(e.env), "manhattan": _manhattan(e.env)})
        marks.append(end)
        rows.append({"seed": seed, "success": e.success, "steps": len(e.steps), "bot_n": e.bot_n, "helps": helps,
                     "help_skipped": help_skipped, "visible_at_start": e.visible_at_start, "min_manhattan": min_md,
                     "no_help_success": base[str(seed)]["end"] == "success", "marks": marks})
    log.close()
    fail = [r for r in rows if not r["success"]]

    def med(xs):
        xs = [x for x in xs if x is not None]
        return statistics.median(xs) if xs else None

    res = {"name": f"help-afm-{a.tier}-{len(seeds)}", "seeds": a.seeds, "help_at": HELP_AT, "episodes": len(rows),
           "success": sum(r["success"] for r in rows), "no_help_success": sum(r["no_help_success"] for r in rows),
           "saved": sorted(r["seed"] for r in rows if r["success"] and not r["no_help_success"]),
           "broken": sorted(r["seed"] for r in rows if not r["success"] and r["no_help_success"]),
           "success_by_helps": {str(k): sum(r["success"] and r["helps"] == k for r in rows) for k in range(4)},
           "helps_total": sum(r["helps"] for r in rows), "help_skipped": sum(r["help_skipped"] for r in rows),
           "fail": {"n": len(fail),
                    "bot_left_start_median": med([r["marks"][0]["bot_left"] for r in fail]),
                    "bot_left_end_median": med([r["marks"][-1]["bot_left"] for r in fail]),
                    "manhattan_start_median": med([r["marks"][0]["manhattan"] for r in fail]),
                    "manhattan_end_median": med([r["marks"][-1]["manhattan"] for r in fail]),
                    "manhattan_min_median": med([r["min_manhattan"] for r in fail])},
           "scorer_stats": sc.stats(), "called": time.strftime("%Y-%m-%d"), "per_episode": rows}
    pathlib.Path(f"reports/stage13/{res['name']}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_episode",)}, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stepcheck", "loop", "help"])
    ap.add_argument("--seeds", default="10000-10099")
    ap.add_argument("--tier", choices=["device", "pcc"], default="device")
    ap.add_argument("--app", default=APP)
    ap.add_argument("--eval", default="data/gotolocal_eval.jsonl")
    a = ap.parse_args()
    a.scorer, a.input = "afm", "text"
    if a.cmd == "loop":
        return cmd_loop(a)
    if a.cmd == "help":
        return cmd_help(a)
    stage12.OUT = pathlib.Path("reports/stage13")
    stage12.make = lambda scorer, mode: AfmScorer(a.tier, a.app)
    stage12.tag = lambda _a: f"afm-{a.tier}"
    stage12.cmd_stepcheck(a)


if __name__ == "__main__":
    main()
