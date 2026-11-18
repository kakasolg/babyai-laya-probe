# 체크포인트 · 저장소 밖 자료 목록 (2026-11-18, [win] Moka-Windows-Dev 기준)

가중치와 자료는 저장소에 넣지 않는다. 여기에는 **이름 · 위치 · 크기**만 적는다. 아무것도 지우지 않았다. 백업할지, 지울지는 MoKa가 정한다.
"다시 만들 수 있음" = 저장소 코드 + 고정 seed로 같은 것을 다시 만들 수 있다(학습은 GPU 시간이 든다).

## 1. 미세조정 체크포인트 — WSL `~/babyai-laya-ft/` (40개, 각 1.6 GB, 합 64 GB)

기본 모델은 모두 `convaiinnovations/laya`(HF 캐시, 아래 3절). 학습 설정은 기본값(`TrainConfig(shuffle_options=("choice",), seed=n)`, 에폭 4, `loss=rlcd`).

| 이름 | 과제 | 시범(판) | 학습 seed | 입력 | 만든 단계 · 날짜 | 쓴 곳 |
|---|---|---|---|---|---|---|
| `gotolocal-s0` · `s1` · `s2` | GoToLocal | 1,000 (998) | 0 · 1 · 2 | 상태 글 | 2b · 3단계, 11-13 | 3 ~ 6 · 14단계, 게임(s0 → ONNX) |
| `gotolocal-prev4-s0` ~ `s2` | GoToLocal | 1,000 (998) | 0 ~ 2 | + `previous actions:` 줄(4걸음) | 11a, 11-17 | 11a |
| `gotolocal16-s0` ~ `s2` | GoToLocal, 물건 16개 | 1,000 | 0 ~ 2 | 상태 글 | 9b, 11-16 | 9단계 |
| `pickupdist-s0` ~ `s2` | PickupDist | 1,000 | 0 ~ 2 | 상태 글(선택지 4) | 8b, 11-15 | 8단계 |
| `putnext-s0` ~ `s2` | PutNextLocal | 1,000 | 0 ~ 2 | + `carrying:` 줄 | 10b, 11-16 | 10 · 14단계 |
| `putnext-nocarry-s0` | PutNextLocal | 1,000 | 0 | `carrying:` 줄 없음 | 10단계 비교, 11-16 | 10단계 |
| `n100-{gotolocal,putnext}-s0` ~ `s2` | 각 과제 | 100 | 0 ~ 2 | 5 · 10단계와 같음 | 11b, 11-17 | 11b, 14(s0) |
| `n500-{gotolocal,putnext}-s0` ~ `s2` | 각 과제 | 500 | 0 ~ 2 | 같음 | 11b, 11-17 | 11b |
| `n5000-{gotolocal,putnext}-s0` ~ `s2` | 각 과제 | 5,000 | 0 ~ 2 | 같음 | 11b · 11b-2, 11-17 | 11b |
| `n10000-{gotolocal,putnext}-s0` ~ `s2` | 각 과제 | 10,000 | 0 ~ 2 | 같음 | 11b-3, 11-17 ~ 18 | 11b |

- 1,000판 체크포인트는 `n1000-*` 이름이 따로 없다 — `gotolocal-s*` · `putnext-s*`가 그것이다.
- **모두 다시 만들 수 있음**(덤프 + seed). 시간: GoToLocal 1,000판 약 5분 ~ 10,000판 약 45분, PutNextLocal 1,000판 약 12분 ~ 10,000판 약 112분(RTX 5080).
- WSL 디스크: 1,007 GB 중 259 GB 사용(11-18).

## 2. 게임 · 웹에 쓰는 내보낸 모델

