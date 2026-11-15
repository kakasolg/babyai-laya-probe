# 6단계 선언 — 최종 확인 (seed 20000~20299, 한 번만)

보드 지시(11-15, cloud-claude 전달, MoKa 지시)를 따른다. 이 파일을 커밋한 **뒤에만** 최종 seed를 쓴다.
재학습 없음. 설정은 5단계와 글자 그대로 같다. 바뀐 것은 seed 범위와 출력 폴더뿐이다.

## 0. 돌리기 전 확인 (개발용 10000~10299, 이미 실행함)

모델 없는 대조군을 고정 점수로 돌렸다. 점수는 forward 0.7, turn left 0.2, turn right 0.1이다(`--scorer fixed`).

| 대조군 (개발용 300판) | 성공 | 봇 걸음 2배 안 | timeout | 살린 판 / 망가뜨린 판 |
|---|---|---|---|---|
| 규칙 없음 | 16 | 16 | 284 | — |
| R-reset | 198 | 51 | 102 | 182 / 0 |

- [cloud] 값(16 / 198, 2배 안 51)과 **똑같다**. [cloud]는 key를 관측 이미지+방향으로 잡았지만, 이 방에서는 결과가 같게 나왔다.
- 결과 파일: `reports/stage6/dev-fixed.json`, `reports/stage6/dev-fixed-reset.json`.
- 코드 변경 회귀 확인도 했다. Laya s0 규칙 없음을 개발용 판에서 다시 돌렸더니, 5단계 `laya-s0.json`과 300판 모두 끝과 걸음 수가 같았다(불일치 0판).

## 1. 평가 판

- `BabyAI-GoToLocal-v0` seed 20000~20299, 300판 전부. 걸음 제한은 64(환경 기본값)이다.
- 판을 빼지 않는다. 봇이 줍기·내려놓기(행동 3·4)를 쓰는 판 수는 적기만 한다.
- 봇 덤프(평가용)는 이 실행에서 처음 만든다. 학습에는 쓰지 않는다.
  - `data/gotolocal_final.jsonl`(git 밖), 요약은 `data/gotolocal_final.jsonl.summary.json`이다.

## 2. 실행 11개 + 기준선 2개

| 점수 | 규칙 없음 | R-reset | 방문 벌점 2.0 |
|---|---|---|---|
| Laya s0 / s1 / s2 (`~/babyai-laya-ft/gotolocal-s0/1/2`) | ○ | ○ | ○ |
| 모델 없음 (고정 점수 forward 0.7 > left 0.2 > right 0.1) | ○ | ○ | — |

- 기준선 둘:
  - 봇: `closed_loop --policy bot`
  - 무작위 행동: `closed_loop --policy random`. 3단계와 같은 방식으로, 판마다 `random.Random(seed)`이고 규칙은 없다.
- 공통 설정은 5단계 그대로다(`probe/stage5.py`).
  - 입력은 상태 글(지시문 줄 + 관측 글)이다.
  - 선택지 순서는 turn left / turn right / forward로 고정한다. 동점이면 이 순서를 따른다.
  - key는 이 걸음에 모델에 준 관측 글이다.
  - R-reset 정의: 세 행동을 다 해 봤으면 그 key만 비우고 1순위를 고른다.
  - 벌점 정의: ln(max(p, 1e-9)) − 2.0 × count가 가장 큰 행동을 고른다.
- **하지 않는 실행**:
  - 규칙 R(포기 있음), Jev, Gemma
  - 다른 계수, 다른 key, 다른 무작위 방식

실행 명령(WSL, 저장소 루트, `PY=~/babyai-laya-venv/bin/python`, `HF_HUB_OFFLINE=1`). 결과는 `reports/stage6/final/`에 저장한다.

```
F="--seeds 20000-20299 --use-final-seeds"; O=reports/stage6/final
$PY -m probe.dump_demos $F --keep-all --out data/gotolocal_final.jsonl
$PY -m probe.closed_loop --policy bot    $F --name bot    --out $O
$PY -m probe.closed_loop --policy random $F --name random --out $O
$PY -m probe.stage5 loop --scorer fixed $F --out $O --name fixed
$PY -m probe.stage5 loop --scorer fixed $F --out $O --name fixed-reset --policy reset --base $O/fixed.json
for s in 0 1 2; do M=~/babyai-laya-ft/gotolocal-s$s
  $PY -m probe.stage5 loop --scorer laya --model $M $F --out $O --name laya-s$s
  $PY -m probe.stage5 loop --scorer laya --model $M $F --out $O --name laya-s$s-reset   --policy reset   --base $O/laya-s$s.json
  $PY -m probe.stage5 loop --scorer laya --model $M $F --out $O --name laya-s$s-penalty --policy penalty --base $O/laya-s$s.json
done
```

## 3. 지표 (모든 분모 300)

- **주 지표 둘**:
  - 성공한 판 수
  - 봇 걸음 2배 안에 성공한 판 수
- **보조 지표**:
  - timeout 판 수
  - 같은 seed의 규칙 없음과 비교해 살린 판 / 망가뜨린 판
  - 처음에 대상이 보인 판 / 안 보인 판 각각의 성공 수
  - 성공 판의 평균 걸음과 같은 판에서 봇의 평균 걸음
  - 300판 걸음 합
  - 개입한 판 수

## 4. 미리 정한 판정

- **규칙 효과 재현**: Laya 세 seed 모두 R-reset 성공이 285판(95 %) 이상이고, 망가뜨린 판이 0이다.
- **모델 단독 재현**: Laya 세 seed 모두 규칙 없음 성공이 264~288판(88~96 %) 안에 든다.
- R-reset과 벌점의 우열은 판정하지 않는다. 두 주 지표를 나란히 적기만 한다.
- 기준에 못 미치면 못 미쳤다고 적는다. 원인을 찾아 다시 돌리지 않는다.

## 5. 실행 규칙

- 20000번대는 `--use-final-seeds`를 줄 때만 열린다. 이 플래그는 `dump_demos`, `closed_loop`, `stage5`에만 있다.
- 실행이 끝나면 플래그를 지워서 다시 막는다.
- 실행은 한 번만 한다. 중간에 죽으면 같은 설정으로 이어서 끝낸다(결정적이라 결과는 같다).
- 결과를 본 뒤 설정을 바꿔 다시 돌리지 않는다.
- 실패한 판은 seed 목록만 적는다. 걸음별로 들여다보거나 규칙을 고치지 않는다.
