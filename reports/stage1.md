# 1단계 보고 (2026-11-13, Host: Moka-Windows-Dev, WSL Ubuntu)

환경: WSL2 Ubuntu, Python **3.12.3**(클라우드는 3.13), minigrid 3.2.0, gymnasium 1.4.0, numpy 2.5.4,
GPU RTX 5080(이번 단계에선 안 씀). 원자료: `env_check.json`, `text_stats.json`, `laya_dryrun.json`.

## 1. 한 것 / 안 한 것

| 한 것 | 안 한 것 (확인 안 함) |
|---|---|
| 클라우드 숫자 재측정 (`probe/measure_env.py`) | Laya 학습·추론 (가중치 로드 자체를 안 함) |
| 시범 덤프 seed 0~999 → 4,915줄 (`probe/dump_demos.py`, `data/`는 git 밖) | 평가 seed 10000~10299 덤프 |
| 관측→글 (`probe/obs_text.py`), 좌표를 MiniGrid `get_view_coords`와 200 seed 대조(불일치 0) | 제로샷 정확도 |
| Laya 0.4.31 설치, 0.4.1 휠과 소스 비교, `laya.train.dry_run`(토크나이저만 받음) | Python 3.13에서 재측정 |

## 2. 재측정 vs 클라우드 — 모두 같음

| 항목 | 클라우드 | 여기 |
|---|---|---|
| 봇 성공 seed 0~299 (GoToRedBallGrey · GoToObj · GoToLocal · Open) | 300/300 ×4, 예외 0 | 300/300 ×4, 예외 0 |
| GoToObj 평균/최대 걸음 (seed 0~299) | 5.0 / 13 | 4.97 / 13 |
| max_steps · 방 | 64 · 8×8 하나 | 64 · 8×8 하나 |
| 지시문 종류 (seed 0~999) | 18 | 18 |
| 봇 행동 | 0·1·2만 | 0·1·2만 (0: 694, 1: 967, 2: 3,254) |
| 관측 · 행동 공간 | 7×7×3, Discrete(7) | 7×7×3, Discrete(7) |
| 같은 (image, mission)에 행동 갈림 (seed 0~999) | 4.3 % / 4,915걸음 | **4.31 %** / 4,915걸음 |
| Open | 22×22 방 9개, 평균 32, 최대 156 | 22×22 방 9개, 평균 32.25, 최대 156 |

Open·GoToLocal 등은 "Sampling rejected: unreachable object" 로그가 나오지만 환경 생성 중 재표집 메시지이고 예외 아님.

## 3. 같은 입력에 봇 행동이 갈리는 비율 (seed 0~999, 4,915걸음)

| 키 | 서로 다른 키 | 갈리는 걸음 비율 | 다수결 기억없는 정책의 최소 오류 |
|---|---|---|---|
| image + mission (클라우드와 같은 기준) | 3,429 | 4.31 % | 1.57 % |
| image + direction + mission | 4,438 | 1.59 % | 0.75 % |
| **글 + mission** (방향 포함) | **4,438** | **1.59 %** | **0.75 %** |

- 글은 (image, direction)의 함수이고 서로 다른 키 수가 같으므로, 이 데이터에서는 **글로 바꾸며 잃은 구분이 없음**.
  4.31 → 1.59 %로 준 건 글 때문이 아니라 방향(`facing`)을 넣었기 때문.
- 대상이 시야에 없는 걸음은 17.9 %(882걸음)이고, 여기서 갈림이 8.8 %로 몰림 — 봇은 이미 본 칸을 기억해 탐색하므로 기억 없는 모델은 이 부분에서 봇과 다를 수밖에 없음.
- 걸음 단위 정확도의 이론상 상한(학습 데이터 기준) ≈ 99.25 %. 평가 seed에서는 처음 보는 키가 있어 더 낮을 것(추정).

## 4. 입력 글 표본 10개 (rng 0, 대상 안 보임 4 + 보임 6)

| seed·걸음 | mission | 글 (줄바꿈 → ` / `) | 봇 |
|---|---|---|---|
| 973·1 | go to the blue key | facing: north / objects: none in view / walls: 3 ahead, 2 left | turn right |
| 454·0 | go to the blue ball | facing: east / objects: none in view / walls: 3 ahead, 2 left | turn right |
| 870·0 | go to the grey ball | facing: west / objects: none in view / walls: 5 ahead, 2 right | turn left |
| 494·0 | go to the red ball | facing: south / objects: none in view / walls: 1 ahead, 3 left | turn right |
| 39·3 | go to the blue key | facing: south / blue key: 2 ahead / walls: 3 ahead, 2 right | forward |
| 261·5 | go to the purple ball | facing: south / purple ball: 2 right / walls: 1 ahead, 3 right | turn right |
| 984·5 | go to the purple box | facing: south / purple box: 3 left / walls: 2 ahead, 1 right | turn left |
| 515·1 | go to the blue box | facing: east / blue box: 4 ahead, 2 left / walls: 6 ahead, 2 right | forward |
| 492·3 | go to the purple ball | facing: north / purple ball: 3 ahead, 3 left / walls: 5 ahead, 1 right | forward |
| 415·8 | go to the red ball | facing: north / red ball: 3 ahead / walls: 5 ahead, 1 right | forward |

