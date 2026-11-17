# 12단계 선언 — 호스팅·공개 결정 모델 참조선: Gemini Decision 1(글 · 그림 · 글+그림)과 Clef (돌리기 전에 커밋)

지시: 보드 스레드 c7d1bc74, 11-17 cloud-claude 글 "MoKa 요청(11-17) ① Clef 자료 ② Gemini Decision 1 ③ 그림 입력".
MoKa가 11-17 이 세션에서 "3번도 진행해줘"라고 함. 학습 없음, 참조선이라 판정 기준은 두지 않는다.
**이 파일을 커밋한 뒤에 모델을 부른다. 결과를 본 뒤 설명 글·질문·입력 형식을 고쳐 다시 돌리지 않는다.** 고치고 싶은 것은 적기만 한다.

코드 `probe/stage12.py`, 원자료 `reports/stage12/*.json`, 응답 캐시 `data/stage12_cache_*.jsonl`(git 밖).

## 1. Clef 과거 기록 (새로 돌리지 않고 찾은 것)

- 저장소 VersionSandbox, `docs/decision_models.md`(브랜치 `fieldlab/tarot-route`, 10-22~10-27) §2.1 · §4.8~4.10, `docs/decision_model_placement_probe.md`.
- 시험한 것은 클라우드 Clef가 아니라 **로컬 `clef-flash`**(Cloudflare, Qwen3.5-9B 미세조정, Apache 2.0, Ollama 0.40.5 `/v1/systemone`)다.
- 과제: Hotpla 가게 업종 고르기(22종, 가게 40곳)와 가게 × 음식 카드 판정, 음식 사진 → 카드. BabyAI가 아니다.
- 숫자(그 문서 그대로): 업종 정확 35/40 · 허용 36/40(Gemma 12B와 같음), 중앙 지연 172 ms. 확률은 0.3~0.7에 낮게 퍼져
  문턱값 구간이 좁았다(AUC 0.935). 실제 사진 33장에서 음식 일치 20(Gemma 18). 결론: 단독 정밀도 미달, "후보 생성기"(C2)로 Gemma 호출을 줄이는 쪽에 둠.
- 그래서 이 단계에 Clef는 **로컬 `clef-flash:latest`**(이 PC에 설치돼 있음, 무료)로 한 줄 넣는다. 클라우드 Clef(27B, 유료, Cloudflare 계정 필요)는 돌리지 않는다.

## 2. 고정한 틀 (5단계 Jev와 글자 그대로)

- 과제 `BabyAI-GoToLocal-v0`, 개발 seed 10000~10299(300판 전부), 걸음 제한 64, 결정적(가장 높은 확률, 동점이면 turn left / turn right / forward 순서의 앞).
- 글 입력: 상태 글 = `mission:` 줄 + 관측 글(5단계와 같음).
- 질문: `{"action": {"type": "choice", "instructions": EXPLAIN, "criteria": {"turn left": null, "turn right": null, "forward": null}}}`.
  EXPLAIN은 `probe/stage5.py`의 글(README "5단계" 확정본) 그대로.
  - Gemini가 `criteria` 값 `null`을 받지 않으면 빈 글자 `""`로, 그것도 안 되면 선택지 이름 자체를 설명으로 넣는다. 어느 것을 썼는지 결과에 적는다.
- 실행: 규칙 없음, R-reset(5단계 정의, key = 관측 글).
- 걸음 단위: 봇 궤적 1,567걸음(`data/gotolocal_eval.jsonl`)에서 봇과의 일치(대상 보임 / 안 보임), 선택지 순서를 뒤집었을 때 답이 바뀌는 비율,
  **앞이 막힌 걸음에서 1순위가 forward인 비율**(`stage5_blocked.blocked_ahead`와 같은 정의, 봇 궤적 걸음 기준. 5단계: Laya 0~0.8 %, Jev 5.2 %, Gemma 22.5 %).
