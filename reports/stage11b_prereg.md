# 11b단계 선언 — 시범 수 곡선: GoToLocal · PutNextLocal, N = 100 · 500 · (1,000) · 5,000 (돌리기 전에 커밋)

지시: 보드 스레드 c7d1bc74, 11-17 cloud-claude 글 "MoKa 지시(11-17) … 11b — 시범 수 곡선을 그린다".
MoKa가 11-17 이 세션에서 "11b 진행"이라고 함. **이 파일을 커밋한 뒤에 자료를 만들고 학습한다.** 결과를 본 뒤 N을 더하거나 설정을 바꿔 다시 돌리지 않는다. 더 보고 싶은 것은 적기만 한다.

코드 `probe/stage11b.py`, 원자료 `reports/stage11b/*.json`. 시범 덤프는 git 밖(`data/`), 체크포인트는 저장소 밖 `~/babyai-laya-ft/n{N}-{gotolocal|putnext}-s{n}`.

## 1. 바꾸는 것: 시범 수 N 하나

- 입력·질문 글·선택지·순서는 5단계(GoToLocal)·10단계(PutNextLocal, `carrying:` 줄 있음)와 글자 그대로 같다. **지난 행동 줄은 넣지 않는다.**
- N = 100 · 500 · 5,000. **1,000은 이미 있는 값을 쓴다**(GoToLocal: 5단계 `reports/stage5/laya-s{0,1,2}*.json`과 2b `reports/stage2b_step_eval_gotolocal-s*.json`; PutNextLocal: 10단계 `reports/stage10/laya-s{0,1,2}*.json`, `stepeval-s*.json`). 다시 돌리지 않는다.
- 시범: 봇 seed 0부터 앞에서 N판(seed 0 ~ N−1). 100판 ⊂ 500판 ⊂ 1,000판 ⊂ 5,000판.
  거르는 규칙은 지금까지 그대로: GoToLocal은 선택지 밖 행동(pick up 등)이 나온 판을 통째로 뺀다(`dump_demos`), PutNextLocal은 그에 더해 봇이 실패한 판도 뺀다(`stage10 dump`).
  **N마다 남은 판 수 · 걸음 수 · 뺀 seed 목록을 적는다.**
- 먼저 확인: seed 0~4,999를 새로 덤프해 앞 1,000판이 기존 자료와 같은지(GoToLocal 998판 / 5,310걸음, PutNextLocal 1,000판 / 12,036걸음, 줄 단위로 같은 내용). 다르면 멈추고 적는다.
- 잠근 seed: 학습 seed 0~4,999는 개발용(10000~)·잠근 범위(20000 · 30000 · 60000 · 70000대)와 겹치지 않는다. `guarded_seeds("0-4999")`와 `stage10.seeds_of("0-4999")`가 통과하는지 코드로 확인한다.

## 2. 학습

- `TrainConfig(shuffle_options=("choice",), seed=n)`, 나머지(에폭 4, 학습률, 묶음 8×8, `loss=rlcd`) 기본값 그대로. N에 맞춰 바꾸지 않는다.
- 학습 seed: N = 100 · 500은 s0 · s1 · s2, N = 5,000은 s0 하나.
- **보정 자료**: laya 0.4.31 `split_calibration`은 **걸음(항목) 단위로 무작위**(`calib_seed` 고정) 떼어 낸다. 판 단위가 아니다(보드 글의 "판 단위로 나눔"은 코드와 다르다).
  지금까지의 1,000판 실행도 이 방식이었으므로 그대로 두고, 떼는 **수만** 같은 비율로 맞춘다:
  `n_calib = round(걸음 수 × 400 / 5,310)`(GoToLocal), `round(걸음 수 × 400 / 12,036)`(PutNextLocal).
  laya에는 `calib_max = n_calib`, `calib_frac = 0.999`로 넘긴다(그러면 `min(calib_max, int(걸음 수 × 0.999)) = n_calib`). 1,000판에 이 식을 쓰면 400이 되어 기존 실행과 같다. 실제로 뗀 항목 수를 결과에 적는다.
- 예상 시간(1,000판 실측 GoToLocal 4.7분, PutNextLocal 12.1분에 걸음 수 비례): GoToLocal 5,000판 약 25분, PutNextLocal 5,000판 약 60분. 전체(학습 14개 + 평가) 약 3시간.

## 3. 평가 (5 · 10단계와 같은 코드, 같은 조건)

