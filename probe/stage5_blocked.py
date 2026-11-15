"""Stage 5 supplement (board 11-14 21:09): on steps whose cell ahead is blocked, how often is rank 1 'forward'?

Blocked step = the state text has an object line that is exactly "1 ahead" (no left/right part) or a walls line
containing "1 ahead". Counted on two sets of steps per scorer:
  loop - the no-rule closed loop (300 dev seeds), replayed deterministically and checked against the saved
         reports/stage5/<name>.json episode by episode (end and step count must match);
  bot  - the 1,567 steps the bot walked on the same seeds (data/gotolocal_eval.jsonl), options in the fixed order.
Jev/Gemma are served from the response cache only; a cache miss stops the script (no new API calls).

Usage (WSL, repo root): python -m probe.stage5_blocked
"""
from __future__ import annotations

import json
import os

from probe import stage5
from probe.laya_rows import state_text
from probe.obs_text import CHOICES

RUNS = [("laya-s0", "laya", "~/babyai-laya-ft/gotolocal-s0"), ("laya-s1", "laya", "~/babyai-laya-ft/gotolocal-s1"),
        ("laya-s2", "laya", "~/babyai-laya-ft/gotolocal-s2"), ("jev", "jev", None), ("gemma", "gemma", None)]


def blocked_ahead(text: str) -> bool:
    for line in text.splitlines():
        name, _, rest = line.partition(": ")
        parts = [p.strip() for p in rest.split(",")]
        if name == "walls" and "1 ahead" in parts:
            return True
        if name not in ("walls", "facing", "objects", "mission") and parts == ["1 ahead"]:
            return True
    return False


def cache_only(sc):
    def miss(*_a, **_k):
        raise SystemExit(f"cache miss for {sc.model}: refusing a new call")
    sc.call = miss
    return sc


def share(rows):
    n = len(rows)
    f = sum(r == "forward" for r in rows)
    return {"blocked_steps": n, "rank1_forward": f, "rate": round(f / n, 4) if n else None}


def main() -> None:
    if not os.environ.get("JEV_MODEL"):
        os.environ["JEV_MODEL"] = stage5.JEV_MODEL = "jev-1.14.0"
    bot_rows = [json.loads(l) for l in open("data/gotolocal_eval.jsonl", encoding="utf-8")]
    bot_rows = [r for r in bot_rows if r["action_name"] in CHOICES and blocked_ahead(r["text"])]
    out = {"definition": __doc__.split("\n\n")[1], "bot_blocked_steps_total": len(bot_rows), "runs": {}}
    for name, kind, model in RUNS:
        sc = stage5.make_scorer(kind, model and os.path.expanduser(model))
        if kind != "laya":
            cache_only(sc)
        eps, aborted = stage5.run_loop(sc, "none")
        saved = json.load(open(f"reports/stage5/{name}.json", encoding="utf-8"))["per_episode"]
        mism = [e.seed for e in eps
                if (saved[str(e.seed)]["end"], saved[str(e.seed)]["steps"]) !=
                ("success" if e.success else "timeout" if e.timeout else "other", len(e.steps))]
        loop = [s["top"] for e in eps for s in e.steps if blocked_ahead(s["text"])]
        bscore = sc.score([state_text(r["text"], r["mission"]) for r in bot_rows], CHOICES)
        bot = [stage5.ranked(b.get("probs") or {})[0] for b in bscore]
        out["runs"][name] = {"loop_no_rule": share(loop), "loop_replay_mismatch_episodes": mism, "aborted": aborted,
                             "bot_trajectory": share(bot)}
        print(name, json.dumps(out["runs"][name]), flush=True)
    stage5.OUT.joinpath("blocked_forward.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
