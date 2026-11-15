# 8a단계 보고 — 다음 과제 `BabyAI-PickupDist-v0` 살펴보기 (학습 없음, 2026-11-15, Host: Moka-Windows-Dev, WSL Ubuntu)

지시: 보드 스레드 c7d1bc74, 11-15 MoKa 지시의 8단계 · 8a. 학습, 모델 추론, Jev·Gemma 호출은 없다.
- 코드: `probe/stage8a.py`
- 원자료: `reports/stage8a/stage8a.json`
- 시범 덤프: `data/pickupdist_train.jsonl` (git 밖, seed 0~999 봇 걸음 전부)

고정한 것(보드 지시 그대로):
- 선택지 4개, 순서는 turn left / turn right / forward / pick up.
- 부분 관측 7×7. 환경은 고치지 않았다.
- seed: 학습 0~999, 개발용 10000~10299, 최종 확인 30000~30299.
  - 30000~30299는 `dump_demos.guarded_seeds`가 거부한다. 거부되는 것을 확인했다. 8d 선언 전에는 쓰지 않는다.
  - 20000~20299도 계속 거부한다.

## 1. 봇 재측정 (MiniGrid 3.2.0)

| | 학습 0~999 | 개발용 10000~10299 | [cloud] 0~199와 대조 |
|---|---|---|---|
| 성공 | 1000 / 1000 | 300 / 300 | 0~199: 200 / 200 (같음) |
| 걸음 평균 · 중앙 · 최대 | 4.95 · 5 · 17 | 5.15 · 5 · 19 | 0~199 평균 5.29 (같음) |
| 행동: 왼쪽 · 오른쪽 · 전진 · 줍기 · 내려놓기 | 757 · 938 · 2,239 · 1,010 · 10 | 237 · 291 · 712 · 302 · 2 | 0~199: 154 · 210 · 488 · 203 · 3 (같음) |
| 4개 밖의 행동(내려놓기)을 쓴 판 | 10판 (36, 52, 183, 336, 445, 525, 728, 974, 981, 984) | 2판 (10210, 10298) | — |

- 걸음 제한은 49(방 7×7)다. 방 하나에 물체 5개가 있다.
- 줍기 1,010번 중 1,000번은 맞는 물체가 바로 앞(`1 ahead`)에 있을 때 했다.
  - 나머지 10번은 길을 막은 물체를 주웠다가 내려놓은 것이다. 위 10판이 그 판이다.
- 학습에서 빼는 판은 위 10판이다(지시대로). 개발용 2판은 평가에서 빼지 않는다.
- 맞는 물체가 바로 앞에 있는데 줍지 않은 걸음이 7개 있다(돌기 7). 맞는 물체가 여럿인 판에서 봇이 다른 하나를 고른 것으로 보인다(추정, 확인 안 함).

## 2. 지시문

- 서로 다른 지시문은 35가지다. 모양은 `pick up a/the <색> <종류>`, `pick up a/the <종류>`, `pick up a/the <색> object`다.
- 판 1,000개를 지시문 종류로 나누면 이렇다.

| 종류 | 판 | 관사 the / a |
|---|---|---|
| 색과 종류 둘 다 (`pick up the blue ball`) | 330 | 330 / 0 |
| 종류만 (`pick up a key`) | 326 | 69 / 257 |
| 색만 (`pick up a blue object`) | 344 | 169 / 175 |

- 방에 맞는 물체가 2개 이상인 판은 **400 / 1,000**이다(물체만 셈). 분포는 1개 600 · 2개 272 · 3개 116 · 4개 12판이다.
- **환경의 특이점(고치지 않음)**: `pick up a grey object`는 환경이 회색 **벽 칸**도 맞는 대상으로 센다.
  - 해당 판은 48판이고, `obj_poss`가 25~27개다.
  - 그래서 회색 물체가 하나뿐인데도 관사가 `a`인 판이 32판 있다.
  - 벽은 주울 수 없으므로 성공 판정은 물체로만 난다. 위의 "2개 이상" 숫자는 물체만 센 값이다.

## 3. 상태 글 — GoToLocal 글 함수를 그대로 쓸 수 있나 (바꾸지 않음, 적기만)