| 위치 | 무엇 | 크기 | 다시 만들 수 있음 |
|---|---|---|---|
| `D:\dev\tools\laya-desktop-build\` | 데스크톱 판: `BabyAI-Laya.exe` · `.pck`(105 MB · 4 MB), 도움 시험 판 `BabyAI-Laya-help.exe` · `.pck`, `laya_server\`(PyInstaller 서버 + ONNX fp32, gotolocal-s0) | 2.5 GB(서버 2.2 GB) | 예(빌드 · 내보내기 코드는 저장소에 있음) |
| WSL `~/babyai-laya-web/` | 웹 실험용 ONNX `laya_fp32.onnx` · `laya_int8.onnx` 등(11-16) | 2.0 GB | 예 |
| `baby-ai-laya-probe-main/data/web-build-1116`, `web-build-1116c` | itch.io 웹 빌드 출력(1116c가 지금 공개판, `licenses.txt` 포함) | 1116c 43 MB | 예(커밋에서 다시 내보내기) |

## 3. 환경 · 캐시

| 위치 | 무엇 | 크기 |
|---|---|---|
| WSL `~/babyai-laya-venv` | 이 저장소의 파이썬 venv(laya 0.4.31, minigrid, torch) | 5.6 GB |
| WSL `~/.cache/huggingface` | 기본 모델 `convaiinnovations/laya` | 4.7 GB |
| WSL `~/laya-ft`(10-21, `ramp-v0-*`, `powertest`) · `~/laya-venv`(10-01) | **이 저장소 것이 아닌 것으로 보인다**(만든 날짜가 이 저장소보다 앞섬, 이름도 다름). 확인하지 않았다 | 4.0 GB · 6.9 GB |

## 4. 자료 (`data/`, git 밖) — 작업 폴더 두 곳에 나뉘어 있다

WSL 실행은 `baby-ai-laya-probe-main`에서, 예전 단계 일부는 `baby-ai-laya-probe`에서 돌아서 `data/`가 두 곳이다.

| 위치 | 무엇 | 크기 | 다시 만들 수 있음 |
|---|---|---|---|
| `-main/data/n5000_*.jsonl`, `n10000_*.jsonl` | 11b 봇 덤프 | 278 MB | 예(`stage11b dump`) |
| `-main/data/laya_rows_*.jsonl` | 학습 행(덤프 → laya 형식) | 약 210 MB | 예 |
| `-main/data/putnext_train.jsonl`, `gotolocal16_train.jsonl`, `gotolocal_eval.jsonl` | 10 · 9단계 덤프, 개발용 봇 궤적 | 약 20 MB | 예 |
| `baby-ai-laya-probe/data/gotolocal_*.jsonl`, `pickupdist_train.jsonl`, `demos_train.jsonl` | 2 ~ 8단계 덤프 | 약 15 MB | 예 |
| `-main/data/stage12_cache_gemini-decision-1_{text,image,both}.jsonl` | **Gemini Decision 1 응답 캐시**(11-17, 유료 호출 약 $1.24) | 38 MB | **아니오** — 다시 부르면 돈이 들고, 모델이 바뀌면 같은 답이 안 나온다 |
| `-main/data/stage12_cache_clef-flash.jsonl` | clef-flash 응답 캐시 | 2.7 MB | 로컬이라 다시 부를 수 있으나 모델 버전이 바뀌면 다름 |
| `baby-ai-laya-probe/data/stage5_cache_jev-1.14.0.jsonl` | **Jev(TypeSafe) 응답 캐시**(유료 API) | 2.6 MB | **아니오** |
| `baby-ai-laya-probe/data/stage5_cache_gemma4_12b-it-q8_0.jsonl` | Gemma 12B 응답 캐시(로컬) | 2.8 MB | 대체로 예 |
| `baby-ai-laya-probe/data/correct_log.jsonl`, `selfcheck_*.jsonl` | **MoKa가 직접 한 교정 기록**(4단계) | 0.4 MB | **아니오** |
| `baby-ai-laya-probe/data/sketch_baby/`, `itch_media_1117/`, `itch_page_*.md`, `screenshots/`, `*_shot*.png` | 그림 초안 · itch 페이지 초안 · 화면 | 약 38 MB | 그림은 seed로 다시 그릴 수 있음, 페이지 초안은 아니오 |
| 두 곳의 `run_*.sh`, `*.log` | 실행 스크립트 · 로그 | 작음 | 로그는 아니오(결과 json은 저장소에 있음) |
| 맥 `data/stage13_cache_afm-*.jsonl` | Apple 모델 응답 캐시(맥에만 있음) | — | 아니오 |

## 5. 게임 사용자 폴더 (Windows `%APPDATA%\Godot\app_userdata\BabyAI Laya- an AI in the room\`)

| 파일 | 무엇 | 크기 | 다시 만들 수 있음 |
|---|---|---|---|
| `correct_log.jsonl` | Correct 모드 기록(사람 교정 포함) | 1.9 MB | **아니오** |
| `test_runs\`, `long_rooms.jsonl` | 게임 안 300판 시험 원자료(`reports/game_test_run.md`) | 0.6 MB + | 시험은 다시 돌릴 수 있음 |
| `help_runs\` | 도움 시험 원자료 | — | 예 |
| `drive_log.jsonl`, `garage.json`, `puzzle_progress.json`, `demo_log.jsonl`, `copy_probe.jsonl` | 드라이브 · 퍼즐 기록, 진행 상태 | 작음 | **아니오**(사람이 둔 판) |

## 6. 디스크를 많이 쓰는 것

체크포인트 64 GB(40 × 1.6 GB)가 압도적이다. 그다음 venv · 캐시 약 10 GB, 데스크톱 빌드 2.5 GB, 웹 ONNX 2.0 GB, `data/` 약 0.7 GB.
이 저장소 것이 아닌 것으로 보이는 `~/laya-ft` · `~/laya-venv` 11 GB. 지우지 않았다.
