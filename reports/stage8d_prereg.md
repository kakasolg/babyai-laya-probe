# 8d 선언 — PickupDist 최종 확인 (2026-11-15, Host: Moka-Windows-Dev)

지시: 보드 스레드 c7d1bc74, 11-15 14:59 MoKa. **이 파일을 커밋한 뒤에만** seed 30000~30299를 연다.
30000번대는 지금까지 한 번도 쓰지 않았다(`probe/dump_demos.py`의 `guarded_seeds`가 거부해 왔다). 재학습은 없다.

## 평가 판

- `BabyAI-PickupDist-v0` seed **30000~30299, 300판 전부**. 걸음 제한 49(환경 기본값). 판을 빼지 않는다.
- 봇이 내려놓기 등 네 선택지 밖의 행동을 쓴 판 수와 회색 벽 판 수만 따로 적는다.
- 봇의 궤적은 이 실행에서 처음 만들고, 학습에 쓰지 않는다.

## 실행 — 설정은 8c와 같다

같게 두는 것: 상태 글(`obs_to_text`), 질문 글(`question_pickup()`), 선택지 순서(turn left / turn right / forward / pick up), 결정적 선택(가장 높은 점수, 동점이면 고정 순서의 앞), R-reset 정의(key = 지시문 줄을 뺀 관측 글, 네 행동을 다 해 봤으면 그 key의 기록을 비우고 1순위부터), 틀린 물체를 주워도 판을 끊지 않는 것.

| 이름 (`reports/stage8/final/`) | 무엇 |
|---|---|
| `bot` · `random` | 봇, 무작위(네 행동) |
| `fixed` · `fixed-reset` | 모델 없음: 고정 점수 forward 0.4 > left 0.3 > right 0.2 > pick up 0.1, 규칙 없음 / R-reset |
| `laya-s0` · `laya-s1` · `laya-s2` | 8b 체크포인트(WSL `~/babyai-laya-ft/pickupdist-s0/1/2`), 규칙 없음 |
| `laya-s0-reset` … `laya-s2-reset` | 같은 체크포인트 + R-reset (`--base`로 규칙 없음과 비교) |

명령: `python -m probe.stage8 loop --use-final-seeds --policy <none|reset|bot|random|fixed|fixed-reset> [--model …] --name … [--base …]`

선언 전 개발용 판(10000~10299)에서 확인한 것:
- 이 코드의 모델 없음 대조군이 8a 값을 그대로 재현한다: 규칙 없음 0판, R-reset 8판(2배 안 0, timeout 265, 틀린 줍기 27).
  결과는 `reports/stage8/dev-fixed.json`, `dev-fixed-reset.json`.
- Laya s0 규칙 없음을 다시 돌려 8c 결과(`laya-s0.json`)와 판별로 비교했다: 300판 모두 결과와 걸음 수가 같았다(불일치 0).

## 지표 (분모 300) — 8c와 같다

성공 · 봇 걸음 2배 안 성공 · timeout · 틀린 물체를 주움 · 처음 대상 보임 / 안 보임 · 지시문 종류별(색만 · 종류만 · 둘 다) · 살린 판 / 망가뜨린 판 · 걸음 합 두 가지(300판 전체 / 틀린 줍기 판 뺌) · 줍기 분류 · 규칙이 고른 줍기가 틀린 물체였던 판 · 회색 벽 판 한 줄.

## 미리 정한 판정

1. **모델 단독 재현**: Laya 규칙 없음 성공의 **세 seed 평균이 252판(84 %) 이상.**
   - 근거(보드): 개발용 평균 267판. 300판 한 묶음의 표본 오차가 약 5판, 두 묶음 차이는 약 7.6판이라 그 두 배(15판)를 뺐다.
   - GoToLocal 6단계에서 seed별 하한을 빠듯하게 잡아 2판 차이로 미달이 났던 것을 반영해, 이번에는 평균으로 본다.
2. **규칙 효과 재현**: Laya 세 seed 모두 R-reset 성공 **276판(92 %) 이상**이고, **망가뜨린 판 0**.

기준에 못 미치면 못 미쳤다고 적는다. 원인을 찾아 다시 돌리지 않는다.

## 한 번만 돌린다

- 30000번대를 여는 것은 이 실행뿐이다(`--use-final-seeds`). 끝나면 플래그를 지우고 다시 막는다.
- 중간에 죽으면 같은 설정으로 이어서 끝낸다. 결과를 본 뒤 설정을 바꿔 다시 돌리지 않는다.
- 실패한 판은 seed 목록과 유형(timeout / 틀린 줍기)만 적는다. 걸음별로 들여다보지 않는다.

## 하지 않는 것

재학습, 규칙 변형, `carrying` · 이력 · 그림 입력, Jev · Gemma, 실패 판 분석, 새 과제.
