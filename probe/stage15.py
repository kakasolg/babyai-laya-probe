"""Stage 15: on-device Apple Foundation Models with outside rules on GoToLocal. Prereg: reports/stage15_prereg.md.
Same frame and seeds as stage 13 (probe/stage13.py); the model is reached through the Kortex Mac probe app.

  python -m probe.stage15 samecheck          # modified probe gives the stage-13 answers (60 uncached calls)
  python -m probe.stage15 a                  # 15a: reversed-order disagreement as an escalation signal (cache only)
  python -m probe.stage15 abonus             # 15a bonus: four more option orders on the 249 blocked steps
  python -m probe.stage15 loop --variant A1|A2|A3 [--seeds 10000-10099]
  python -m probe.stage15 peers              # untrained models + R-reset, recounted on the same 100 seeds (no calls)
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import pathlib
import time

from probe import stage5, stage12, stage13
from probe.closed_loop import NAME_TO_ACT, Ep
from probe.dump_demos import guarded_seeds
from probe.laya_rows import state_text
from probe.obs_text import CHOICES
from probe.stage5_blocked import blocked_ahead
from probe.text_stats import categorize

OUT = pathlib.Path("reports/stage15")
REV = list(reversed(CHOICES))
L, R, F = CHOICES


def scorer(a, cache_only=False):
    sc = stage13.AfmScorer("device", a.app)
    old = sc.cache  # stage-13 answers: read only
    stage12._reload(sc, "data/stage15_cache_afm-device.jsonl")
    sc.cache = old | sc.cache
    if cache_only:
        def miss(*_a, **_k):
            raise SystemExit("cache miss: refusing a new call")
        sc.call = miss
    return sc


def pick(d, options):
    p = d.get("probs") or {}
    return max(options, key=lambda c: p.get(c, 0.0))  # ties: first in the given order


def eval_rows(a):
    rows = [json.loads(l) for l in open(a.eval, encoding="utf-8")]
    rows = [r for r in rows if r["action_name"] in CHOICES]
    for r in rows:
        r["state"] = state_text(r["text"], r["mission"])
        r["unseen"] = categorize(r)["target_unseen"]
        r["blocked"] = blocked_ahead(r["state"])
    return rows


def save(name, res):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")


def cmd_samecheck(a):
    sc = scorer(a)
    rows = eval_rows(a)[:30]
    diff = []
    for r in rows:
        for opts in (CHOICES, REV):
            old = pick(sc.cache[sc.key(r["state"], opts)], opts)
            new = pick(sc.call(r["state"], list(opts)), opts)
            if old != new:
                diff.append({"seed": r["seed"], "step": r["step"], "options": list(opts), "stage13": old, "now": new})
    res = {"steps": len(rows), "calls": 2 * len(rows), "different": len(diff), "diff": diff, "called": time.strftime("%Y-%m-%d")}
    save("samecheck", res)
    print(json.dumps(res))


def cmd_a(a):
    sc = scorer(a, cache_only=True)
    rows = eval_rows(a)
    for r, x, y in zip(rows, sc.score([r["state"] for r in rows], CHOICES), sc.score([r["state"] for r in rows], REV)):
        r["m"], r["r"] = pick(x, CHOICES), pick(y, REV)
        r["same"], r["ok"] = r["m"] == r["r"], r["m"] == r["action_name"]

    def part(sub):
        same, diff = [r for r in sub if r["same"]], [r for r in sub if not r["same"]]
        wrong = [r for r in sub if not r["ok"]]
        ag = lambda s: round(sum(r["ok"] for r in s) / len(s), 4) if s else None  # noqa: E731
        return {"n": len(sub), "agree": ag(sub), "same_n": len(same), "same_agree": ag(same),
                "diff_n": len(diff), "diff_agree": ag(diff),
                "gap_pp": round(100 * (ag(same) - ag(diff)), 1) if same and diff else None,
                "wrong_n": len(wrong), "wrong_in_diff": sum(not r["same"] for r in wrong),
                "caught_share": round(sum(not r["same"] for r in wrong) / max(len(wrong), 1), 4),
                "diff_wrong_share": round(sum(not r["ok"] for r in diff) / max(len(diff), 1), 4),
                "pairs_fixed_vs_reversed": dict(collections.Counter(f"{r['m']} | {r['r']}" for r in sub)),
                "diff_bot_action": dict(collections.Counter(r["action_name"] for r in diff)),
                "diff_reversed_agrees_with_bot": sum(r["r"] == r["action_name"] for r in diff)}

    res = {"all": part(rows), "blocked": part([r for r in rows if r["blocked"]]),
           "target_unseen": part([r for r in rows if r["unseen"]]),
           "target_visible_not_blocked": part([r for r in rows if not r["unseen"] and not r["blocked"]])}
    al = res["all"]
    gap, caught = al["gap_pp"], al["caught_share"]
    res["reading"] = ("usable escalation signal" if gap >= 15 and caught >= 0.40 else
                      "right when it fires but misses most mistakes" if gap >= 15 else "not a signal")
    res["scorer_stats"] = sc.stats()
    save("a-order-disagreement", res)
    print(json.dumps(res, indent=1))


def cmd_abonus(a):
    sc = scorer(a)
    rows = [r for r in eval_rows(a) if r["blocked"]]
    states = [r["state"] for r in rows]
    res = {"blocked_steps": len(rows), "unique_states": len(set(states)), "orders": {}}
    pos = {k: collections.Counter() for k in ("first", "middle", "last")}
    right_not_middle = n_not_middle = 0
    for order in itertools.permutations(CHOICES):
        order = list(order)
        ds = sc.score(states, order)
        picks = [pick(d, order) for d in ds]
        res["orders"][" / ".join(order)] = {
            "picks": dict(collections.Counter(picks)),
            "by_position": dict(collections.Counter(("first", "middle", "last")[order.index(p)] for p in picks)),
            "agree_bot": sum(p == r["action_name"] for p, r in zip(picks, rows)),
            "format_errors": sum(bool(d.get("format_error")) for d in ds)}
        for p in picks:
            pos[("first", "middle", "last")[order.index(p)]][p] += 1
        if order[1] != R:
            n_not_middle += len(picks)
            right_not_middle += sum(p == R for p in picks)
    share = right_not_middle / n_not_middle
    res.update({"by_position_all_orders": {k: dict(v) for k, v in pos.items()},
                "turn_right_when_not_middle": right_not_middle, "steps_when_not_middle": n_not_middle,
                "turn_right_share_not_middle": round(share, 4),
                "bot_action_on_blocked": dict(collections.Counter(r["action_name"] for r in rows)),
                "reading": "not the position" if share < 0.05 else "mostly the position" if share >= 0.20 else "partly",
                "scorer_stats": sc.stats(), "called": time.strftime("%Y-%m-%d")})
    save("a-bonus-positions", res)
    print(json.dumps(res, indent=1))


def cmd_loop(a):
    sc = scorer(a)
    v = a.variant
    seeds = list(guarded_seeds(a.seeds))
    base = json.load(open(f"reports/stage13/afm-device-{len(seeds)}.json", encoding="utf-8"))["per_episode"]
    rows = []
    log = open(f"data/stage15_loop_{v}.jsonl", "w", encoding="utf-8")
    acts_model, acts_code = collections.Counter(), collections.Counter()
    for seed in seeds:
        e = Ep(seed, shadow_bot=False, swap=False)
        mission = e.obs["mission"]
        tried = {}
        ep = {"seed": seed, "model_steps": 0, "code_steps": 0, "reduced_steps": 0, "a1_steps": 0, "a2_steps": 0, "clears": 0,
              "format_errors": 0}
        while not e.done:
            text = e.text()
            st = state_text(text, mission)
            opts = list(CHOICES)
            a1 = v in ("A1", "A3") and blocked_ahead(st)
            if a1:
                opts.remove(F)
            a1_opts = list(opts)
            a2 = False
            if v in ("A2", "A3"):
                t = tried.setdefault(text, set())
                left = [o for o in opts if o not in t]
                if not left:
                    t.clear()
                    ep["clears"] += 1
                    left = a1_opts
                a2 = len(left) < len(a1_opts)
                opts = left
            by_code = len(opts) == 1
            fe = False
            if by_code:
                c = opts[0]
            else:
                d = sc.score([st], opts)[0]
                c = pick(d, opts)
                fe = bool(d.get("format_error"))
            if v in ("A2", "A3"):
                tried[text].add(c)
            reduced = len(opts) < 3
            e.step(NAME_TO_ACT[c], choice=c, intervened=reduced)
            s = e.steps[-1]
            ep["code_steps" if by_code else "model_steps"] += 1
            ep["reduced_steps"] += reduced
            ep["a1_steps"] += a1
            ep["a2_steps"] += a2
            ep["format_errors"] += fe
            (acts_code if by_code else acts_model)[c] += 1
            log.write(json.dumps({"seed": seed, "step": len(e.steps) - 1, "mission": mission, "text": text, "options": opts,
                                  "action": c, "by_code": by_code, "a1": a1, "a2": a2, "moved": s["moved"], "pos": s["pos"],
                                  "dir": s["dir"], "target_visible": s["target_visible"], "format_error": fe}) + "\n")
        ep.update({"success": e.success, "timeout": e.timeout, "steps": len(e.steps), "bot_n": e.bot_n,
                   "within_2x": e.success and len(e.steps) <= 2 * e.bot_n, "visible_at_start": e.visible_at_start,
                   "blocked_forward": sum(s["policy"] == F and not s["moved"] for s in e.steps),
                   "no_rule_success": base[str(seed)]["end"] == "success",
                   "trace": "".join({L: "l", R: "r", F: "f"}[s["policy"]].upper() if s["intervened"] else
                                    {L: "l", R: "r", F: "f"}[s["policy"]] for s in e.steps)})
        rows.append(ep)
        print(seed, "ok" if e.success else "--", len(e.steps), ep["trace"][:70], flush=True)
    log.close()
    ok = [r for r in rows if r["success"]]
    tot = lambda k, sub=rows: sum(r[k] for r in sub)  # noqa: E731
    res = {"name": f"{v}-afm-device-{len(seeds)}", "variant": v, "seeds": a.seeds, "episodes": len(rows),
           "success": len(ok), "within_2x_bot": tot("within_2x"), "timeout": tot("timeout"),
           "visible_at_start": {"n": sum(r["visible_at_start"] for r in rows), "success": sum(r["visible_at_start"] for r in ok)},
           "unseen_at_start": {"n": sum(not r["visible_at_start"] for r in rows), "success": sum(not r["visible_at_start"] for r in ok)},
           "no_rule_success": tot("no_rule_success"),
           "saved": sorted(r["seed"] for r in ok if not r["no_rule_success"]),
           "broken": sorted(r["seed"] for r in rows if not r["success"] and r["no_rule_success"]),
           "steps_total": tot("steps"), "model_steps": tot("model_steps"), "code_steps": tot("code_steps"),
           "reduced_steps": tot("reduced_steps"), "a1_steps": tot("a1_steps"), "a2_steps": tot("a2_steps"), "clears": tot("clears"),
           "a2_steps_per_episode_mean": round(tot("a2_steps") / len(rows), 2),
           "blocked_forward_steps": tot("blocked_forward"), "format_error_steps": tot("format_errors"),
           "actions_model": dict(acts_model), "actions_code": dict(acts_code),
           "success_eps": {"steps": tot("steps", ok), "model_steps": tot("model_steps", ok), "code_steps": tot("code_steps", ok),
                           "reduced_steps": tot("reduced_steps", ok),
                           "eps_with_no_reduced_step": sum(r["reduced_steps"] == 0 for r in ok),
                           "eps_code_majority": sum(r["code_steps"] > r["model_steps"] for r in ok)},
           "scorer_stats": sc.stats(), "called": time.strftime("%Y-%m-%d"), "per_episode": rows}
    save(res["name"], res)
    print(json.dumps({k: x for k, x in res.items() if k != "per_episode"}, default=str))


def cmd_peers(a):
    lo, hi = (int(x) for x in a.seeds.split("-"))
    res = {}
    for stage, names in (("stage5", ["gemma", "gemma-reset", "jev", "jev-reset"]),
                         ("stage12", ["gemini-text", "gemini-text-reset", "clef-flash", "clef-flash-reset"])):
        for n in names:
            pe = json.load(open(f"reports/{stage}/{n}.json", encoding="utf-8"))["per_episode"]
            sub = {int(k): x for k, x in pe.items() if lo <= int(k) <= hi}
            ok = [x for x in sub.values() if x["end"] == "success"]
            res[n] = {"episodes": len(sub), "success": len(ok), "within_2x_bot": sum(x["steps"] <= 2 * x["bot"] for x in ok)}
    save("peers-same-100", res)
    print(json.dumps(res, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["samecheck", "a", "abonus", "loop", "peers"])
    ap.add_argument("--variant", choices=["A1", "A2", "A3"])
    ap.add_argument("--seeds", default="10000-10099")
    ap.add_argument("--app", default=stage13.APP)
    ap.add_argument("--eval", default="data/gotolocal_eval.jsonl")
    a = ap.parse_args()
    {"samecheck": cmd_samecheck, "a": cmd_a, "abonus": cmd_abonus, "loop": cmd_loop, "peers": cmd_peers}[a.cmd](a)


if __name__ == "__main__":
    main()
