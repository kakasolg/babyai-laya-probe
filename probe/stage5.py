"""Stage 5: closed loop for three scorers (Laya fine-tuned, Jev and Gemma 12B untrained) with/without rule R.

Usage (WSL, repo root):
  python -m probe.stage5 loop --scorer laya --model ~/babyai-laya-ft/gotolocal-s0 --name laya-s0 [--policy R|reset|penalty]
  python -m probe.stage5 loop --scorer gemma|jev --name gemma [--policy R|reset]
  python -m probe.stage5 stepcheck --scorer gemma|jev           # bot trajectories of the 300 dev seeds

Fixed for every run (board instruction 11-14, stage 5):
  dev seeds 10000-10299 (all 300), step limit 64, input = Laya's state text (mission line + obs text),
  options in the order turn left / turn right / forward, deterministic (highest score), no escape rule.

Rule R (exactly as defined on the board; nothing else):
  per episode an empty table tried; key = the obs text given to the model at this step.
  Rank the three actions by score; take the highest one not in tried[key], add it to tried[key].
  All three tried -> the episode ends as gave_up (a failure, counted apart from timeout).
  Executed action != rank 1 -> one intervention.
R-reset (board 11-14 20:29): as R, except all three tried -> clear tried[key] only, take rank 1, keep walking.
Visit penalty (Laya only): per key count[a]; take argmax ln(max(p(a), 1e-9)) - 2.0 * count[a], then count[a] += 1.

Jev/Gemma calls are cached by (model, explanation, state, option order): the same request is sent once.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import math
import os
import pathlib
import statistics
import time
import urllib.error
import urllib.request

import numpy as np

from probe.closed_loop import NAME_TO_ACT, Ep
from probe.dump_demos import guarded_seeds, seed_range
from probe.laya_rows import state_text
from probe.obs_text import CHOICES
from probe.text_stats import categorize

OUT = pathlib.Path("reports/stage5")
SEEDS = "10000-10299"
ALL_FAIL_12 = [10014, 10015, 10016, 10017, 10023, 10024, 10026, 10122, 10149, 10164, 10220, 10242]

# The explanation given to both untrained models. Fixed before any Jev/Gemma call; copied verbatim into README.
EXPLAIN = """You control an agent in a grid room. Choose exactly one action using only the
current observation and the mission.

turn left / turn right: rotate 90 degrees in place, no movement.
forward: move one cell ahead. It does nothing if that cell holds a wall or an object.

The mission succeeds when an object matching the mission's color and type is in the
cell directly ahead of the agent. Any matching object counts.

The observation lists only what is inside the agent's limited forward view.
Cells that are not listed as objects or walls and are in view are empty.
Anything outside the view is unknown, not empty.

How to read the observation:
- "facing: east" is the compass direction the agent faces. All other positions are relative to the agent.
- The view covers the agent's own row and the 6 rows ahead, 3 cells to each side. Cells behind a wall are not seen.
- "<color> <type>: 2 ahead, 1 left" means that object is 2 cells forward and 1 cell to the left of the agent.
  A zero part is left out: "3 right" means the same row as the agent, 3 cells to the right.
- "X: 1 ahead" (no left/right part) means X is in the cell directly in front, so forward is blocked.
  If X matches the mission, the mission is already met.
