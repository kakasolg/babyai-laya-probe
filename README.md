# babyai-laya-probe

단순한 기존 환경(BabyAI)에서 Laya 같은 작은 판단 모델이 관측과 지시를 받아
연속으로 알맞은 행동을 고르는지 확인한다. 알고 싶은 것은 "이 과제를 외웠는가"가 아니라
"작은 모델에 판단을 맡기는 접근이 어디까지 되는가"다.
BabyAI 결과를 DSR·트레이드·드론으로 확대 해석하지 않는다.

## 고정된 결정

- 과제: `BabyAI-GoToLocal-v0` 하나(8×8 방 하나, 물체 8개, 지시문 36가지 = 색·종류 18 × 관사 2). 목표는 특정 물체 하나가 아니라 색·종류 조건이다 — 맞는 물체 아무거나 앞에서 바라보면 성공(맞는 것이 2개 이상이면 관사 a). 환경은 수정하지 않는다.
  1단계의 `GoToObj`는 방에 물체가 늘 1개라 지시문을 안 읽어도 풀려서, 학습 전에 바꿨다(2026-11-14, MoKa 확인).
  GoToObj 덤프·보고(`reports/stage1.md`)는 남겨 두고 쓰지 않는다.
- 봇이 0·1·2 밖의 행동(3·4)을 낸 판은 통째로 학습에서 빼고 몇 판인지 적는다.
- 체크포인트: english `convaiinnovations/laya` 고정 리비전 `55cf4c4`, 별칭이 아니라 경로를 직접 넘긴다.
- 주 지표: 닫힌 루프 성공률. 맞는 물체가 2개 이상인 판(약 32 %)은 어느 쪽에 가도 성공이지만 봇은 하나만 골라서,
  걸음 단위 정확도는 낮게 나올 수 있다.
- 입력: **부분 관측(7×7)** + 방향 + 지시문. 모델과 비교 대상이 같은 정보를 본다. 전체 지도는 쓰지 않는다.
- 선택지: `turn left`(0) / `turn right`(1) / `forward`(2).
- 라벨: 전문가 봇(`minigrid.utils.baby_ai_bot.BabyAIBot`) 시범에서만. LLM이 추측한 행동은 정답으로 쓰지 않는다.
- seed: 학습 0~999, **개발용 평가 10000~10299**, **최종 확인용 20000~20299**. 섞지 않는다.
  10000~10299는 3단계부터 실패 사례를 보고 방법을 고르는 데 쓰고 있으므로 개발용이다(2026-11-14).
  **seed 20000~20299는 11-15에 6단계 최종 확인으로 한 번 썼다**(`reports/stage6.md`, 선언은 `reports/stage6_prereg.md`).
  앞으로 방법을 고르는 데 쓰지 않고, 새 최종 확인이 필요하면 새 범위를 정한다. `dump_demos`·`closed_loop`·`stage5`는
  이 범위를 다시 거부한다(실행 때만 쓴 `--use-final-seeds` 플래그는 지웠다).
- 모든 정책 표에 "봇 걸음 수의 2배 안에 성공한 비율"을 함께 적는다(64걸음 제한이 무작위를 띄우므로).
- 비교 대상: 무작위, 늘 전진, 전문가 봇.
- 첫 평가: 닫힌 루프 성공률과 대표 실패 사례. 속도 최적화는 뒤로.
- 범위 밖: 범용 프레임워크, 강화학습, 음성 입력, 온라인 재학습, 다른 분야 어댑터.
- 경계: 모델은 `choose(state_text, mission, choices) -> choice`만 한다. 환경 실행·관측→글 변환은 밖에 있다.

## 관측 → 글 (`probe/obs_text.py`)

에이전트 기준 상대 위치. 빈칸·안 보이는 칸은 쓰지 않는다. 지시문은 쓰지 않는다(따로 붙인다).

```
facing: south
blue key: 2 ahead
walls: 3 ahead, 2 right
```

- 1줄: `facing: east|south|west|north` (`obs["direction"]`).
- 벽이 아닌 물체마다 한 줄, 가까운 것부터: `<색> <종류>: N ahead, M left|right`. 0인 쪽은 뺀다.
  `1 ahead` = 바로 앞 칸(GoTo 성공 위치).
