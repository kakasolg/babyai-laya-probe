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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stepcheck", "loop"])
    ap.add_argument("--seeds", default="10000-10099")
    ap.add_argument("--tier", choices=["device", "pcc"], default="device")
    ap.add_argument("--app", default=APP)
    ap.add_argument("--eval", default="data/gotolocal_eval.jsonl")
    a = ap.parse_args()
    a.scorer, a.input = "afm", "text"
    if a.cmd == "loop":
        return cmd_loop(a)
    stage12.OUT = pathlib.Path("reports/stage13")
    stage12.make = lambda scorer, mode: AfmScorer(a.tier, a.app)
    stage12.tag = lambda _a: f"afm-{a.tier}"
    stage12.cmd_stepcheck(a)


if __name__ == "__main__":
    main()
