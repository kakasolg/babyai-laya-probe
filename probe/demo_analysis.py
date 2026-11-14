"""Stage 3.5 item 7: does the previous step carry information the bot uses? (training demos, no model)

Usage: python -m probe.demo_analysis data/gotolocal_train.jsonl [--out reports/stage3_5/demo_analysis.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib

from probe.measure_env import ambiguity


def with_prev(rows):
    prev = {}
    for r in rows:  # dump is in (seed, step) order
        p = prev.get(r["seed"])
        r["prev_text"] = p["text"] if p else None
        r["prev_action"] = p["action_name"] if p else None
        prev[r["seed"]] = r
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--out", default="reports/stage3_5/demo_analysis.json")
    a = ap.parse_args()
    rows = with_prev([json.loads(l) for l in open(a.dump, encoding="utf-8")])
    later = [r for r in rows if r["prev_action"] is not None]
    res = {"episodes": len({r["seed"] for r in rows}), "steps": len(rows), "steps_with_prev": len(later)}
    res["ambiguity"] = {
        "text+mission": ambiguity([((r["text"], r["mission"]), r["action"]) for r in rows]),
        "text+mission+prev_text+prev_action": ambiguity(
            [((r["text"], r["mission"], r["prev_text"], r["prev_action"]), r["action"]) for r in rows]),
    }
    same = sum(r["action_name"] == r["prev_action"] for r in later)
    res["same_as_prev_action"] = {"over_steps_with_prev": round(same / len(later), 4),
                                  "copy_baseline_all_steps_first_counts_wrong": round(same / len(rows), 4)}
    fwd = [r for r in later if r["prev_action"] == "forward"]
    trn = [r for r in later if r["prev_action"] != "forward"]
    res["forward_after_forward"] = round(sum(r["action_name"] == "forward" for r in fwd) / len(fwd), 4)
    res["forward_after_turn"] = round(sum(r["action_name"] == "forward" for r in trn) / len(trn), 4)
    runs = collections.Counter()
    for seed in sorted({r["seed"] for r in rows}):
        acts = [r["action_name"] for r in rows if r["seed"] == seed]
        n = 0
        for x in acts + [None]:
            if x == "forward":
                n += 1
            else:
                if n:
                    runs[n] += 1
                n = 0
    res["forward_run_lengths"] = dict(sorted(runs.items()))
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