- **대상이 시야에 없을 때**: 대상 줄이 없을 뿐 따로 표시하지 않는다(어느 줄이 대상인지 글에 적지 않음 — 지시문과 맞춰 보는 건 모델 몫).
  물체가 하나도 안 보이면 `objects: none in view`.
- 같은 색·종류 물체가 여럿 보이면 각각 한 줄.
- **벽**: 에이전트에서 곧게 뻗은 세 줄(앞·왼쪽·오른쪽)에서 가장 가까운 벽 칸까지 거리만:
  `walls: 3 ahead, 2 left`. 벽이 안 보이는 줄은 빼고, 셋 다 없으면 `walls: none in line`.
  모서리·대각선 쪽 벽은 적지 않는다.
- 좌표: `image[i, j]`, 에이전트는 (3, 6), 앞 = `6 - j`, 옆 = `i - 3`. MiniGrid `get_view_coords`와 200개 seed에서 대조해 불일치 0.

Laya에 줄 상태는 `mission: <지시문>\n` + 위 글(`probe/laya_rows.py`).

## 실행법

학습·실험은 WSL Ubuntu(RTX 5080)에서, venv는 저장소 밖 `~/babyai-laya-venv`(Python 3.12).

```bash
uv venv ~/babyai-laya-venv --python 3.12
VIRTUAL_ENV=~/babyai-laya-venv uv pip install -r requirements.txt
cd /mnt/d/dev/kotlin-prj/baby-ai-laya-probe
PY=~/babyai-laya-venv/bin/python
$PY -m probe.measure_env                                   # 1단계: 클라우드 숫자 재측정 → reports/env_check.json
$PY -m probe.dump_demos --seeds 0-999 --out data/gotolocal_train.jsonl   # + .summary.json (봇 성공·뺀 판)
$PY -m probe.text_stats data/gotolocal_train.jsonl --tokenizer <체크포인트>/tokenizer
$PY -m probe.laya_dryrun data/gotolocal_train.jsonl        # Laya 형식 검사·토큰 길이(학습 없음, 가중치 안 받음)
```

`data/`(시범 덤프)·체크포인트는 git에 넣지 않는다. 덤프는 seed로 다시 만든다.

## 단계

1. (완료) 저장소·재측정·시범 덤프·관측→글·Laya 설치와 형식 확인 — `reports/stage1.md` (GoToObj)
2. a (완료) GoToLocal로 덤프·통계·표본·dry_run — `reports/stage2a.md`
   b (완료) 최소 미세조정과 걸음 단위 정확도(평가 seed), 순서 뒤집기 민감도 — `reports/stage3.md`
3. (완료) 닫힌 루프: 평가 seed 300판 성공률, 비교 대상 셋과 나란히, 대표 실패 사례 — `reports/stage3.md`
   3.5 학습 seed 1·2, 실패 A/B/C, 전진 막힘 탈출 장치(평가만), 지시문 바꿔치기, 시범 분석 — `reports/stage3_5.md`
   ```bash
   $PY -m probe.dump_demos --seeds 10000-10299 --out data/gotolocal_eval.jsonl --keep-all
   $PY -m probe.finetune data/gotolocal_train.jsonl --seed 0          # → ~/babyai-laya-ft/gotolocal-s0
   $PY -m probe.step_eval data/gotolocal_eval.jsonl --model ~/babyai-laya-ft/gotolocal-s0
   $PY -m probe.closed_loop --policy random|forward|bot --name <tag>
   $PY -m probe.closed_loop --policy model --model ~/babyai-laya-ft/gotolocal-s0 [--mask] --name <tag>
   ```
4. (만듦, MoKa가 돌림) 한 걸음씩 멈추고 키보드로 모델 선택을 확인·교정하는 루프(교정은 기록만) — `reports/stage4.md`, 아래 "교정 루프"
5. 닫힌 루프 세 갈래(Laya · Jev · Gemma 12B)와 "안 해본 행동" 규칙 R — `reports/stage5.md`, 아래 "5단계"
6. 최종 확인(seed 20000~20299, 선언 뒤 한 번) — `reports/stage6_prereg.md`, `reports/stage6.md`
7. GoToLocal 한 장 정리 — **`reports/summary_gotolocal.md`** (처음 읽는 사람은 여기부터)
8. 다음 과제 `BabyAI-PickupDist-v0`(선택지에 `pick up` 추가) — 8a 살펴보기(학습 없음): `reports/stage8a.md`, `python -m probe.stage8a`.
   seed: 학습 0~999, 개발용 10000~10299, 최종 30000~30299(8d 선언 전엔 거부).
   8b 학습 · 8c 닫힌 루프(개발용 300판): `reports/stage8.md`. WSL에서
   `python -m probe.stage8 train --seed 0` → `stepeval --model ~/babyai-laya-ft/pickupdist-s0 --name s0`
   → `loop --policy none|reset|bot|random --model … --name laya-s0 [--base reports/stage8/laya-s0.json]`.