그대로 썼다. 위 표본과 통계는 모두 GoToLocal의 `obs_to_text` 결과다. 보이는 물체 종류는 ball · box · key뿐이고, 문(door)은 없다.
같은 글·지시문에 봇 행동이 갈리는 걸음은 0.32 %다(그림+지시문 키로는 0.24 %).

바꿀지 정해야 할 것이 네 가지 있다. 지금은 아무것도 바꾸지 않았다.

1. **들고 있는 물체가 글에 없다.**
   - MiniGrid는 들고 있는 물체를 관측 그림의 에이전트 칸에 넣는데, 글 함수는 그 칸을 건너뛴다.
   - 맞는 물체를 주우면 판이 바로 끝나므로, 봇 시범에서 들고 있는 걸음은 24걸음뿐이다. 모두 위의 막은 물체를 주운 10판이고, 학습에서 빠진다.
   - 닫힌 루프에서는 틀린 물체를 주운 뒤에 생긴다. 내려놓기가 선택지에 없으니, **틀린 물체를 주우면 그 판은 더 이상 성공할 수 없다**. 다시 줍기를 해도 아무 일도 일어나지 않는다.
   - 후보: `carrying: <색> <종류>` 한 줄. 넣을지는 MoKa가 정한다.
2. **"object" 지시문과의 대응.** `pick up a blue object`에 맞는 줄은 `blue key: …`, `blue ball: …`처럼 종류가 붙어 있다. 글에는 대응 힌트를 넣지 않는다(GoToLocal과 같은 방식). 모델이 배울 몫이다.
3. **바로 앞 칸의 대상.** 표현은 GoToLocal과 같은 `<물체>: 1 ahead`다. GoToLocal에서는 그 자리에 서면 판이 끝났지만, 여기서는 줍기를 골라야 한다. 글은 바꿀 필요가 없어 보인다(추정).
4. **Laya 질문 글.** 지금 `laya_rows.py`의 설명은 "reach the object"이고 선택지가 3개라 바꿔야 한다. dry_run에는 **초안**을 썼다(확정 아님).
   - instructions: "A grid agent must pick up an object that matches the mission. Pick its next action from what it can see now."
   - 줍기 선택지 설명: "pick up the object in the cell directly ahead"
   - 나머지 세 선택지의 설명은 GoToLocal과 같다.

## 4. 입력 글 표본 10개 (봇 행동과 함께, seed 순 첫 해당)

| 무엇 | seed · 걸음 | 상태 글 (줄은 ` / `로 이음) | 봇 |
|---|---|---|---|
| 줍기가 정답 | 0 · 6 | mission: pick up the green key / facing: west / red ball: 1 right / green key: 1 ahead / yellow key: 1 ahead, 1 right / walls: 2 ahead, 1 left | pick up |
| 줍기가 정답 | 1 · 3 | mission: pick up a key / facing: west / blue key: 1 ahead / grey ball: 2 ahead / red key: 3 left / yellow ball: 2 ahead, 3 left / walls: 3 ahead, 2 right | pick up |
| 줍기가 정답 | 2 · 6 | mission: pick up the red ball / facing: south / red ball: 1 ahead / grey key: 1 ahead, 2 right / yellow key: 2 ahead, 2 right / walls: 3 ahead, 2 left | pick up |
| 대상이 안 보임 | 3 · 0 | mission: pick up a key / facing: south / green box: 3 left / walls: 1 ahead, 1 right | turn left |
| 대상이 안 보임 | 6 · 0 | mission: pick up a red object / facing: west / grey box: 2 ahead, 1 right / walls: 3 ahead, 1 left | turn right |
| 색만 지정 | 4 · 0 | mission: pick up the green object / facing: east / red box: 1 right / grey box: 3 right / purple box: 3 ahead / green ball: 1 ahead, 3 right / blue key: 4 ahead, 2 right / walls: 5 ahead, 1 left | forward |
| 색만 지정 | 5 · 0 | mission: pick up a red object / facing: west / red box: 1 right / red key: 3 ahead / purple ball: 3 ahead, 1 left / yellow key: 3 ahead, 1 right / walls: 4 ahead, 3 left, 3 right | turn right |
| 맞는 물체 2개 이상 | 7 · 0 | mission: pick up a grey object / facing: east / yellow key: 2 ahead / yellow ball: 3 ahead / grey ball: 4 ahead / blue box: 4 ahead, 3 left / walls: 5 ahead, 1 right | forward |
| 맞는 물체 2개 이상 | 9 · 0 | mission: pick up a box / facing: east / purple box: 1 ahead, 2 right / walls: 2 ahead, 1 left | forward |
| 방해 물체가 더 가까움 | 10 · 1 | mission: pick up a box / facing: west / purple key: 2 left / blue ball: 3 left / red box: 4 ahead / blue key: 3 ahead, 3 left / walls: 5 ahead, 1 right | forward |

