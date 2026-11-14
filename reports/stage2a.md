# 2a단계 보고 — GoToLocal 덤프·통계 (2026-11-14, Host: Moka-Windows-Dev, WSL Ubuntu)

지시: 보드 스레드 "[babyai-laya-probe] 2단계 지시"(cloud-claude, MoKa 확인 11-14). 학습 없음.
환경: Python 3.12.3, minigrid 3.2.0, laya 0.4.31. 원자료: `gotolocal_text_stats.json`, `gotolocal_laya_dryrun.json`,
덤프 요약 `data/gotolocal_train.jsonl.summary.json`(git 밖, 아래에 옮겨 적음).

## 한 것 / 안 한 것

| 한 것 | 안 한 것 (확인 안 함) |
|---|---|
| `BabyAI-GoToLocal-v0` seed 0~999 봇 덤프 → 998판 5,310걸음 | 학습, 가중치 로드, 제로샷 |
| 걸음 범주 통계, 표본 10개, 토큰 길이, `dry_run`(english 고정 리비전 `55cf4c4`, 토크나이저만) | 평가 seed 10000~10299 덤프 |
| README·1단계 보고의 잘못 읽은 두 곳 고침 | multilingual 토큰 길이(english로 고정됐으므로 뺌) |

## 1. 봇 (seed 0~999)

| 항목 | 값 |
|---|---|
| 성공 | 1000/1000 |
| 걸음 평균 / 최대 | 5.33 / 24 (max_steps 64) |
| 행동 | 0: 938 · 1: 1,110 · 2: 3,274 · **3: 2 · 4: 2** |
| 학습에서 뺀 판 | **2판** (seed 94, 844 — 봇 궤적에 pickup(3)·drop(4)이 한 번씩 들어 있어 뺐다. 세 행동으로 못 푸는 판인지는 확인 안 함) |
| 남은 판 / 걸음 | 998 / 5,310 |
| 지시문 | 36가지 = 대상(색 6 × 종류 3) 18 × 관사 2 |

클라우드 숫자(300판 중 3·4가 한 번씩, 평균 5.3, 최대 24)와 맞음. 1,000판에선 3·4를 쓴 판이 2판.

**관사가 답을 흘림 (환경 그대로의 성질, 확인함)**: 첫 걸음 기준 `the` 680판은 모두 맞는 물체 1개, `a` 318판은 모두 2개 이상.
모델이 "a면 어느 쪽이든 가까운 것"을 배울 수 있다는 뜻이고 환경을 고치지 않으므로 그대로 둠. 지시문 가리기 비교(3단계)에서 관사도 같이 가려짐.

## 2. 걸음 범주

| 범주 | 걸음 비율 |
|---|---|
| 대상(지시문에 맞는 물체)이 시야에 없음 | 17.3 % |
| 대상이 보이지만 방해 물체가 더 가까움 | **52.8 %** |
| 방에 맞는 물체 2개 이상 | 24.1 % (판 기준 31.9 %) |
| 시야에 맞는 물체 2개 이상 | 11.9 % |
| 첫 걸음에 대상이 안 보이는 판 | 49.3 % |
| 한 걸음에 보이는 물체 수 | 평균 4.4, 최대 8 |

거리 = 앞 + |옆|(맨해튼). 3단계의 "처음부터 대상이 보인 판 / 안 보인 판"은 약 반반으로 나뉠 것(학습 seed 기준).

## 3. 입력 글 표본 10개 (rng 0, 한 판에 하나; 줄바꿈 → ` / `)