각 단계는 MoKa 확인 뒤 하나씩 진행한다.

## 교정 루프 (4단계) — MoKa가 칠 명령

**WSL Ubuntu 터미널**에서 친다(venv를 따로 켤 필요 없이 venv의 python을 바로 부름):

```bash
cd /mnt/d/dev/kotlin-prj/baby-ai-laya-probe && HF_HUB_OFFLINE=1 ~/babyai-laya-venv/bin/python -m probe.correct_loop
```

Windows PowerShell에서 친다면 같은 줄을 `wsl -d Ubuntu -- bash -lc '…'` 안에 넣는다.
기본은 세 모델이 모두 실패한 12판(A → B → C 순), seed 0 모델, 막힘 탈출 장치 꺼짐.
12판은 성능을 대표하는 평가 세트가 아니라 반복 실패를 진단하는 사례 모음이다.
유형: A 현재 입력에 단서가 있는데 잘못 선택 · B 대상이 안 보이는 상태에서 탐색 반복(기억 부족 가능성, 단정 안 함) · C 현재 자료로 원인 미분류.
`--seeds 10014,10017`로 다른 판, `--window`로 MiniGrid 창도 같이(WSLg에서 열림 확인, 글자 화면만으로도 끝까지 쓸 수 있음).
기록은 `data/correct_log.jsonl`(git 밖)에 걸음마다 한 줄 이어 붙는다. 평가용 20000~20299는 거부.

| 입력 (치고 Enter) | 하는 일 |
|---|---|
| (그냥 Enter) | 모델 선택대로 한 걸음 |
| `a` / `d` / `w` | 왼쪽 돌기 / 오른쪽 돌기 / 전진으로 바꿔 한 걸음 (= 교정, 기록만) |
| `b` | 봇이 고를 행동 보기 (기본은 숨김) |
| `m` → `1`~`4` | 이 걸음에 메모: 1 입력에 답이 있는데 모델이 틀림 · 2 입력에 정보가 없음 · 3 글이 헷갈리게 적힘 · 4 기타(한 줄 글) |
| `r` | 이 판 끝까지 모델대로, 멈추지 않음 |
| `n` / `q` | 다음 판 / 그만두기 |

화면 예시 (seed 10014, 걸음 6 — 벽에 막혔는데 모델이 전진을 고르는 곳):

```
걸음 6 / 최대 64   지시문: go to the purple ball
########################
### .  .  .  .  Ex . ###
### .  .  Pk Ex .  . ###
### .  Yo .  .  .  . ###
### .  Rx .  .  .  . ###
### .  .  .  Yx .  . ###
### v :Yx:Po :  .  . ###
########################
범례: R/G/B/P/Y/E = 빨/초/파/보/노/회색, o 공 · k 열쇠 · x 상자, ':' = 모델 시야(7×7) 안, '.' = 시야 밖
사람은 방 전체를 보지만 모델은 아래 글만 본다:
  mission: go to the purple ball
  facing: south
  yellow box: 1 left
  purple ball: 2 left
  walls: 1 ahead, 1 right
모델 점수: turn left 0.19 · turn right 0.18 · forward 0.63   → 모델 선택: forward
[Enter 모델대로 | a 왼 d 오 w 전진 | b 봇 | m 메모 | r 끝까지 | n 다음 판 | q 그만] >
```

`v`는 에이전트(남쪽을 봄). 남쪽을 보면 왼쪽이 동쪽이라 `yellow box: 1 left`가 바로 오른편 칸에 그려진다.

## 게임으로 보기 (`godot/`, Godot 4.7)

글자 화면 대신 그림으로 보는 뷰어 겸 게임. 재학습·평가와는 무관하고, 3단계 모델(seed 0)의 걸음을 다시 보여 줄 뿐이다.

