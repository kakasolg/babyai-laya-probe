"""Stats over a demo dump: step categories, 10 samples, ambiguity, token lengths.

Usage: python -m probe.text_stats data/gotolocal_train.jsonl [--tokenizer <dir>] [--out reports/gotolocal_text_stats.json]

Categories (from the 7x7 view + the instruction's type/color):
  target_unseen     no object matching the mission is in view
  distractor_closer a matching object is in view but a non-matching one is nearer (ahead + |side|)
  two_matching      the room holds >= 2 matching objects (n_matching from the env)
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import statistics

import numpy as np

from probe.measure_env import ambiguity
from probe.obs_text import AX, AY, IDX_TO_COLOR, IDX_TO_OBJECT, _SKIP, rel


def visible(image) -> list[tuple[int, str, str]]:
    img = np.asarray(image)
    out = []
    for i in range(7):
        for j in range(7):
            o = int(img[i, j, 0])
            if o in _SKIP or (i, j) == (AX, AY):
                continue
            ahead, side = rel(i, j)
            out.append((ahead + abs(side), IDX_TO_OBJECT[o], IDX_TO_COLOR[int(img[i, j, 1])]))
    return out


def categorize(r: dict) -> dict:
    t = r["target"]
    vis = visible(r["image"])
    match = [v for v in vis if v[1] == t["type"] and (t["color"] is None or v[2] == t["color"])]
    other = [v for v in vis if v not in match]
    return {
        "target_unseen": not match,
        "distractor_closer": bool(match) and bool(other) and min(o[0] for o in other) < min(m[0] for m in match),
        "two_matching": r["n_matching"] >= 2,
        "two_matching_in_view": len(match) >= 2,
        "n_visible": len(vis),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--tokenizer", default=None)
    ap.add_argument("--out", default="reports/gotolocal_text_stats.json")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.dump, encoding="utf-8")]
    for r in rows:
        r["cat"] = categorize(r)
    n = len(rows)
    eps = {r["seed"]: r for r in rows if r["step"] == 0}
    res = {"steps": n, "episodes": len(eps), "missions": len({r["mission"] for r in rows})}
    res["step_share"] = {k: round(sum(r["cat"][k] for r in rows) / n, 4)
                         for k in ("target_unseen", "distractor_closer", "two_matching", "two_matching_in_view")}
    res["episode_share"] = {
        "two_matching": round(sum(r["n_matching"] >= 2 for r in eps.values()) / len(eps), 4),
        "target_unseen_at_start": round(sum(r["cat"]["target_unseen"] for r in eps.values()) / len(eps), 4),
    }
    res["visible_objects_per_step"] = {"mean": round(statistics.mean(r["cat"]["n_visible"] for r in rows), 2),
                                       "max": max(r["cat"]["n_visible"] for r in rows)}

    img = lambda r: json.dumps(r["image"])  # noqa: E731
    # Distinct keys ≈ steps means the data is sparse; this is NOT an accuracy ceiling (README).
    res["ambiguity"] = {
        "image+mission": ambiguity([((img(r), r["mission"]), r["action"]) for r in rows]),
        "text+mission": ambiguity([((r["text"], r["mission"]), r["action"]) for r in rows]),
    }

    by = collections.defaultdict(collections.Counter)
    for r in rows:
        by[(r["text"], r["mission"])][r["action_name"]] += 1
    splits = sorted(((k, c) for k, c in by.items() if len(c) > 1), key=lambda kc: -sum(kc[1].values()))
    res["top_split_keys"] = [{"mission": k[1], "text": k[0], "bot_actions": dict(c)} for k, c in splits[:8]]

    # 10 samples, fixed rng: 3 target unseen, 3 distractor nearer than target, 2 with two matching
    # objects in view, 2 any. One per episode.
    rng = random.Random(0)
    used: set[int] = set()

    def pick(pool, k):
        pool = [r for r in pool if r["seed"] not in used]
        got = rng.sample(pool, k)
        used.update(r["seed"] for r in got)
        return got

    picks = (pick([r for r in rows if r["cat"]["target_unseen"]], 3)
             + pick([r for r in rows if r["cat"]["distractor_closer"]], 3)
             + pick([r for r in rows if r["cat"]["two_matching_in_view"]], 2)
             + pick(rows, 2))
    res["samples"] = [{**{k: r[k] for k in ("seed", "step", "mission", "n_matching", "text", "action_name")},
                       "cats": [k for k in ("target_unseen", "distractor_closer", "two_matching_in_view") if r["cat"][k]]}
                      for r in picks]

    if a.tokenizer:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(a.tokenizer)
        n_text = [len(tok(r["text"], add_special_tokens=False)["input_ids"]) for r in rows]
        res["tokens_text_only"] = {"tokenizer": a.tokenizer, "median": statistics.median(n_text), "max": max(n_text)}
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("samples", "top_split_keys")}, indent=1))


if __name__ == "__main__":
    main()
