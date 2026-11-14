"""Stage 4: step-by-step check-and-correct loop. Corrections are only logged, never trained on.

Usage (WSL):
  python -m probe.correct_loop [--seeds 10014,10016] [--model ~/babyai-laya-ft/gotolocal-s0] [--window]
Default episodes: the 12 dev seeds all three stage-3.5 models failed, ordered A -> B -> C (seed 0 classes).
Seeds 20000-20299 are refused (final check).

Each step waits for one line of input (type the key, then Enter):
  (empty)  take the model's choice          a / d / w   turn left / turn right / forward instead (= correction)
  b        show the bot's choice            m           memo for this step (1/2/3/4)
  r        model to the end, no stops       n           next episode         q   quit
The escape rule from stage 3.5 is OFF here. Log: data/correct_log.jsonl (one line per step).
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import pathlib
import sys

import gymnasium as gym
import minigrid  # noqa: F401
from minigrid.utils.baby_ai_bot import BabyAIBot

from probe.laya_model import Chooser
from probe.laya_rows import state_text
from probe.obs_text import ACTIONS, CHOICES, obs_to_text
from probe.text_stats import categorize

ENV_ID = "BabyAI-GoToLocal-v0"
KEY_TO_CHOICE = {"a": "turn left", "d": "turn right", "w": "forward"}
NAME_TO_ACT = {v: k for k, v in ACTIONS.items()}
MEMOS = {"1": "입력에 답이 있는데 모델이 틀림", "2": "입력에 정보가 없음", "3": "글이 헷갈리게 적힘", "4": "기타"}
COLOR = {"red": "R", "green": "G", "blue": "B", "purple": "P", "yellow": "Y", "grey": "E"}
TYPE = {"ball": "o", "key": "k", "box": "x"}
ARROW = ">v<^"


def default_seeds() -> list[int]:
    """12 seeds failed by all of model-s0/s1/s2 (stage 3.5), A -> B -> C by the seed-0 class."""
    runs = [json.load(open(f"reports/stage3_5/model-s{s}.json", encoding="utf-8")) for s in range(3)]
    failed = [{k for k, v in r["per_episode"].items() if not v[0]} for r in runs]
    common = set.intersection(*failed)
    cls = {str(f["seed"]): f for f in runs[0]["failures"]}
    return [int(s) for s in sorted(common, key=lambda s: (cls[s]["class"], int(s)))]


def failure_note(seed: int) -> str:
    try:
        r = json.load(open("reports/stage3_5/model-s0.json", encoding="utf-8"))
    except FileNotFoundError:
        return "(분류 기록 없음)"
    for f in r["failures"]:
        if f["seed"] == seed:
            return (f"seed 0 모델 기준 유형 {f['class']} ({f['why']}), 반복 시작 걸음 {f['loop_start']}"
                    + (f", 주기 {f['period']}" if f["period"] else ", 반복 없음(헤맴)"))
    return "seed 0 모델은 이 판을 성공함" if str(seed) in r["per_episode"] else "(3.5단계에서 안 돌린 판)"


def grid_text(u) -> str:
    """Whole room as text. In-view cells (the agent's 7x7 partial view) are marked with ':' padding."""
    lines = []
    for y in range(u.height):
        row = ""
        for x in range(u.width):
            cell = u.grid.get(x, y)
            vis = u.in_view(x, y)
            if (x, y) == tuple(int(v) for v in u.agent_pos):
                s = f" {ARROW[u.agent_dir]} "
            elif cell is None:
                s = " : " if vis else " . "
            elif cell.type == "wall":
                s = "###"
            else:
                c = f"{COLOR.get(cell.color, '?')}{TYPE.get(cell.type, '?')}"
                s = f":{c}" if vis else f" {c}"
            row += s
        lines.append(row)
    lines.append("범례: R/G/B/P/Y/E = 빨/초/파/보/노/회색, o 공 · k 열쇠 · x 상자, ':' = 모델 시야(7×7) 안, '.' = 시야 밖")
    return "\n".join(lines)


def clone(env):
    """Deep copy of the unwrapped env without its pygame window/clock (those cannot be copied)."""
    u = env.unwrapped
    saved = (getattr(u, "window", None), getattr(u, "clock", None))
    u.window, u.clock = None, None
    try:
        return copy.deepcopy(u)
    finally:
        u.window, u.clock = saved


def bot_choice(env):
    """Ask a fresh bot from the current state (on a copy, so the real episode is untouched)."""
    try:
        return ACTIONS.get(int(BabyAIBot(clone(env)).replan()), "other")
    except Exception as ex:  # noqa: BLE001
        return f"bot_error:{type(ex).__name__}"


def bot_finishes(env, reset_budget: bool = False) -> bool:
    """Reliability check: does a fresh bot, started from this state, finish the episode alone?
    reset_budget=True gives it a full max_steps budget (separates 'no steps left' from 'bot fails')."""
    u = clone(env)
    if reset_budget:
        u.step_count = 0
    bot = BabyAIBot(u)
    last = None
    while True:
        a = int(bot.replan(last))
        _, r, term, trunc, _ = u.step(a)
        last = a
        if term or trunc:
            return bool(term and r > 0)


def read_line(prompt: str, script: list[str] | None) -> str:
    if script is not None:
        line = script.pop(0) if script else "q"
        print(prompt + line)
        return line.strip()
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def play(seed: int, chooser: Chooser, log, script, window: bool) -> str:
    env = gym.make(ENV_ID, render_mode="human" if window else None)
    obs, _ = env.reset(seed=seed)
    u = env.unwrapped
    d = u.instrs.desc
    target = {"type": d.type, "color": d.color}
    print("\n" + "=" * 72)
    print(f"seed {seed} · {obs['mission']} · {failure_note(seed)}")
    rows, step, auto, result = [], 0, False, None
    while result is None:
        if window:
            try:
                env.render()
            except Exception as ex:  # noqa: BLE001
                print(f"(창 그림 실패, 글자만 씀: {type(ex).__name__})")
                window = False
        text = obs_to_text(obs["image"], obs["direction"])
        (choice, probs), = chooser.choose_batch([text], [obs["mission"]])
        bot = bot_choice(env)
        row = {"seed": seed, "step": step, "mission": obs["mission"], "input": state_text(text, obs["mission"]),
               "probs": probs, "model_choice": choice, "bot_choice": bot, "memo": None,
               "target_visible": not categorize({"image": obs["image"], "target": target,
                                                 "n_matching": len(d.obj_poss)})["target_unseen"]}
        taken = choice
        if not auto:
            print("\n" + "-" * 72)
            print(f"걸음 {step} / 최대 {u.max_steps}   지시문: {obs['mission']}")
            print(grid_text(u))
            print("사람은 방 전체를 보지만 모델은 아래 글만 본다:")
            print("  " + state_text(text, obs["mission"]).replace("\n", "\n  "))
            print("모델 점수: " + " · ".join(f"{c} {probs.get(c, 0):.2f}" for c in CHOICES) + f"   → 모델 선택: {choice}")
            while True:
                k = read_line("[Enter 모델대로 | a 왼 d 오 w 전진 | b 봇 | m 메모 | r 끝까지 | n 다음 판 | q 그만] > ", script)
                if k == "":
                    break
                if k in KEY_TO_CHOICE:
                    taken = KEY_TO_CHOICE[k]
                    break
                if k == "b":
                    print(f"  봇 선택: {bot}")
                elif k == "m":
                    mk = read_line("  메모 1 답이 있는데 틀림 / 2 정보 없음 / 3 글이 헷갈림 / 4 기타 > ", script)
                    if mk in MEMOS:
                        row["memo"] = {"code": int(mk), "label": MEMOS[mk]}
                        if mk == "4":
                            row["memo"]["note"] = read_line("  한 줄 메모 > ", script)
                        print(f"  메모 저장: {row['memo']['label']}")
                    else:
                        print("  (1~4가 아니라서 저장 안 함)")
                elif k == "r":
                    auto = True
                    break
                elif k in ("n", "q"):
                    result = "skipped" if k == "n" else "quit"
                    break
                else:
                    print("  (모르는 키)")
            if result is not None:
                break
        row.update({"taken": taken, "corrected": taken != choice})
        rows.append(row)
        obs, reward, term, trunc, _ = env.step(NAME_TO_ACT[taken])
        step += 1
        if term or trunc:
            result = "success" if term and reward > 0 else "timeout"
    env.close()
    for r in rows:
        r["episode_result"] = result
        r["logged_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        log.write(json.dumps(r, ensure_ascii=False) + "\n")
    log.flush()
    n_corr = sum(r["corrected"] for r in rows)
    print(f"\n>>> seed {seed}: {result}, 걸음 {len(rows)}, 교정 {n_corr}, 메모 {sum(r['memo'] is not None for r in rows)}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=None, help="comma list; default = the 12 all-model failures")
    ap.add_argument("--model", default=os.path.expanduser("~/babyai-laya-ft/gotolocal-s0"))
    ap.add_argument("--log", default="data/correct_log.jsonl")
    ap.add_argument("--window", action="store_true", help="also open the MiniGrid window (if a display works)")
    ap.add_argument("--script", default=None, help="file with pre-written key lines (self-check)")
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else default_seeds()
    if any(20000 <= s < 20300 for s in seeds):
        raise SystemExit("20000-20299 are reserved for the final check (README)")
    script = open(a.script, encoding="utf-8").read().split("\n") if a.script else None
    print(f"판 {len(seeds)}개: {seeds}\n모델: {a.model} (막힘 탈출 장치 꺼짐)\n기록: {a.log}")
    chooser = Chooser(a.model)
    pathlib.Path(a.log).parent.mkdir(parents=True, exist_ok=True)
    with open(a.log, "a", encoding="utf-8") as log:
        for s in seeds:
            if play(s, chooser, log, script, a.window) == "quit":
                break
            if script is None and s != seeds[-1]:
                if read_line("Enter 다음 판 / q 그만 > ", None) == "q":
                    break
    sys.exit(0)


if __name__ == "__main__":
    main()