1. 리플레이 내보내기 (WSL, 한 번만): dev seed 10000~10029 + 세 모델 모두 실패한 12판, 모두 35판.
   ```bash
   cd /mnt/d/dev/kotlin-prj/baby-ai-laya-probe && HF_HUB_OFFLINE=1 ~/babyai-laya-venv/bin/python -m probe.export_godot
   ```
   → `godot/data/episodes.json` (git에 안 넣음)
   - 만들려면 WSL venv(`~/babyai-laya-venv`: minigrid 3.2.0, laya 0.4.31), 저장소 밖 체크포인트 `~/babyai-laya-ft/gotolocal-s0`, GPU가 필요하다.
     체크포인트가 없는 곳에선 다시 만들 수 없다.
2. 실행 (Windows):
   ```
   D:\dev\tools\godot\Godot_v4.7.2-stable_win64.exe --path D:\dev\kotlin-prj\baby-ai-laya-probe\godot
   ```

게임 화면 글은 영어다(2026-11-14, 웹 빌드에서 한글 글꼴이 깨져서 바꿨고 **데스크톱도 같이 바뀜**). 아래의 모드 이름은 화면 위쪽 스위치에서 Play yourself / Watch Laya / Correct.
그냥 실행하면 첫 화면에서 "Try it yourself"(직접 해보기)와 "See Laya get stuck"(아래 실패 장면) 중 하나를 고른다. 명령줄 인자(`--seed` 등)를 주면 첫 화면을 건너뛴다.
"Stuck example" 버튼은 seed 10014 걸음 6(모델이 벽 앞에서 전진을 반복하기 시작하는 곳)의 기록 재생으로 바로 간다.

- **직접 해보기**: 같은 방을 같은 세 가지 행동(←/→ 돌기, ↑ 전진)으로 걸어 본다. V로 보기 방식을 바꾼다: 시야만 → 글만(AI와 같은 조건) → 방 전체. 끝나면 AI·봇 걸음 수와 비교하고, Enter로 같은 판의 AI 관전으로 넘어간다.
- **AI 관전**: 걸음마다 AI가 받은 글, 세 선택지 점수, 봇의 선택(다르면 주황색)을 보여 준다. 지나간 길과 같은 칸을 3번 이상 밟은 횟수(노란 ×n)를 그린다.
- 점검: `Godot_v4.7.2-stable_win64_console.exe --headless --path godot -- --selftest` — 내보낸 944걸음을 게임 규칙으로 다시 걸어 위치·결과·입력 글이 Python 쪽과 모두 같은지 확인한다(현재 불일치 0).
- **교정** (4단계 교정 루프를 게임 안에서): 세 모델이 모두 실패한 12판을 Laya가 **실시간으로** 한 걸음씩 고른다.
  - Enter = AI대로 · ←/→/↑ = 다른 행동으로 바꿔 한 걸음(교정) · B = 봇 선택 보기 · 1~4 = 이 걸음 메모 · R = 끝까지 AI대로 · N = 다음 판
  - Laya는 WSL에서 `probe/correct_server.py`(127.0.0.1:18799)로 돈다. 교정 모드에 처음 들어가면 게임이 `probe/run_correct_server.sh`로 직접 켠다(콘솔 창이 하나 뜨고, 모델 읽느라 20~40초). 게임 창을 닫으면 서버도 끈다.
  - 기록은 글자판 교정 루프와 같은 `data/correct_log.jsonl`, 같은 형식에 `"source": "game"`이 붙는다. 교정은 기록만 하고 학습엔 안 쓴다. 막힘 탈출 장치 꺼짐, 20000~20299 거부.

## 5단계 — 학습 없는 모델(Jev·Gemma)에 주는 설명 (확정본, 2026-11-14)

Jev·Gemma를 부르기 전에 확정했다. 결과를 본 뒤 고치지 않는다. 코드의 `probe/stage5.py` `EXPLAIN`과 글자 하나까지 같다.
두 모델에 같은 글을 준다. Jev는 `instructions`에 이 글, `state`에 상태 글, `criteria`는 `turn left / turn right / forward`(설명 없음).
Gemma(`gemma4:12b-it-q8_0`)는 이 글 + `[Observation]` 상태 글 + `[Actions]` 1~3 번호 + `Answer with one digit only.`
상태 글 = Laya가 받는 것 그대로(`mission: …` 줄 + 관측 글). 규약 줄은 `probe/obs_text.py`의 실제 동작에서 옮겼다.

