# babyai-laya-probe

단순한 기존 환경(BabyAI)에서 Laya 같은 작은 판단 모델이 관측과 지시를 받아
연속으로 알맞은 행동을 고르는지 확인한다. 알고 싶은 것은 "이 과제를 외웠는가"가 아니라
"작은 모델에 판단을 맡기는 접근이 어디까지 되는가"다.
BabyAI 결과를 DSR·트레이드·드론으로 확대 해석하지 않는다.

## 고정된 결정

- 과제: `BabyAI-GoToLocal-v0` 하나(8×8 방 하나, 물체 8개, 지시문 36가지). 환경은 수정하지 않는다.
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
  20000~20299는 덤프도 평가도 하지 않고 최종 확인 때 한 번만 쓴다(`closed_loop.py`가 거부함).
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
5. 실패하면 작은 비교 하나씩: 입력 정보, 글 표현, 데이터 양, 모델

각 단계는 MoKa 확인 뒤 하나씩 진행한다.

## 교정 루프 (4단계) — MoKa가 칠 명령

**WSL Ubuntu 터미널**에서 친다(venv를 따로 켤 필요 없이 venv의 python을 바로 부름):

```bash
cd /mnt/d/dev/kotlin-prj/baby-ai-laya-probe && HF_HUB_OFFLINE=1 ~/babyai-laya-venv/bin/python -m probe.correct_loop
```

Windows PowerShell에서 친다면 같은 줄을 `wsl -d Ubuntu -- bash -lc '…'` 안에 넣는다.
기본은 세 모델이 모두 실패한 12판(A → B → C 순), seed 0 모델, 막힘 탈출 장치 꺼짐.
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
