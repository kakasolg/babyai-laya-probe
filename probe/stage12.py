"""Stage 12 (reports/stage12_prereg.md): hosted / open decision models as reference lines on GoToLocal, untrained.
Gemini Decision 1 with text, image or text + image input, and local clef-flash (Ollama) with text input.

Usage (WSL, repo root):
  python -m probe.stage12 stepcheck --scorer clef|gemini [--input text|image|both]
  python -m probe.stage12 loop --scorer clef|gemini [--input ...] --policy none|reset
The Gemini key comes only from the environment variable GEMINI_API_KEY.
"""
from __future__ import annotations

import argparse
import base64
import collections
import io
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

from probe import stage5
from probe.dump_demos import guarded_seeds
from probe.laya_rows import state_text
from probe.obs_text import CHOICES
from probe.stage5_blocked import blocked_ahead
from probe.text_stats import categorize

OUT = pathlib.Path("reports/stage12")
EXPLAIN = stage5.EXPLAIN
IMAGE_PARA = ("The image is the agent's own limited forward view, 7 x 7 cells. The agent is the red triangle in the bottom row,\n"
              "middle column, and it always points up: up in the image is straight ahead, left in the image is the agent's left.\n"
              "Grey cells are walls. Coloured shapes are objects: a ball is a circle, a box is a square outline, a key is a key shape.\n"
              "Lit cells are in view; black cells are out of view or hidden behind a wall, so they are unknown, not empty.")
_TASK = EXPLAIN.split("Any matching object counts.")[0] + "Any matching object counts."
IMAGE_EXPLAIN = _TASK + "\n\n" + IMAGE_PARA
BOTH_EXPLAIN = EXPLAIN + "\n\n" + IMAGE_PARA
INSTR = {"text": EXPLAIN, "image": IMAGE_EXPLAIN, "both": BOTH_EXPLAIN}
GEMINI_MODEL = "gemini-decision-1"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
CLEF_MODEL = "clef-flash:latest"
COST_STOP_USD = 2.0
USD_PER_TOKEN = 0.10 / 1e6


def pov_png(image) -> str:
    """The agent's 7x7 view drawn like MiniGrid get_pov_render(32), as base64 PNG."""
    import numpy as np
    from minigrid.core.grid import Grid
    from PIL import Image
    g, vis = Grid.decode(np.asarray(image, dtype=np.uint8))
    img = g.render(32, agent_pos=(3, 6), agent_dir=3, highlight_mask=vis)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _reload(sc, path: str):
    sc.path = pathlib.Path(path)
    sc.path.parent.mkdir(parents=True, exist_ok=True)
    sc.cache = {}
    if sc.path.exists():
        for line in open(sc.path, encoding="utf-8"):
            d = json.loads(line)
            sc.cache[d["key"]] = d


def packed(text: str, mission: str, image, mode: str) -> str:
    """The 'state' string handed to the scorer (also its cache key)."""
    if mode == "text":
        return state_text(text, mission)
    return json.dumps({"mode": mode, "mission": mission, "text": text, "png": pov_png(image)})


