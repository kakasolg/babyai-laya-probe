"""Stage 11b (reports/stage11b_prereg.md): demo-count curve, N = 100 / 500 / 5,000 bot demos (1,000 = stages 5 / 10).

Usage (WSL, repo root, PY=~/babyai-laya-venv/bin/python, HF_HUB_OFFLINE=1):
  $PY -m probe.stage11b dump --task gotolocal|putnext        # seeds 0-4999 -> data/n5000_<task>.jsonl (+ check vs 1,000)
  $PY -m probe.stage11b train --task gotolocal --n 100 --seed 0
  $PY -m probe.stage11b eval --task gotolocal --n 100 --seed 0  # step agreement, loop none, loop reset

Inputs, questions, choices and training settings are those of stage 5 (GoToLocal) and stage 10 (PutNextLocal,
carrying line). Demos for N are the kept episodes among bot seeds 0..N-1 (same filters as before).
Calibration: laya holds out steps at random (not whole episodes); only the count is scaled to the N=1,000 ratio.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import pathlib
import time

OUT = pathlib.Path("reports/stage11b")
DUMP = "data/n5000_{task}.jsonl"
OLD_DUMP = {"gotolocal": "/mnt/d/dev/kotlin-prj/baby-ai-laya-probe/data/gotolocal_train.jsonl",
            "putnext": "data/putnext_train.jsonl"}
CALIB_RATIO = {"gotolocal": 400 / 5310, "putnext": 400 / 12036}
DEV = "10000-10299"


# ---------------------------------------------------------------- dump

def _episode(args):
    task, seed = args
    if task == "gotolocal":
        from probe.dump_demos import ENV_ID, episode
        from probe.obs_text import ACTIONS
        lines, _ok, acts = episode(ENV_ID, seed)
        keep = all(x in ACTIONS for x in acts)
    else:
        from probe.stage10 import ACT, bot_episode
        lines, ok, _ = bot_episode(seed)
        keep = ok and all(r["action"] in ACT for r in lines)
    return seed, keep, lines


def cmd_dump(a):
    from probe.dump_demos import guarded_seeds
    from probe.stage10 import seeds_of
    seeds = list(guarded_seeds("0-4999"))
    assert list(seeds_of("0-4999")) == seeds  # the stage-10 guard allows the train range too
    t0 = time.time()
    with mp.Pool(24) as pool:
        res = pool.map(_episode, [(a.task, s) for s in seeds], chunksize=20)
    out = DUMP.format(task=a.task)
    dropped = []
    with open(out, "w", encoding="utf-8") as f:
        for seed, keep, lines in res:
            if not keep:
                dropped.append(seed)
                continue
            for ln in lines:
                f.write(json.dumps(ln) + "\n")
    # first 1,000 seeds must equal the existing N=1,000 dump line for line
    new = [json.loads(l) for l in open(out, encoding="utf-8")]
    new1k = [d for d in new if d["seed"] < 1000]
    old = [json.loads(l) for l in open(OLD_DUMP[a.task], encoding="utf-8")]
    same = new1k == old
    summ = {"task": a.task, "seeds": "0-4999", "minutes": round((time.time() - t0) / 60, 2),
            "check_first_1000_equals_old_dump": same, "old_dump_lines": len(old), "new_first_1000_lines": len(new1k),
            "per_n": {n: sizes(a.task, new, dropped, n) for n in (100, 500, 1000, 5000)}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"dump-{a.task}.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summ.items() if k != "per_n"}
                     | {"per_n": {n: {k: v for k, v in d.items() if k != "dropped_seeds"}
                                  for n, d in summ["per_n"].items()}}))
    if not same:
        raise SystemExit("first 1,000 seeds differ from the existing dump: stop (prereg 1)")


def sizes(task, rows, dropped, n):
    sub = [d for d in rows if d["seed"] < n]
    return {"episodes_kept": len({d["seed"] for d in sub}), "steps": len(sub),
            "calibration_items": round(len(sub) * CALIB_RATIO[task]), "dropped_seeds": [s for s in dropped if s < n]}


def demos(task: str, n: int):
    return [d for d in map(json.loads, open(DUMP.format(task=task), encoding="utf-8")) if d["seed"] < n]


# ---------------------------------------------------------------- train

def name_of(task, n, seed):
    return f"n{n}-{task}-s{seed}"


def ckpt(task, n, seed):
    from probe.laya_model import FT_ROOT
    return os.path.join(FT_ROOT, name_of(task, n, seed))


def cmd_train(a):
    import torch
    from laya.train import TrainConfig, finetune

    from probe.laya_model import BASE_REV, base_dir
    from probe.laya_rows import QID, question, question_putnext, state_text
    rows = demos(a.task, a.n)
    q = question() if a.task == "gotolocal" else question_putnext()
    rows_path = f"data/laya_rows_{name_of(a.task, a.n, 'X')}.jsonl"
    with open(rows_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"state": state_text(r["text"], r["mission"]), "questions": q,
                                "expected": {QID: r["action_name"]}}) + "\n")
    n_calib = round(len(rows) * CALIB_RATIO[a.task])
    cfg = TrainConfig(shuffle_options=("choice",), seed=a.seed, calib_max=n_calib, calib_frac=0.999)
    out = ckpt(a.task, a.n, a.seed)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    rep = finetune(rows_path, base_dir(), out, cfg)
    summary = {"name": name_of(a.task, a.n, a.seed), "checkpoint": f"babyai-laya-ft/{name_of(a.task, a.n, a.seed)}",
               "base": f"convaiinnovations/laya@{BASE_REV}", "task": a.task, "n_demo_seeds": a.n,
               "episodes_kept": len({r["seed"] for r in rows}), "steps": len(rows), "calib_target": n_calib,
               "config": {k: str(v) for k, v in cfg.__dict__.items()},
               "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0)),
               "train_minutes": round((time.time() - t0) / 60, 2),
               "gpu_peak_alloc_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               **{k: rep.get(k) for k in ("train_items", "calibration_items", "temperature", "epoch_loss",
                                          "calibration")}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"train-{summary['name']}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("name", "episodes_kept", "steps", "train_items", "calibration_items",
                                              "train_minutes", "epoch_loss")}, default=str))


# ---------------------------------------------------------------- eval

def cmd_eval(a):
    name = name_of(a.task, a.n, a.seed)
    path = ckpt(a.task, a.n, a.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.task == "gotolocal":
        from probe.dump_demos import guarded_seeds
        from probe.stage5 import LayaScorer, run_loop, stepcheck, summarize
        sc = LayaScorer(path)
        step = stepcheck(sc)
        (OUT / f"stepeval-{name}.json").write_text(json.dumps(step, indent=1), encoding="utf-8")
        seeds = list(guarded_seeds(DEV))
        base = None
        for pol in ("none", "reset"):
            eps, aborted = run_loop(sc, pol, seeds)
            tag = name + ("" if pol == "none" else "-reset")
            res = summarize(eps, tag, sc, pol, aborted, base)
            res["blocked_forward_rate"] = round(res["blocked_forward_steps"] / max(res["steps_total"], 1), 4)
            res["model"], res["seeds"] = f"babyai-laya-ft/{name}", DEV
            (OUT / f"{tag}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
            base = res
            print(json.dumps({"name": tag, "all": res["all"], "timeout": res["timeout"],
                              "blocked_forward_rate": res["blocked_forward_rate"]}
                             | ({"broken": res["vs_no_rule"]["broken"]} if pol == "reset" else {})))
        print(json.dumps({"stepeval": step["all"], "order_flip": step["order_flip_rate"],
                          "choice_vs_argmax": step["scorer_stats"]}))
    else:
        import probe.stage10 as s10
        s10.OUT = OUT
        s10.stepeval(path, name, False)
        sc = s10.Scorer(path)
        base = None
        for pol in ("none", "reset"):
            eps = s10.run_loop(pol, sc, s10.seeds_of(DEV))
            tag = name + ("" if pol == "none" else "-reset")
            res = s10.summarize(eps, tag, pol, base)
            res["env"], res["seeds"], res["carry_line"], res["model"] = s10.ENV, DEV, True, f"babyai-laya-ft/{name}"
            (OUT / f"{tag}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
            base = res
            print(json.dumps({"name": tag, "all": res["all"], "timeout": res["timeout"], "reached": res["reached"],
                              "blocked_forward_rate": res["blocked_forward_rate"]}
                             | ({"broken": res["vs_no_rule"]["broken"]} if pol == "reset" else {})))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["dump", "train", "eval"])
    ap.add_argument("--task", choices=["gotolocal", "putnext"], required=True)
    ap.add_argument("--n", type=int, choices=[100, 500, 5000])
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    {"dump": cmd_dump, "train": cmd_train, "eval": cmd_eval}[a.cmd](a)


if __name__ == "__main__":
    main()