| seed·걸음 | mission (맞는 물체 수) | 범주 | 글 | 봇 |
|---|---|---|---|---|
| 941·0 | go to a yellow ball (2) | 대상 안 보임 | facing: south / grey ball: 1 ahead, 1 left / yellow box: 2 ahead, 2 left / walls: 4 ahead, 1 right | turn left |
| 462·0 | go to the red ball (1) | 대상 안 보임 | facing: west / green box: 2 left / walls: 1 ahead, 3 right | turn right |
| 861·1 | go to the purple ball (1) | 대상 안 보임 | facing: west / purple box: 3 right / red ball: 5 ahead / walls: 6 ahead, 1 left | forward |
| 597·5 | go to a grey key (3) | 방해가 더 가까움 | facing: north / purple box: 1 left / blue box: 1 ahead, 1 left / purple ball: 3 left / grey key: 3 ahead, 3 left / walls: 4 ahead, 1 right | forward |
| 66·3 | go to the purple box (1) | 방해가 더 가까움 | facing: north / red ball: 1 right / green ball: 1 ahead, 1 left / purple box: 1 ahead, 3 right / walls: 3 ahead, 2 left | forward |
| 384·1 | go to the green ball (1) | 방해가 더 가까움 | facing: east / yellow key: 2 left / yellow box: 2 ahead, 1 left / yellow ball: 1 ahead, 3 right / blue ball: 2 ahead, 3 right / yellow key: 4 ahead, 1 left / grey key: 5 ahead, 1 left / green ball: 5 ahead, 1 right / blue ball: 5 ahead, 2 right / walls: 6 ahead, 3 left | forward |
| 875·1 | go to a red key (2) | 맞는 것 2개 보임 + 방해가 더 가까움 | facing: south / purple ball: 1 ahead, 1 right / grey ball: 1 ahead, 2 right / red key: 3 ahead / red key: 3 ahead, 2 right / walls: 4 ahead, 1 left | forward |
| 815·9 | go to a yellow key (2) | 맞는 것 2개 보임 + 방해가 더 가까움 | facing: east / purple ball: 1 left / yellow key: 1 ahead, 1 left / purple key: 1 ahead, 2 right / yellow key: 1 ahead, 3 left / walls: 2 ahead, 3 right | forward |
| 627·0 | go to a blue box (2) | 대상 안 보임 | facing: north / red ball: 2 right / purple ball: 3 right / red ball: 3 ahead, 3 right / walls: 4 ahead, 1 left | turn right |
| 477·4 | go to the yellow box (1) | 방해가 더 가까움 | facing: north / red box: 1 ahead / green ball: 1 ahead, 1 left / blue ball: 3 left / blue key: 1 ahead, 2 right / yellow box: 2 ahead, 1 left / walls: 3 ahead, 3 right | turn left |

글 형식에서 MoKa가 볼 점:
- **어느 줄이 대상인지 표시하지 않음** — 지시문과 줄을 맞춰 보는 것이 모델이 할 일. 표시하면 "지시를 읽는가"를 볼 수 없게 됨.
- 물체 줄은 가까운 순서(맨해튼, 같으면 앞 거리·옆 순)라 대상 줄의 자리가 매번 다름.
- `1 ahead` 물체는 앞을 막음(477·4: 바로 앞 red box → 봇이 돌아감).
- 시야 안 물체는 벽 너머 칸이 아니면 모두 보임(물체는 시야를 가리지 않음).

## 4. 글 길이 (english 토크나이저, 5,310행)

| | 중앙 | 최대 |
|---|---|---|
| 관측 글만 | 47 | 86 |
| 상태(`mission:` 줄 + 글) | 55 | 94 |
| 모델 전체 입력(지시·선택지 3개 포함) | 116 | 155 |

max_len 512, **잘림 0행**. GoToObj(86/90)보다 물체 줄이 늘어 길어짐.

## 5. dry_run (Laya 0.4.31, english `55cf4c4`, `shuffle_options=("choice",)`)

5,310행 모두 유효, 건너뜀 0. 학습 4,910 / 보정 400, 유효 배치 64, 4 epoch 308 업데이트.

## 6. 같은 입력에 봇 행동이 갈리는 비율 (참고만)

| 키 | 서로 다른 키 / 걸음 | 갈림 |
|---|---|---|
| image + mission | 5,256 / 5,310 | 0.60 % |
| 글 + mission | 5,285 / 5,310 | 0.49 % |

입력이 거의 다 한 번씩만 나와서 이 숫자는 데이터가 성긴 정도일 뿐, 정확도 상한도 정보 손실 지표도 아님(1단계 보고 고쳐 읽기 참고).

## 7. 추정 (확인 안 함)

- 걸음 단위 정확도는 맞는 물체가 2개 이상인 판(24 % 걸음)에서 봇과 다른 쪽을 골라 낮게 나올 수 있음 — 주 지표는 닫힌 루프 성공률(2b·3에서 확인).
- 대상 안 보임 구간(17 %)은 봇이 기억으로 탐색하므로 기억 없는 모델이 맴돌 위험이 있음.
