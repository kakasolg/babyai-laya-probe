"""Stage 2b: step-level agreement with the bot on the eval dump, plus option-order sensitivity.

Usage: python -m probe.step_eval data/gotolocal_eval.jsonl --model <ckpt dir> [--name gotolocal-s0]
Each step is scored with the options in canonical order and reversed; "flip" = the two choices differ.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib

from probe.laya_model import Chooser
from probe.obs_text import CHOICES
from probe.text_stats import categorize


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", default="gotolocal-s0")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.dump, encoding="utf-8")]
    rows = [r for r in rows if r["action_name"] in CHOICES]
    ch = Chooser(a.model)
    texts, missions = [r["text"] for r in rows], [r["mission"] for r in rows]
    fwd = ch.choose_batch(texts, missions)
    rev = ch.choose_batch(texts, missions, choices=list(reversed(CHOICES)))
    prev = {}
    for r, (c, p), (rc, _) in zip(rows, fwd, rev):
        r["model"], r["rev"], r["top_p"] = c, rc, max(p.values()) if p else None
        r["cat"] = categorize(r)
        r["prev_bot"] = prev.get(r["seed"])
        prev[r["seed"]] = r["action_name"]

    def acc(sub):
        return {"n": len(sub), "agree": round(sum(r["model"] == r["action_name"] for r in sub) / max(len(sub), 1), 4)}

    res = {"model": a.model, "steps": len(rows), "all": acc(rows),
           "order_flip_rate": round(sum(r["model"] != r["rev"] for r in rows) / len(rows), 4),
           "reversed_order_agree": round(sum(r["rev"] == r["action_name"] for r in rows) / len(rows), 4),
           "by_category": {k: acc([r for r in rows if r["cat"][k]]) for k in
                           ("target_unseen", "distractor_closer", "two_matching", "two_matching_in_view")},
           # stage 3.5 item 7: bot action changes vs. repeats the previous bot action (first steps apart)
           "bot_action_changed": acc([r for r in rows if r["prev_bot"] is not None and r["prev_bot"] != r["action_name"]]),
           "bot_action_same": acc([r for r in rows if r["prev_bot"] is not None and r["prev_bot"] == r["action_name"]]),
           "first_step": acc([r for r in rows if r["prev_bot"] is None]),
           "target_visible_unique": acc([r for r in rows if not r["cat"]["target_unseen"] and not r["cat"]["two_matching"]]),
           "confusion_bot_to_model": {b: dict(collections.Counter(r["model"] for r in rows if r["action_name"] == b))
                                      for b in CHOICES},
           "model_choice_share": dict(collections.Counter(r["model"] for r in rows))}
    p = pathlib.Path(f"reports/stage2b_step_eval_{a.name}.json")
    p.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