```text
You control an agent in a grid room. Choose exactly one action using only the
current observation and the mission.

turn left / turn right: rotate 90 degrees in place, no movement.
forward: move one cell ahead. It does nothing if that cell holds a wall or an object.

The mission succeeds when an object matching the mission's color and type is in the
cell directly ahead of the agent. Any matching object counts.

The observation lists only what is inside the agent's limited forward view.
Cells that are not listed as objects or walls and are in view are empty.
Anything outside the view is unknown, not empty.

How to read the observation:
- "facing: east" is the compass direction the agent faces. All other positions are relative to the agent.
- The view covers the agent's own row and the 6 rows ahead, 3 cells to each side. Cells behind a wall are not seen.
- "<color> <type>: 2 ahead, 1 left" means that object is 2 cells forward and 1 cell to the left of the agent.
  A zero part is left out: "3 right" means the same row as the agent, 3 cells to the right.
- "X: 1 ahead" (no left/right part) means X is in the cell directly in front, so forward is blocked.
  If X matches the mission, the mission is already met.
- Objects are listed nearest first. "objects: none in view" means no object is visible.
- "walls: 4 ahead, 1 left" gives the distance to the nearest wall on the three straight lines from the agent
  (ahead, left, right); a line with no visible wall is left out, "walls: none in line" if none.
  "walls: 1 ahead" means a wall is directly in front, so forward is blocked. Walls off these lines are not listed.
```

```bash
$PY -m probe.stage5 loop --scorer laya --model ~/babyai-laya-ft/gotolocal-s0 --name laya-s0 [--rule --base reports/stage5/laya-s0.json]
$PY -m probe.stage5 stepcheck --scorer gemma            # Jev: JEV_MODEL=jev-1.14.0, 키는 환경변수 TYPESAFE_API_KEY
$PY -m probe.stage5 loop --scorer gemma --name gemma [--rule --base reports/stage5/gemma.json]
# 변형(보드 11-14 20:29): --policy R | reset | penalty(Laya만), 예: --name laya-s0-reset --policy reset --base reports/stage5/laya-s0.json
$PY -m probe.stage5_blocked                                # 앞 칸이 막힌 걸음의 forward 1순위 비율(캐시만 씀)
```

## 게임 웹 빌드

- 2026-11-14 itch.io에 공개: https://mokaflow.itch.io/babyai-laya-an-ai-in-the-room (HTML, 1320×860, 업로드는 아래 ZIP을 손으로).
- 범위: Play yourself + 기록된 Laya 재생(Watch Laya)만. 웹에선 Correct(교정) 모드가 숨겨지고 들어갈 수 없다 — 추론 서버(WSL·Python·GPU)가 브라우저에 없다.
- 프리셋 `godot/export_presets.cfg`: Web, 스레드 없음(교차 출처 격리 헤더 불필요), `data/*.json` 포함. Godot 4.7.2 공식 export templates의 web 템플릿이 필요하다.
- 내보내기: `Godot_v4.7.2-stable_win64_console.exe --headless --path godot --export-release "Web" <빌드 폴더>/index.html`
- 확인한 대상은 데스크톱 키보드·마우스(Chromium 계열). 모바일은 아직 지원하지 않는다.
- 엔진 라이선스 고지: `Godot_v4.7.2-stable_win64_console.exe --headless --script tools/gen_godot_licenses.gd -- <빌드 폴더>/licenses.txt`
  (게임의 웹 전용 "Licenses" 버튼이 같은 폴더의 `licenses.txt`를 연다). itch.io ZIP = 빌드 폴더의 파일 10개를 폴더 없이 그대로.
- 웹 빌드에서 막아 둔 것: Correct 모드 진입, 프로세스 실행(`_start_server`), 로컬 추론 서버 요청(`_fix_get`) — 모두 `web` 검사로 빠져나간다.
- 기록 데이터 `godot/data/episodes.json`과 출처 `godot/data/PROVENANCE.md`만 git에 들어간다(나머지 `data/`는 제외).
  `probe/export_godot.py`는 파일에 로컬 경로 대신 체크포인트 이름(`babyai-laya-ft/gotolocal-s0`)을 쓴다.