- 개발 seed 10000~10299 300판, GPU, laya 기본 정밀도(bf16), 살아 있는 판을 묶어 계산, 결정적(가장 높은 확률, 동점이면 선택지 고정 순서의 앞).
- 실행: 규칙 없음, R-reset(key = `mission:` 줄을 뺀 상태 글, 5 · 10단계와 같음). 걸음 제한은 환경 그대로(GoToLocal 64, PutNextLocal 128).
- 지표: 성공, 봇 걸음 2배 안 성공(분모 300), timeout, R-reset의 살린 판 / 망가뜨린 판(같은 체크포인트의 규칙 없음 대비), 막힌 칸 전진 비율(막힌 전진 걸음 / 전체 걸음), 걸음 단위 일치.
  PutNextLocal은 "어디까지 갔나 ①~④"도.
- 걸음 단위 일치:
  - GoToLocal: 봇 궤적 1,567걸음(`data/gotolocal_eval.jsonl`). `stage5.stepcheck` + `LayaScorer`(확률 1순위, 동점 고정 순서). 1,000판 값(2b `step_eval`)은 laya의 `choice` 필드를 썼다 — 두 방식이 갈리는 걸음 수(`choice_field_vs_argmax_mismatch`)를 함께 적는다.
  - PutNextLocal: `stage10 stepeval`(개발 300판 봇 궤적 3,518걸음), 1,000판 값과 같은 코드.

## 4. 미리 정한 읽기 (보드 글 그대로, 통과 / 실패 판정은 없다)

비교 숫자 LID(Perplexity 인용, 원문 미확인): 100판 GoToLocal 64.6 % · PutNextLocal 11.1 %, 500판 97.9 % · 93.0 %.
**조건이 다르다(지난 행동 입력, 평가 판 수, 환경 버전 · 걸음 제한 미확인) — 같은 줄의 비교가 아니다.**

1. **적은 쪽(N = 100)**: Laya 규칙 없음 혼자 성공률(세 seed 평균, 300판 분모)을 LID 100판 숫자와 비교한다. 과제마다
   - 15 %p 넘게 높으면 → "적은 시범에서 유리한 것으로 보인다(조건이 달라 추정)"
   - 차이가 ±15 %p 안이면 → "가르지 못함"
   - 15 %p 넘게 낮으면 → "적은 시범에서도 낮다"
   N = 500도 같은 방식으로 적되 읽기는 N = 100만 미리 정한 것이다. 15 %p는 [cloud]가 임의로 잡았다.
2. **많은 쪽(N = 5,000, s0 하나)**: 규칙 없음 혼자 2배 안 성공을 **같은 학습 seed s0의 1,000판 값**(GoToLocal 271, PutNextLocal 245)과 비교한다. 과제마다
   - 15판 넘게 오르면(GoToLocal ≥ 287, PutNextLocal ≥ 261) → "시범 수가 병목이었다"
   - 그 밖(+15판 이하, 내려간 경우 포함) → "이 입력에서는 1,000판 근처에서 이미 평평하다"
   "s0 하나"라는 말을 함께 적는다. 세 seed 평균(GoToLocal 271.3, PutNextLocal 251.0)도 옆에 적는다.
3. **R-reset**: 모든 N · seed에서 망가뜨린 판 수를 그대로 적는다. 시범이 적어 모델이 약할 때도 0인지가 볼 것이다.

## 5. 보고

- 선언 · 결과 커밋 해시. 과제마다 표 하나: N × {혼자 성공, 혼자 2배 안, R-reset 성공, R-reset 2배 안, 망가뜨린 판, 걸음 단위 일치}, seed별 값과 평균.
  학습 시간, 자료 크기(판 · 걸음 · 보정 항목), N마다 뺀 seed 목록([cloud]의 작은 CNN 비교용).
- 순서: GoToLocal 먼저, PutNextLocal 다음. GoToLocal이 끝나면 중간 보고를 올릴 수 있다(push · 보드 글은 MoKa에게 묻고).
- 한 것 / 안 한 것 / 추정. 보고하고 멈춘다.

## 하지 않는 것

지난 행동 입력의 곡선, 10,000판, 다른 과제, 5,000판의 s1 · s2, 최종 seed, `soft-ce` 손실 비교(다음 후보로 적어만 둔다), 규칙 변형, 실패 판 분석, 보정 자료를 판 단위로 바꾸기.
자원: GPU 사용 전 확인, DSR 실행과 겹치면 시각을 적는다.
