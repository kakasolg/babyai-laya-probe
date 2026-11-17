"""Stage 11a (reports/stage11_prereg.md): GoToLocal with a "previous actions:" line (last 4 actions) in the state text.

Usage (WSL, repo root):
  python -m probe.stage11 rows --dump <data>/gotolocal_train.jsonl --out <data>/laya_rows_gotolocal_prev4.jsonl
  python -m probe.stage11 train --rows <data>/laya_rows_gotolocal_prev4.jsonl --seed 0
  python -m probe.stage11 loop --seed 0 --policy none|reset
  python -m probe.stage11 stepcheck --seed 0 --eval <data>/gotolocal_eval.jsonl

Training fills the line with the bot's own previous actions; the closed loop fills it with the actions actually
executed (the R-reset pick when the rule picked). The R-reset key stays the obs text (no mission line, no
previous-actions line), exactly as in stage 5.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import time

from probe.laya_model import FT_ROOT
from probe.laya_rows import QID, question
from probe.obs_text import CHOICES

OUT = pathlib.Path("reports/stage11")
PREV_N = 4


def prev_line(acts: list[str]) -> str:
    return "previous actions: " + (", ".join(acts[-PREV_N:]) if acts else "none")


def state(text: str, mission: str, acts: list[str]) -> str:
    return f"mission: {mission}\n{prev_line(acts)}\n{text}"


def demos_with_prev(path: str):
    """Dump lines in file order (one episode after another, steps in order) + the bot's previous actions."""
    acts, last_seed = [], None
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        if d["seed"] != last_seed:
            acts, last_seed = [], d["seed"]
            assert d["step"] == 0, d["seed"]
        d["prev"] = list(acts)
        yield d
        acts.append(d["action_name"])


def cmd_rows(a):
    n = 0
    with open(a.out, "w", encoding="utf-8") as g:
        for d in demos_with_prev(a.dump):
            g.write(json.dumps({"state": state(d["text"], d["mission"], d["prev"]), "questions": question(),
                                "expected": {QID: d["action_name"]}}) + "\n")
            n += 1
    print(json.dumps({"rows": n, "out": a.out}))


def cmd_train(a):
    import torch
    from laya.train import TrainConfig, finetune

    from probe.laya_model import BASE_REV, base_dir
    name = f"gotolocal-prev4-s{a.seed}"
    out = os.path.join(FT_ROOT, name)
    cfg = TrainConfig(shuffle_options=("choice",), seed=a.seed)  # stage 2b settings
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    rep = finetune(a.rows, base_dir(), out, cfg)
    summary = {"name": name, "checkpoint": out, "base": f"convaiinnovations/laya@{BASE_REV}",
               "rows": sum(1 for _ in open(a.rows, encoding="utf-8")),
               "config": {k: str(v) for k, v in cfg.__dict__.items()},
               "train_minutes": round((time.time() - t0) / 60, 2),
               "gpu_peak_alloc_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               **{k: rep.get(k) for k in ("train_items", "calibration_items", "temperature", "epoch_loss",
                                          "calibration")}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"train_{name}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("name", "train_minutes", "epoch_loss")}, default=str))


def ckpt(seed: int) -> str:
    return os.path.join(FT_ROOT, f"gotolocal-prev4-s{seed}")


def cmd_loop(a):
    from probe.stage5 import LayaScorer, run_loop, summarize
    from probe.dump_demos import guarded_seeds
    seeds = list(guarded_seeds("10000-10299"))
    sc = LayaScorer(ckpt(a.seed))
    eps, aborted = run_loop(sc, a.policy, seeds,
                            state_fn=lambda e: state(e.text(), e.obs["mission"], [s["policy"] for s in e.steps]))
    name = f"prev4-s{a.seed}" + ("" if a.policy == "none" else f"-{a.policy}")
    base_p = OUT / f"prev4-s{a.seed}.json"
    base = json.load(open(base_p, encoding="utf-8")) if a.policy != "none" else None
    res = summarize(eps, name, sc, a.policy, aborted, base)
    res["model"] = ckpt(a.seed)
    res["seeds"] = "10000-10299"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("name", "all", "timeout", "blocked_forward_steps")}
                     | ({"vs": res["vs_no_rule"]} if base else {}), default=str))


def cmd_stepcheck(a):
    from probe.stage5 import LayaScorer, ranked
    sc = LayaScorer(ckpt(a.seed))
    rows = [d for d in demos_with_prev(a.eval) if d["action_name"] in CHOICES]
    full = sc.score([state(d["text"], d["mission"], d["prev"]) for d in rows])
    masked = sc.score([state(d["text"], d["mission"], []) for d in rows])
    for d, f, m in zip(rows, full, masked):
        d["m"], d["mm"] = ranked(f["probs"])[0], ranked(m["probs"])[0]
        d["prev_bot"] = d["prev"][-1] if d["prev"] else None

    def acc(sub, key="m"):
        return {"n": len(sub), "agree": round(sum(d[key] == d["action_name"] for d in sub) / max(len(sub), 1), 4)}

    later = [d for d in rows if d["prev_bot"] is not None]
    res = {"model": ckpt(a.seed), "steps": len(rows), "all": acc(rows),
           "bot_action_same": acc([d for d in later if d["prev_bot"] == d["action_name"]]),
           "bot_action_changed": acc([d for d in later if d["prev_bot"] != d["action_name"]]),
           "first_step": acc([d for d in rows if d["prev_bot"] is None]),
           "masked_none": {"all": acc(rows, "mm"),
                           "bot_action_same": acc([d for d in later if d["prev_bot"] == d["action_name"]], "mm"),
                           "bot_action_changed": acc([d for d in later if d["prev_bot"] != d["action_name"]], "mm")},
           "repeat_prev_rate": {"model": round(sum(d["m"] == d["prev_bot"] for d in later) / len(later), 4),
                                "bot": round(sum(d["action_name"] == d["prev_bot"] for d in later) / len(later), 4),
                                "masked_model": round(sum(d["mm"] == d["prev_bot"] for d in later) / len(later), 4),
                                "n": len(later)},
           "model_choice_share": dict(collections.Counter(d["m"] for d in rows))}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"stepcheck-prev4-s{a.seed}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("rows")
    p.add_argument("--dump", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("train")
    p.add_argument("--rows", required=True)
    p.add_argument("--seed", type=int, required=True)
    p = sub.add_parser("loop")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--policy", choices=["none", "reset"], default="none")
    p = sub.add_parser("stepcheck")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--eval", required=True)
    a = ap.parse_args()
    {"rows": cmd_rows, "train": cmd_train, "loop": cmd_loop, "stepcheck": cmd_stepcheck}[a.cmd](a)


if __name__ == "__main__":
    main()