- Objects are listed nearest first. "objects: none in view" means no object is visible.
- "walls: 4 ahead, 1 left" gives the distance to the nearest wall on the three straight lines from the agent
  (ahead, left, right); a line with no visible wall is left out, "walls: none in line" if none.
  "walls: 1 ahead" means a wall is directly in front, so forward is blocked. Walls off these lines are not listed."""

JEV_MODEL = os.environ.get("JEV_MODEL", "")  # explicit version, set at run time (never jev-latest)
GEMMA_MODEL = "gemma4:12b-it-q8_0"
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")


class ApiAborted(Exception):
    pass


class LayaScorer:
    name = "laya"

    def __init__(self, path: str):
        from probe.laya_model import Chooser
        self.ch = Chooser(path)
        self.choice_mismatch = 0  # Laya's own 'choice' field vs argmax of its probabilities

    def score(self, states: list[str], options=CHOICES) -> list[dict]:
        from probe.laya_rows import QID, question
        res = self.ch.agent.predict_batch(states, question(options), batch_size=128) if states else []
        out = []
        for r in res:
            a = r["answers"][QID]
            p = a.get("probabilities") or {}
            if p and a.get("choice") != max(options, key=lambda c: p.get(c, 0.0)):
                self.choice_mismatch += 1
            out.append({"probs": p})
        return out

    def stats(self):
        return {"choice_field_vs_argmax_mismatch": self.choice_mismatch}


class CachedScorer:
    """Request cache + counters for the untrained models."""
    workers = 4

    def __init__(self, model: str):
        self.model = model
        self.path = pathlib.Path(f"data/stage5_cache_{model.replace(':', '_').replace('/', '_')}.jsonl")
        self.cache = {}
        if self.path.exists():
            for line in open(self.path, encoding="utf-8"):
                d = json.loads(line)
                self.cache[d["key"]] = d
        self.new = self.reused = self.errors = 0
        self.lat = []
        self.usage = collections.Counter()

    def key(self, state: str, options) -> str:
        return hashlib.sha256(json.dumps([self.model, EXPLAIN, state, list(options)]).encode()).hexdigest()

    def score(self, states: list[str], options=CHOICES) -> list[dict]:
        keys = [self.key(s, options) for s in states]
        todo = {k: s for k, s in zip(keys, states) if k not in self.cache}
        self.reused += len(keys) - len(todo)
        if todo:
            with cf.ThreadPoolExecutor(self.workers) as ex:
                futs = {ex.submit(self.call, s, list(options)): k for k, s in todo.items()}
                with open(self.path, "a", encoding="utf-8") as f:
                    for fu in cf.as_completed(futs):
                        k = futs[fu]
                        d = fu.result()  # ApiAborted propagates
                        d.update({"key": k, "state": todo[k], "options": list(options)})
                        self.cache[k] = d
                        f.write(json.dumps(d) + "\n")
                        self.new += 1
                        self.lat.append(d["ms"])
                        for u, v in (d.get("usage") or {}).items():
                            if isinstance(v, (int, float)):
                                self.usage[u] += v
        return [self.cache[k] for k in keys]

    def stats(self):
        lat = sorted(self.lat)
        pct = (lambda q: round(lat[min(len(lat) - 1, int(q * len(lat)))], 1)) if lat else (lambda q: None)
        return {"model": self.model, "new_calls": self.new, "reused": self.reused, "errors_retried": self.errors,
                "latency_ms_p50": pct(0.5), "latency_ms_p95": pct(0.95), "usage_new_calls": dict(self.usage)}


class GemmaScorer(CachedScorer):
    name = "gemma"

    def __init__(self):
        super().__init__(GEMMA_MODEL)

    @staticmethod
    def prompt(state: str, options) -> str:
        opts = "\n".join(f"{i}) {o}" for i, o in enumerate(options, 1))
        return f"{EXPLAIN}\n\n[Observation]\n{state}\n\n[Actions]\n{opts}\n\nAnswer with one digit only."

    def call(self, state: str, options) -> dict:
        body = json.dumps({"model": self.model, "stream": False, "think": False, "logprobs": True, "top_logprobs": 20,
                           "options": {"temperature": 0, "num_predict": 2},
                           "messages": [{"role": "user", "content": self.prompt(state, options)}]}).encode()
        for attempt in range(3):
            try:
                t0 = time.perf_counter()
                req = urllib.request.Request(f"{OLLAMA}/api/chat", data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    d = json.loads(r.read())
                ms = (time.perf_counter() - t0) * 1000
                break
            except Exception:  # noqa: BLE001
                self.errors += 1
                if attempt == 2:
                    raise ApiAborted("ollama")
                time.sleep(2 ** attempt)
        raw = {}
        for t in d["logprobs"][0]["top_logprobs"]:
            tok = t["token"].strip()
            if len(tok) == 1 and tok in "123" and int(tok) <= len(options):
                o = options[int(tok) - 1]
                raw[o] = max(raw.get(o, -1e9), t["logprob"])
        text = d.get("message", {}).get("content", "")
        if not raw:
            return {"probs": {}, "format_error": True, "raw_answer": text, "ms": round(ms, 1)}
        z = sum(math.exp(v) for v in raw.values())
        probs = {o: (math.exp(raw[o]) / z if o in raw else 0.0) for o in options}
        out_tok = text.strip()[:1]
        return {"probs": probs, "format_error": out_tok not in ("1", "2", "3"), "raw_answer": text,
                "ms": round(ms, 1)}


class JevScorer(CachedScorer):
    name = "jev"
    ENDPOINT = "https://api.typesafe.ai/v1/systemone"
    MAX_CALLS = 45000

    def __init__(self):
        if not JEV_MODEL or "latest" in JEV_MODEL:
            raise SystemExit("set JEV_MODEL to an explicit version (not jev-latest)")
        super().__init__(JEV_MODEL)

    def call(self, state: str, options) -> dict:
        if self.new >= self.MAX_CALLS:
            raise ApiAborted("call limit 45,000 reached")
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise SystemExit("TYPESAFE_API_KEY not set")
        q = {"action": {"type": "choice", "instructions": EXPLAIN, "criteria": {o: None for o in options}}}
        body = json.dumps({"state": state, "model": self.model, "questions": q}).encode()
        for attempt in range(3):  # first try + 2 retries on transient errors
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(self.ENDPOINT, data=body, method="POST",
                                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    d = json.loads(r.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code not in (429,) and e.code < 500:
                    raise ApiAborted(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None
                self.errors += 1
            except (urllib.error.URLError, TimeoutError, OSError):
                self.errors += 1
            if attempt == 2:
                raise ApiAborted("transient errors x3")
            time.sleep(2 ** attempt)
        ms = (time.perf_counter() - t0) * 1000
        a = d["answers"]["action"]
        probs = a.get("probabilities") or {}
        bad = a.get("choice") not in options or not probs
        return {"probs": {o: float(probs.get(o, 0.0)) for o in options}, "format_error": bad,
                "raw_answer": {k: v for k, v in a.items() if k != "probabilities"}, "model_returned": d.get("model"),
                "usage": d.get("usage"), "ms": round(ms, 1)}


class FixedScorer:
    """Model-free control (board 11-15, stage 6): the same scores at every step."""
    name = "fixed"
    P = {"forward": 0.7, "turn left": 0.2, "turn right": 0.1}

    def score(self, states: list[str], options=CHOICES) -> list[dict]:
        return [{"probs": dict(self.P)} for _ in states]

    def stats(self):
        return {"fixed_probs": self.P}


def make_scorer(kind: str, model: str | None):
    return {"laya": lambda: LayaScorer(model), "gemma": GemmaScorer, "jev": JevScorer,
            "fixed": FixedScorer}[kind]()


def ranked(probs: dict) -> list[str]:
    return sorted(CHOICES, key=lambda c: -probs.get(c, 0.0))  # stable: ties keep the fixed option order


# ---------------------------------------------------------------- closed loop

PENALTY = 2.0  # visit penalty coefficient, fixed by the board (11-14 20:29); never tuned


def run_loop(scorer, policy: str, seeds=None):
    """policy: none | R | reset | penalty (board 11-14: R, R-reset and visit penalty share key and ranking)."""
    eps = [Ep(s, shadow_bot=False, swap=False) for s in (seeds if seeds is not None else seed_range(SEEDS))]
    for e in eps:
        e.tried, e.gave_up, e.n_interv, e.resets, e.count = {}, False, 0, 0, {}
    aborted = None
    while True:
        live = [e for e in eps if not e.done]
        if not live:
            break
        try:
            scores = scorer.score([state_text(e.text(), e.obs["mission"]) for e in live])
        except ApiAborted as x:
            aborted = str(x)
            break
        for e, sc in zip(live, scores):
            p = sc.get("probs") or {}
            order = ranked(p)
            text = e.text()
            c = order[0]
            interv = False
            if policy in ("R", "reset"):
                tried = e.tried.setdefault(text, set())
                left = [o for o in order if o not in tried]
                if not left:
                    if policy == "R":
                        e.gave_up = e.done = True
                        e.env.close()
                        continue
                    tried.clear()  # R-reset: only this key is cleared, then rank 1 as usual
                    e.resets += 1
                    left = order
                c = left[0]
                tried.add(c)
            elif policy == "penalty":
                cnt = e.count.setdefault(text, collections.Counter())
                c = max(CHOICES, key=lambda o: math.log(max(p.get(o, 0.0), 1e-9)) - PENALTY * cnt[o])  # ties: fixed order
                cnt[c] += 1
            if policy != "none":
                interv = c != order[0]
                e.n_interv += interv
            e.step(NAME_TO_ACT[c], choice=c, intervened=interv)
            e.steps[-1].update({"probs": p, "top": order[0], "top_p": p.get(order[0]),
                                "format_error": bool(sc.get("format_error"))})
    return eps, aborted


def rate(sub):
    n = len(sub)
    ok = sum(e.success for e in sub)
    ok2 = sum(e.success and len(e.steps) <= 2 * e.bot_n for e in sub)
    return {"n": n, "success": ok, "rate": round(ok / max(n, 1), 4), "within_2x_bot": ok2,
            "rate_2x": round(ok2 / max(n, 1), 4)}


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 4) if xs else None


def summarize(eps, name, scorer, policy, aborted, base=None):
    rule = policy != "none"
    succ = [e for e in eps if e.success]
    steps = [s for e in eps for s in e.steps]
    blocked = [s for s in steps if s["policy"] == "forward" and not s["moved"]]
    res = {"name": name, "scorer": scorer.name, "policy": policy, "rule_r": policy == "R", "api_aborted": aborted,
           "episodes": len(eps), "steps_sum_all_episodes": len(steps),
           "all": rate(eps), "timeout": sum(e.timeout for e in eps), "gave_up": sum(e.gave_up for e in eps),
           "target_visible_at_start": rate([e for e in eps if e.visible_at_start]),
           "target_unseen_at_start": rate([e for e in eps if not e.visible_at_start]),
           "mean_steps_success": round(float(np.mean([len(e.steps) for e in succ])), 2) if succ else None,
           "bot_mean_steps_same_eps": round(float(np.mean([e.bot_n for e in succ])), 2) if succ else None,
           "blocked_forward_steps": len(blocked),
           "top_p_median_blocked_forward": med([s["top_p"] for s in blocked]),
           "top_p_median_other_steps": med([s["top_p"] for s in steps if s not in blocked]),
           "format_error_steps": sum(s["format_error"] for s in steps), "steps_total": len(steps),
           "actions": dict(collections.Counter(s["policy"] for s in steps)),
           "all_fail_12_solved": [e.seed for e in eps if e.seed in ALL_FAIL_12 and e.success],
           "scorer_stats": scorer.stats(),
           "per_episode": {e.seed: {"end": "success" if e.success else "gave_up" if e.gave_up else
                                    "timeout" if e.timeout else "unfinished",
                                    "steps": len(e.steps), "bot": e.bot_n, "interventions": e.n_interv} for e in eps}}
    if rule:
        res["episodes_with_intervention"] = sum(e.n_interv > 0 for e in eps)
        res["interventions"] = sum(e.n_interv for e in eps)
        res["success_without_intervention"] = sum(e.success and e.n_interv == 0 for e in eps)
        res["success_with_intervention"] = sum(e.success and e.n_interv > 0 for e in eps)
    if policy == "reset":
        res["resets"] = sum(e.resets for e in eps)
        res["resets_per_episode"] = {"0": sum(e.resets == 0 for e in eps), "1": sum(e.resets == 1 for e in eps),
                                     "2+": sum(e.resets >= 2 for e in eps)}
        for k, e in zip(res["per_episode"], eps):
            res["per_episode"][k]["resets"] = e.resets
    if base is not None:
        b = {int(k): v["end"] == "success" for k, v in base["per_episode"].items()}
        res["vs_no_rule"] = {
            "saved": sorted(e.seed for e in eps if e.success and not b[e.seed]),
            "broken": sorted(e.seed for e in eps if not e.success and b[e.seed]),
            "gave_up_and_failed_without_rule": sum(e.gave_up and not b[e.seed] for e in eps)}
    res["trace"] = {e.seed: [[s["policy"], s["top"], round(s["top_p"] or 0, 3), int(s["moved"])] for s in e.steps]
                    for e in eps if not e.success}
    return res


# ---------------------------------------------------------------- step check (untrained models)

def stepcheck(scorer):
    rows = [json.loads(l) for l in open("data/gotolocal_eval.jsonl", encoding="utf-8")]
    rows = [r for r in rows if r["action_name"] in CHOICES]
    states = [state_text(r["text"], r["mission"]) for r in rows]
    fwd = scorer.score(states, CHOICES)
    rev = scorer.score(states, list(reversed(CHOICES)))
    for r, a, b in zip(rows, fwd, rev):
        r["m"] = ranked(a.get("probs") or {})[0]
        r["r"] = max(reversed(CHOICES), key=lambda c: (b.get("probs") or {}).get(c, 0.0))
        r["fe"] = bool(a.get("format_error")) or bool(b.get("format_error"))
        r["unseen"] = categorize(r)["target_unseen"]

    def acc(sub):
        return {"n": len(sub), "agree": round(sum(r["m"] == r["action_name"] for r in sub) / max(len(sub), 1), 4)}

    return {"scorer": scorer.name, "steps": len(rows), "all": acc(rows),
            "target_visible": acc([r for r in rows if not r["unseen"]]),
            "target_unseen": acc([r for r in rows if r["unseen"]]),
            "order_flip_rate": round(sum(r["m"] != r["r"] for r in rows) / len(rows), 4),
            "format_error_rate": round(sum(r["fe"] for r in rows) / len(rows), 4),
            "choice_share": dict(collections.Counter(r["m"] for r in rows)),
            "scorer_stats": scorer.stats()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["loop", "stepcheck"])
    ap.add_argument("--scorer", required=True, choices=["laya", "gemma", "jev", "fixed"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--rule", action="store_true", help="same as --policy R")
    ap.add_argument("--policy", default=None, choices=["none", "R", "reset", "penalty"])
    ap.add_argument("--base", default=None, help="no-rule run json to compare against")
    ap.add_argument("--seeds", default=SEEDS)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    seeds = list(guarded_seeds(a.seeds))
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sc = make_scorer(a.scorer, a.model and os.path.expanduser(a.model))
    if a.mode == "stepcheck":
        res = stepcheck(sc)
        (OUT / f"stepcheck-{a.scorer}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps(res))
        return
    policy = a.policy or ("R" if a.rule else "none")
    if policy == "penalty" and a.scorer != "laya":
        raise SystemExit("visit penalty is for the Laya seeds only (board 11-14 20:29)")
    eps, aborted = run_loop(sc, policy, seeds)
    base = json.load(open(a.base, encoding="utf-8")) if a.base else None
    res = summarize(eps, a.name, sc, policy, aborted, base)
    res["model"] = a.model if a.scorer == "laya" else getattr(sc, "model", None)
    res["seeds"] = a.seeds
    (out / f"{a.name}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("name", "all", "timeout", "gave_up", "api_aborted", "all_fail_12_solved",
                                          "scorer_stats")} | ({"vs": res["vs_no_rule"]} if base else {}), default=str))


if __name__ == "__main__":
    main()
