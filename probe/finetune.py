"""Stage 2b: minimal fine-tune of the pinned english checkpoint on the GoToLocal bot demos.

Usage: python -m probe.finetune data/gotolocal_train.jsonl [--seed 0] [--name gotolocal-s0]
Options are shuffled per epoch by Laya itself (shuffle_options=("choice",)), the same intent as
dsr-bot laya_finetune.py (position bias). Default epochs. Checkpoint goes to ~/babyai-laya-ft/<name>.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import time

import torch
from laya.train import TrainConfig, finetune

from probe.laya_model import BASE_REV, FT_ROOT, base_dir
from probe.laya_rows import write_rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--name", default="gotolocal-s0")
    a = ap.parse_args()
    rows = "data/laya_rows_gotolocal_train.jsonl"
    n = write_rows(a.dump, rows)
    out = os.path.join(FT_ROOT, a.name)
    cfg = TrainConfig(shuffle_options=("choice",), seed=a.seed)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    rep = finetune(rows, base_dir(), out, cfg)
    mins = (time.time() - t0) / 60
    summary = {"name": a.name, "checkpoint": out, "base": f"convaiinnovations/laya@{BASE_REV}", "rows": n,
               "config": {k: str(v) for k, v in cfg.__dict__.items()}, "train_minutes": round(mins, 2),
               "gpu_peak_alloc_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               "gpu_peak_reserved_gb": round(torch.cuda.max_memory_reserved() / 2**30, 2),
               "gpu": torch.cuda.get_device_name(0),
               **{k: rep.get(k) for k in ("train_items", "calibration_items", "temperature", "epoch_loss",
                                          "calibration")}}
    p = pathlib.Path(f"reports/stage2b_train_{a.name}.json")
    p.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("train_minutes", "gpu_peak_alloc_gb", "epoch_loss")}, default=str))


if __name__ == "__main__":
    main()