갈리는 키 예 (모두 대상 안 보임): `facing: west / objects: none in view / walls: 6 ahead, 2 left` + "go to the blue key" → 왼쪽 1 · 오른쪽 1 · 전진 1.

## 5. 글 길이 (Laya 토크나이저, 4,915행)

| 체크포인트 | 상태(`mission:` 줄 + 글) 중앙/최대 | 모델 전체 입력(지시·선택지 3개 포함) 중앙/최대 | 체크포인트 max_len |
|---|---|---|---|
| english (ModernBERT-large) | 25 / 29 | 86 / 90 | 512 |
| multilingual (mmBERT-base) | 28 / 32 | 93 / 97 | 1024 |

잘림 없음. 전체 입력의 약 70 %가 지시문·선택지 설명(템플릿) — 길이를 줄일 여지는 템플릿 쪽(속도는 뒤로 미룸).

## 6. Laya 0.4.31 — 0.4.1 대비

- **`laya/train.py`·`train_cli.py`는 0.4.1과 바이트 단위로 같음.** `finetune(data, model_dir, output_dir, config=None, device="auto")`,
  `TrainConfig` 필드·기본값(epochs 4, micro_batch 8 × grad_accum 8, loss `rlcd`, `shuffle_options`, `label_smoothing` …),
  데이터 형식 `{state, questions, expected}` / `{state, questions, gold}` 모두 그대로. VersionSandbox `train_laya.py` 호출 방식이 그대로 통함.
- `dry_run`: 4,915행 모두 유효, 건너뜀 0, 학습 4,515 / 보정 400, 4 epoch 284 업데이트(english·multilingual 같음).
- 바뀐 것(학습 경로 밖이거나 영향 작음):
  - `common.py`: 추론 `batch_size` 검증, CPU fp32 무기울기 추론용 머리 빠른 경로 — 학습 중엔 안 탐.
  - `revisions.py`: `revision=`·`LAYA_REVISION` 처리 정리, 다이제스트 경로 검사 강화.
  - 새 모듈: `policy`, `vega`, `video`, `_agreement`, `evals_tournament`, 통합 `agno`·`tools`. 새 의존성 `vegaml`, `cryptography`.
  - Router 기본값이 0.4.0부터 multilingual(주석). 이 저장소는 Router를 안 쓰고 체크포인트를 직접 지정.
- 설치된 것: torch **2.15.0+cu132**(CUDA 사용 가능 확인), transformers 5.23.0, venv 5.4 GB. dsr-bot `~/laya-venv`(torch 2.11 cu128, laya 0.3.23)는 안 건드림.
- **주의**: `finetune(..., "english")`처럼 별칭을 주면 `snapshot_download`를 **revision 없이** 불러 Hub의 최신 main을 받음.
  캐시에 이미 `55cf4c4`(고정 리비전)와 `7b928d8`(캐시의 `refs/main`) 두 스냅숏이 있음 → 재현성을 위해 2단계에선 고정 리비전 경로를 직접 넘김.

## 7. 체크포인트 후보와 추천

| | english `convaiinnovations/laya` | multilingual (`laya/multilingual`) | typed-decisions |
|---|---|---|---|
| 구조 | ModernBERT-large 421M, 512 tok | mmBERT-base 322M, 1024 tok | ModernBERT-large 421M, 4가지 합성 업무로 미세조정 |
| 이 입력 길이 | 86 / 90 | 93 / 97 | 확인 안 함 |
| 기존 사용 | dsr-bot 미세조정 (203개로 85.2 %) | VersionSandbox 한국어 CS | 없음 |

**추천: english.** 입력이 전부 영어이고, 라우터 설명상 영어에선 english가 앞섬(0.820 vs 0.710, 개발자 주장·재현 안 함),
이 PC에서 미세조정이 돌아간 전례가 있음. multilingual은 더 작아 빠를 수 있어 5단계 비교 후보로 남김. typed-decisions는 다른 업무로 이미 조정돼 있어 첫 비교 기준을 흐릴 수 있어 뺌.

## 8. 연결 작업 규모

크지 않음(추정). `laya_rows.py` → `finetune()`로 바로 들어가고, 닫힌 루프는 `agent.predict(state, question)` 한 번 = 한 걸음.
위험은 두 가지: (1) 대상이 안 보이는 18 % 구간은 봇이 기억으로 움직여 기억 없는 모델이 따라 하기 어려움 — 닫힌 루프에서 맴돌기가 나올 수 있음(추정, 3단계에서 확인),
(2) dsr-bot에서 본 선택지 위치 편향 — `shuffle_options=("choice",)`로 학습하고, 평가 때 순서를 뒤집은 일치율을 같이 잴 것.