- 닫힌 루프 지표: 성공, 봇 걸음 2배 안(분모 300), 처음 대상 보임 158 / 안 보임 142, 살린 / 망가뜨린 판(R-reset 대 같은 모델 규칙 없음), 형식 오류 걸음.
- 같은 요청(모델, 설명 글, 입력, 선택지 순서)은 한 번만 보낸다(5단계와 같은 캐시).
- 응답 시간: 새 호출의 왕복 중앙값 · 95 %.

## 3. 그림 입력 (Gemini Decision 1)

- 공식 문서(aistudio.google.com/docs/decisions-api, 11-17 읽음): `POST https://generativelanguage.googleapis.com/v1beta/decisions`,
  `input`에 `{"type": "image", "data": <base64>, "mime_type": "image/png", "resolution": ...}`를 받는다. **판단 API가 그림을 받으므로 진행한다.**
- 그림: 환경이 주는 부분 관측(7×7)을 MiniGrid 시점 렌더로 그린 것. 관측 `image`를 `Grid.decode` → `render(tile_size=32, agent_pos=(3,6), agent_dir=3, highlight_mask)`,
  224×224 PNG. MiniGrid `get_pov_render(32)`와 픽셀이 같음을 확인(seed 10003). 방 전체 그림은 쓰지 않는다. `resolution: "low"` 고정.
- 세 입력(같은 판, 같은 질문 틀):
  - **(가) 글만**: 2절 그대로.
  - **(나) 그림만**: input = [그림, 글 `mission: <지시문>`]. instructions = IMAGE_EXPLAIN(아래).
  - **(다) 글 + 그림**: input = [그림, 2절의 상태 글]. instructions = EXPLAIN + 빈 줄 + IMAGE_PARA.
- IMAGE_PARA (고정):
  "The image is the agent's own limited forward view, 7 x 7 cells. The agent is the red triangle in the bottom row,
  middle column, and it always points up: up in the image is straight ahead, left in the image is the agent's left.
  Grey cells are walls. Coloured shapes are objects: a ball is a circle, a box is a square outline, a key is a key shape.
  Lit cells are in view; black cells are out of view or hidden behind a wall, so they are unknown, not empty."
- IMAGE_EXPLAIN = EXPLAIN의 첫 세 문단("You control …"부터 "Any matching object counts."까지) + 빈 줄 + IMAGE_PARA.
- 지표는 2절과 같다. 막힌 걸음 정의는 글 기준(같은 걸음)을 그대로 쓴다.
- Laya에는 그림 입력이 없으니 이것은 **같은 호스팅 모델에서 글 대 그림** 비교다.

## 4. 모델·버전·비용

- Gemini: 모델 id `gemini-decision-1`, API `v1beta`, 키는 환경 변수 `GEMINI_API_KEY`로만(코드·로그·git·보드에 넣지 않는다).
  공시 요금 입력 $0.10 / 100만 토큰, 출력 무료. 호출 날짜를 결과에 적는다.
- 비용 추정(5단계 Jev 실측 기반): 걸음 단위 3,126호출 × 약 760토큰 + 닫힌 루프 두 실행의 새 상태 약 1,000~2,000호출.
  글 설정 약 400~500만 토큰 ≈ **$0.5**. 그림 설정은 그림 토큰(low, 수백 토큰 미만으로 봄)을 더해 설정당 **$1 미만**으로 본다.
  한 설정이 $2를 넘을 것 같으면(첫 100호출의 실제 토큰 수로 다시 계산) 멈추고 MoKa에게 묻는다.
- Clef: 로컬 `clef-flash:latest`, Ollama 0.40.5, 비용 0. GPU 사용 전 확인.
- 보내는 자료는 BabyAI 공개·합성 관측뿐이다. 잠근 seed(20000·30000·60000·70000대)는 쓰지 않는다(코드가 거부).

## 하지 않는 것

다른 과제, 프롬프트 다듬기, 미세조정, 생성형 모델로 대체, 클라우드 Clef, clef-flash 그림 입력, 최종 seed, 규칙 R · 벌점.
