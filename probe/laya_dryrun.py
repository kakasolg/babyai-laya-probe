"""Check the finetune data format against installed Laya WITHOUT training or loading weights.

Downloads only tokenizer/* + rl_agent_config.json of each candidate checkpoint (pinned revision),
runs laya.train.dry_run, and measures the full model-input length per row.
Usage: python -m probe.laya_dryrun data/demos_train.jsonl [--out reports/laya_dryrun.json]
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import pathlib
import statistics

import laya
from huggingface_hub import snapshot_download
from laya.revisions import PINNED_REVISIONS
from laya.router import resolve_model_spec
from laya.train import TrainConfig, dry_run, encode_item, finetune, items_from_rows, read_data
from transformers import AutoTokenizer

from probe.laya_rows import write_rows

CANDIDATES = ["english", "multilingual"]


def config_only_dir(alias: str) -> str:
    repo, sub = resolve_model_spec(alias)
    prefix = f"{sub}/" if sub else ""
    d = snapshot_download(repo, revision=PINNED_REVISIONS.get(repo),
                          allow_patterns=[prefix + "rl_agent_config.json", prefix + "tokenizer/*"])
    return os.path.join(d, sub) if sub else d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--rows", default="data/laya_rows_train.jsonl")
    ap.add_argument("--out", default="reports/laya_dryrun.json")
    a = ap.parse_args()
    n = write_rows(a.dump, a.rows)
    res = {"laya": getattr(laya, "__version__", "?"), "rows": n,
           "finetune_signature": str(inspect.signature(finetune)),
           "trainconfig_defaults": {k: str(v) for k, v in TrainConfig().__dict__.items()}, "checkpoints": {}}
    cfg = TrainConfig(shuffle_options=("choice",))
    for alias in CANDIDATES:
        d = config_only_dir(alias)
        rl_cfg = json.load(open(os.path.join(d, "rl_agent_config.json"), encoding="utf-8"))
        summ = dry_run(a.rows, d, cfg)
        from laya.agent import _fix_tokenizer_config
        _fix_tokenizer_config(d)
        tok = AutoTokenizer.from_pretrained(os.path.join(d, "tokenizer"))
        rows = read_data(a.rows)
        items, _ = items_from_rows(tok, rows, summ["max_len"], summ["head_max_len"])
        full = [len(encode_item(tok, it, summ["max_len"], summ["head_max_len"])["ids"]) for it in items]
        state = [len(it["state_ids"]) for it in items]
        res["checkpoints"][alias] = {
            "repo": resolve_model_spec(alias), "revision": PINNED_REVISIONS.get(resolve_model_spec(alias)[0]),
            "dir": d, "rl_agent_config_keys": sorted(rl_cfg), "max_len": summ["max_len"],
            "head_max_len": summ["head_max_len"], "dry_run": {k: v for k, v in summ.items() if k != "data"},
            "tokens_state(mission+text)": {"median": statistics.median(state), "max": max(state)},
            "tokens_full_input": {"median": statistics.median(full), "max": max(full)},
        }
        print(alias, json.dumps(res["checkpoints"][alias]["tokens_full_input"]),
              json.dumps(res["checkpoints"][alias]["tokens_state(mission+text)"]), flush=True)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
