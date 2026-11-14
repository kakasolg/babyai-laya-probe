"""Stats over a demo dump: ambiguity before/after obs->text, 10 samples, token lengths.

Usage: python -m probe.text_stats data/demos_train.jsonl [--tokenizer <hf dir or repo>] [--out reports/text_stats.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import statistics

from probe.measure_env import ambiguity


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--tokenizer", default=None)
    ap.add_argument("--out", default="reports/text_stats.json")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.dump, encoding="utf-8")]
    res = {"steps": len(rows), "episodes": len({r["seed"] for r in rows})}

    img = lambda r: json.dumps(r["image"])  # noqa: E731
    res["ambiguity"] = {
        "image+mission": ambiguity([((img(r), r["mission"]), r["action"]) for r in rows]),
        "image+direction+mission": ambiguity([((img(r), r["direction"], r["mission"]), r["action"]) for r in rows]),
        "text+mission": ambiguity([((r["text"], r["mission"]), r["action"]) for r in rows]),
    }
    unseen = [r for r in rows if "objects: none in view" in r["text"]]
    res["object_not_in_view_share"] = round(len(unseen) / len(rows), 4)
    res["object_not_in_view_ambiguity"] = ambiguity([((r["text"], r["mission"]), r["action"]) for r in unseen])

    # Where text keys split: the most frequent split keys with their action counts.
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        by[(r["text"], r["mission"])][r["action_name"]] += 1
    splits = sorted(((k, c) for k, c in by.items() if len(c) > 1), key=lambda kc: -sum(kc[1].values()))
    res["top_split_keys"] = [{"mission": k[1], "text": k[0], "bot_actions": dict(c)} for k, c in splits[:8]]

    # 10 samples: 4 with no object in view, 6 with the object visible (fixed rng, reproducible).
    rng = random.Random(0)
    seen = [r for r in rows if r not in unseen]
    pick = rng.sample(unseen, 4) + rng.sample(seen, 6)
    res["samples"] = [{k: r[k] for k in ("seed", "step", "mission", "text", "action_name")} for r in pick]

    if a.tokenizer:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(a.tokenizer)
        n_text = [len(tok(r["text"], add_special_tokens=False)["input_ids"]) for r in rows]
        n_both = [len(tok(r["mission"] + "\n" + r["text"], add_special_tokens=False)["input_ids"]) for r in rows]
        res["tokens"] = {"tokenizer": a.tokenizer,
                         "text": {"median": statistics.median(n_text), "max": max(n_text), "min": min(n_text)},
                         "mission+text": {"median": statistics.median(n_both), "max": max(n_both)}}
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("samples", "top_split_keys")}, indent=1))


if __name__ == "__main__":
    main()