## 5. 토큰 길이와 `dry_run` (english `55cf4c4`, 가중치 안 받음, 초안 질문)

| | 중앙값 | 최대 |
|---|---|---|
| 상태 글(지시문 줄 + 관측 글) | 43 | 69 |
| 모델 전체 입력 | 118 | 144 (`max_len` 512 넘는 것 0) |

`dry_run`: 4,944행(4개 밖의 행동 10걸음은 뺌)이 모두 유효하고, 건너뛴 것은 0이다. 학습 4,544 / 보정 400, 4 epoch에 최적화 갱신 284번이다.

## 6. 걸음 범주 (학습 시범 4,954걸음)

| 범주 | 비율 |
|---|---|
| 줍기가 정답인 걸음 | 20.4 % |
| 맞는 물체가 바로 앞(`1 ahead`) | 20.3 % |
| 대상이 안 보임 | 11.1 % |
| 방해 물체가 대상보다 가까움 | 33.3 % |
| 방에 맞는 물체 2개 이상인 판의 걸음 | 32.8 % |

## 7. 모델 없음 대조군 (개발용 300판, 고정 점수 forward 0.4 > left 0.3 > right 0.2 > pick up 0.1)

| | 성공 | 봇 걸음 2배 안 | timeout | 틀린 물체를 주운 판 | 처음 보임 / 안 보임 성공 | 300판 걸음 합 | 살린 / 망가뜨린 |
|---|---|---|---|---|---|---|---|
| 규칙 없음 | 0 | 0 | 300 | 0 | 0/175 · 0/125 | 14,700 | — |
| R-reset | **8** | **0** | 292 | 27 | 7/175 · 1/125 | 14,571 | 8 / 0 |

- GoToLocal은 같은 대조군이 198 / 227판 풀렸는데, 여기서는 **규칙만으로는 거의 안 풀린다**(8판, 2배 안 0).
- 추정(확인 안 함): 성공하려면 맞는 물체 앞에서 꼴찌 순위인 줍기를 골라야 하는데, R-reset은 그 상태 글에서 나머지 세 행동을 다 해 본 뒤에야 줍기를 시도한다. 게다가 틀린 물체를 주우면 판이 막힌다(27판). 그러니 이 과제의 성공 수는 GoToLocal보다 규칙 효과가 덜 섞일 것이다.
- R-reset은 정의 그대로다(key = 관측 글, 네 행동을 다 해 봤으면 그 key만 비우고 1순위). 300판 모두 개입이 있다.

## 한 것 / 안 한 것 / 추정

**한 것**
- 봇 재측정을 했다. [cloud]의 0~199 숫자와 모두 같았다.
- 지시문 종류와 수, 맞는 물체 수를 셌고, 환경이 회색 벽을 대상으로 세는 점을 확인했다.
- 글 함수를 그대로 썼을 때 바꿀 후보 네 가지를 적었다.
- 표본 10개, 토큰 길이, 초안 질문으로 `dry_run`을 했다.
- 걸음 범주를 셌고, 모델 없음 대조군(규칙 없음 · R-reset)을 개발용 판에서 쟀다.
- 30000~30299를 거부하게 했다.

**안 한 것**
- 학습과 모델 추론, 글 함수·질문 글 확정, 최종 seed, 무작위 기준선과 봇 기준선의 닫힌 루프(8c에서 함)를 하지 않았다.
- 7걸음(대상이 앞에 있는데 돌기)의 원인 확인, 대조군이 왜 실패하는지 걸음별로 보기도 하지 않았다.

**추정**
- 대조군이 낮은 이유는 위 §7의 추정이다.
- 바로 앞 칸의 표현은 바꿀 필요가 없다는 것도 추정이다(§3의 3).

MoKa가 글 형식(특히 `carrying:` 줄과 질문 글)을 본 뒤 8b(학습) · 8c(닫힌 루프) · 8d(선언 뒤 최종 확인)를 정한다. 여기서 멈춘다.