class GeminiScorer(stage5.CachedScorer):
    name = "gemini"
    workers = 4

    def __init__(self, mode: str):
        self.mode = mode
        super().__init__(f"{GEMINI_MODEL}_{mode}")
        self.criteria_null = os.environ.get("STAGE12_CRITERIA", "null")  # null | empty | name (prereg fallback order)
        _reload(self, f"data/stage12_cache_{GEMINI_MODEL}_{mode}.jsonl")

    def key(self, state, options):
        import hashlib
        return hashlib.sha256(json.dumps([GEMINI_MODEL, INSTR[self.mode], state, list(options),
                                          self.criteria_null]).encode()).hexdigest()

    def body(self, state, options):
        crit = {o: (None if self.criteria_null == "null" else "" if self.criteria_null == "empty" else o) for o in options}
        if self.mode == "text":
            inp = [{"type": "text", "text": state}]
        else:
            d = json.loads(state)
            img = {"type": "image", "data": d["png"], "mime_type": "image/png", "resolution": "low"}
            txt = f"mission: {d['mission']}" if self.mode == "image" else state_text(d["text"], d["mission"])
            inp = [img, {"type": "text", "text": txt}]
        return {"model": GEMINI_MODEL, "input": inp,
                "questions": {"action": {"type": "choice", "instructions": INSTR[self.mode], "criteria": crit}}}

    def call(self, state, options):
        if self.usage["total_input_tokens"] * USD_PER_TOKEN > COST_STOP_USD:
            raise stage5.ApiAborted(f"cost stop: over ${COST_STOP_USD} in this run")
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SystemExit("GEMINI_API_KEY not set")
        data = json.dumps(self.body(state, list(options))).encode()
        for attempt in range(4):
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(GEMINI_URL, data=data, method="POST",
                                             headers={"x-goog-api-key": key, "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.loads(r.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code not in (429,) and e.code < 500:
                    raise stage5.ApiAborted(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}") from None
                self.errors += 1
            except (urllib.error.URLError, TimeoutError, OSError):
                self.errors += 1
            if attempt == 3:
                raise stage5.ApiAborted("transient errors x4")
            time.sleep(2 ** (attempt + 1))
        ms = (time.perf_counter() - t0) * 1000
        a = d["answers"]["action"]
        probs = a.get("probabilities") or {}
        bad = a.get("choice") not in options or not probs
        return {"probs": {o: float(probs.get(o, 0.0)) for o in options}, "format_error": bad,
                "raw_answer": {k: v for k, v in a.items() if k != "probabilities"},
                "usage": {k: v for k, v in (d.get("usage") or {}).items() if isinstance(v, (int, float))},
                "ms": round(ms, 1)}


class ClefScorer(stage5.CachedScorer):
    """Local clef-flash through Ollama /v1/systemone, the same request shape as Jev in stage 5."""
    name = "clef"
    workers = 1

    def __init__(self):
        super().__init__(CLEF_MODEL)
        _reload(self, "data/stage12_cache_clef-flash.jsonl")

    def call(self, state, options):
        q = {"action": {"type": "choice", "instructions": EXPLAIN, "criteria": {o: None for o in options}}}
        body = json.dumps({"model": CLEF_MODEL, "state": state, "questions": q, "keep_alive": "30m"}).encode()
        for attempt in range(3):
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(f"{stage5.OLLAMA}/v1/systemone", data=body,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    d = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    raise stage5.ApiAborted(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}") from None
                self.errors += 1
            except Exception:  # noqa: BLE001
                self.errors += 1
            if attempt == 2:
                raise stage5.ApiAborted("ollama x3")
            time.sleep(2 ** attempt)
        ms = (time.perf_counter() - t0) * 1000
        a = d["answers"]["action"]
        probs = a.get("probabilities") or {}
        bad = a.get("choice") not in options or not probs
        return {"probs": {o: float(probs.get(o, 0.0)) for o in options}, "format_error": bad,
                "raw_answer": {k: v for k, v in a.items() if k != "probabilities"}, "ms": round(ms, 1)}


def make(scorer: str, mode: str):
    if scorer == "clef":
        assert mode == "text", "clef-flash runs text only (prereg)"
        return ClefScorer()
    return GeminiScorer(mode)


def tag(a) -> str:
    return "clef-flash" if a.scorer == "clef" else f"gemini-{a.input}"


def cmd_stepcheck(a):
    sc = make(a.scorer, a.input)
    rows = [json.loads(l) for l in open(a.eval, encoding="utf-8")]
    rows = [r for r in rows if r["action_name"] in CHOICES]
    states = [packed(r["text"], r["mission"], r["image"], a.input) for r in rows]
    fwd = sc.score(states, CHOICES)
    rev = sc.score(states, list(reversed(CHOICES)))
    for r, x, y in zip(rows, fwd, rev):
        r["m"] = stage5.ranked(x.get("probs") or {})[0]
        r["r"] = max(reversed(CHOICES), key=lambda c: (y.get("probs") or {}).get(c, 0.0))
        r["fe"] = bool(x.get("format_error")) or bool(y.get("format_error"))
        r["unseen"] = categorize(r)["target_unseen"]
        r["blocked"] = blocked_ahead(state_text(r["text"], r["mission"]))

    def acc(sub):
        return {"n": len(sub), "agree": round(sum(r["m"] == r["action_name"] for r in sub) / max(len(sub), 1), 4)}

    blk = [r for r in rows if r["blocked"]]
    res = {"scorer": tag(a), "steps": len(rows), "all": acc(rows),
           "target_visible": acc([r for r in rows if not r["unseen"]]),
           "target_unseen": acc([r for r in rows if r["unseen"]]),
           "order_flip_rate": round(sum(r["m"] != r["r"] for r in rows) / len(rows), 4),
           "format_error_rate": round(sum(r["fe"] for r in rows) / len(rows), 4),
           "blocked_steps": len(blk),
           "blocked_forward_rank1": round(sum(r["m"] == "forward" for r in blk) / max(len(blk), 1), 4),
           "choice_share": dict(collections.Counter(r["m"] for r in rows)),
           "scorer_stats": sc.stats(), "called": time.strftime("%Y-%m-%d"),
           **({"criteria": sc.criteria_null} if a.scorer == "gemini" else {})}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"stepcheck-{tag(a)}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "scorer_stats"}), json.dumps(res["scorer_stats"]))


def cmd_loop(a):
    sc = make(a.scorer, a.input)
    seeds = list(guarded_seeds("10000-10299"))
    eps, aborted = stage5.run_loop(sc, a.policy, seeds,
                                   state_fn=lambda e: packed(e.text(), e.obs["mission"], e.obs["image"], a.input))
    name = tag(a) + ("" if a.policy == "none" else f"-{a.policy}")
    base_p = OUT / f"{tag(a)}.json"
    base = json.load(open(base_p, encoding="utf-8")) if a.policy != "none" else None
    res = stage5.summarize(eps, name, sc, a.policy, aborted, base)
    steps = [s for e in eps for s in e.steps]
    blk = [s for s in steps if blocked_ahead(s["text"])]
    res["loop_blocked_steps"] = len(blk)
    res["loop_blocked_forward_rank1"] = round(sum(s["top"] == "forward" for s in blk) / max(len(blk), 1), 4)
    res["model"] = GEMINI_MODEL if a.scorer == "gemini" else CLEF_MODEL
    res["input"] = a.input
    res["called"] = time.strftime("%Y-%m-%d")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("name", "all", "timeout", "gave_up", "api_aborted", "scorer_stats")}
                     | ({"vs": res["vs_no_rule"]} if base else {}), default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stepcheck", "loop"])
    ap.add_argument("--scorer", choices=["clef", "gemini"], required=True)
    ap.add_argument("--input", choices=["text", "image", "both"], default="text")
    ap.add_argument("--policy", choices=["none", "reset"], default="none")
    ap.add_argument("--eval", default="data/gotolocal_eval.jsonl")
    a = ap.parse_args()
    {"stepcheck": cmd_stepcheck, "loop": cmd_loop}[a.cmd](a)


if __name__ == "__main__":
    main()
