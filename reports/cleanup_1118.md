# 저장소 정리 보고 (2026-11-18, [win] Moka-Windows-Dev)

지시: 보드 스레드 c7d1bc74, 11-18 cloud-claude 글 "MoKa 지시(11-18): 저장소 정리". MoKa가 이 세션에서 병합은 "문제 없으면 진행", 정리는 "Yes, start cleanup".
실험은 돌리지 않았다. 파일 · 브랜치 · 체크포인트를 지우지 않았고, 거부 규칙과 게임 코드를 바꾸지 않았다. 브랜치 `win/cleanup`(main `3534c3a`에서).

## 0. [win]이 더한 정리 항목 (보드 글에 없던 것)

1. **seed 거부 규칙의 빈틈**: 기본 거부 `guarded_seeds`가 60000~60299를 거부하지 않는다(9 · 10단계 코드만 거부). `reports/seeds.md` 2절. 고치지 않음.
2. **`data/`가 작업 폴더 두 곳에 나뉘어 있다**(`baby-ai-laya-probe/data` 79 MB, `baby-ai-laya-probe-main/data` 633 MB). 다시 만들 수 없는 응답 캐시도 두 곳에 흩어져 있다. `reports/checkpoints.md` 4절.
3. **다시 만들 수 없는 것 목록**: Gemini · Jev 응답 캐시, MoKa 교정 기록, 게임 사용자 폴더의 기록. 백업 여부는 MoKa 결정(6절).
4. **이 저장소 것이 아닌 것으로 보이는 WSL 폴더** `~/laya-ft`(4.0 GB) · `~/laya-venv`(6.9 GB) — 날짜가 이 저장소보다 앞선다. 확인만 하고 손대지 않았다.
5. **작업 폴더**: 기본 폴더 `baby-ai-laya-probe`는 옛 브랜치 `win/puzzle-mode`(2c0968a, main에 이미 들어감)에 머물러 있다. 병합용으로 `baby-ai-laya-probe-merge`를 새로 만들었다(지금 `win/cleanup`). `baby-ai-laya-probe-main`은 `win/stage14`. 어느 폴더를 main으로 둘지 정하면 헷갈림이 줄어든다.
6. **`win/stage14`는 아직 main에 없다**(push됨, 결과 보고 끝).

## 1. 병합 (끝)

- `c3b1045` Merge cloud/stage11b-cnn(`win/stage11b` 포함) → `3534c3a` Merge mac/stage13. 충돌 없음. main push, 보드 안내 글 올림.
- main에 없는 원격 브랜치: `mac/stage15`(진행 중), `win/stage14`(이번 결과, 병합 전).
- 이미 main에 들어간 브랜치(지우지 않음): cloud/drive-engine, cloud/puzzle-pack, cloud/stage11b-cnn, cloud/summary-four-tasks, cloud/summary-prior-art, mac/stage13, win/drive-ui, win/laya-desktop, win/putnext-replay, win/puzzle-mode, win/stage11, win/stage11b, win/stage12.

## 2. README 단계 목록 (끝, `3534c3a`)

11 = 11a + 11b(11b-2 · 11b-3 · 작은 CNN), 12 [win], 13 [mac], 14 [win], 15 [mac]. "네 과제 정리"는 번호 없는 정리 문서 줄로 옮겼고 7(GoToLocal 한 장 정리)은 남겼다(예전 글의 "7단계"가 어긋나지 않게). 게임 쪽은 "게임에서 잰 것" 줄. 이 브랜치에서 seed 장부 · 체크포인트 목록 줄을 더했다.

## 3. seed 장부 — `reports/seeds.md`

범위 표, 코드 거부 규칙 대조(60000대 빈틈), 다음 최종용 빈 범위 제안 **80000~80299**.
[cloud]가 적은 범위와 코드가 조금 다르다: 코드에는 41000~41299와 50000~50039만 보이고, 40000~40999 · 50040~50299는 보드 글에만 있다. 표에는 둘 다 "쓴 것으로 본다"로 적었다.

## 4. 체크포인트 · 저장소 밖 자료 — `reports/checkpoints.md`

체크포인트 40개(64 GB), 데스크톱 빌드 2.5 GB, 웹 ONNX 2.0 GB, venv · HF 캐시, `data/` 두 곳, 게임 사용자 폴더. 다시 만들 수 있는 것 / 없는 것을 나눴다.

## 5. 낡은 문서 · 풀리지 않은 것

### 지금 퍼즐 게임 (main 기준, `PUZZLE.md` 고칠 때 참고)
- **들어가는 길**: 게임을 그냥 켜면 퍼즐 모드가 첫 화면이다(`2c0968a`). 드라이브 화면은 "Drive" 버튼 뒤에 있다. 퍼즐 화면에 "Save log" 버튼.
- **방**: 묶음 `godot/data/puzzle_rooms_l1.json`(300방) 중 `godot/data/puzzle_keep_l1.json`이 고른 **106방만** 낸다(194방 뺌). 기준: "저장된 정답에서 멈출 때마다 목표가 5걸음(`near`)보다 멀다" — 목표 바로 앞에서 멈추는 쉬운 방을 뺐다.
- **별**: 그대로 — 도와준 횟수 ≤ `nudge_par` 3개, `nudge_par`+1이면 2개, 그 이상 1개, 못 끝내면 없음(`puzzle_game.gd` 219행). 방마다 가장 많이 받은 별을 `user://puzzle_progress.json`에 남긴다.
- **불빛**: 풀고 나면 바닥에 "여기서 이 방향이면 자율주행이 혼자 끝까지 가는 자리"가 켜진다(PUZZLE.md 설명과 같음).
- **그림 · 말**: 아기(8장) · 장난감(6장) 그림, 엄마 말풍선(왼쪽 판, 하트)과 아기 말풍선(머리 위). 엄마 말은 운전자가 한 걸음 둔 뒤에만 나온다.
- **기록**: 판이 끝나면 `user://drive_log.jsonl`에 한 줄(`mode: "puzzle"`, `nudge_par`, `nudges`, 결과, 걸음 수).

### 운전 기록이 게임 창에서 안 남던 문제 (11-15 "미해결")
- 코드(`godot/drive/drivelog.gd`)는 11-15 이후 바뀌지 않았다. 원인은 **찾지 못했다**.
- 지금 사용자 폴더의 `drive_log.jsonl`(85줄)에는 11-15 19:51 UTC 뒤에도 줄이 있다: 퍼즐 13줄(11-15 23:45 ~ 11-16 00:58 UTC), 드라이브 9줄 + 퍼즐 2줄(11-16 21:48 ~ 21:51 UTC). 이 줄들이 게임 창에서 쓴 것인지 헤드리스 시험에서 쓴 것인지는 기록으로 가릴 수 없다.
- 그래서 **"풀렸다"고 말하지 않는다.** 확인하는 가장 쉬운 길: MoKa가 게임 창에서 퍼즐 한 판을 끝내고 줄 수가 86으로 느는지 본다.
- 진단용 한 줄 후보(넣지 않음): `drivelog.gd` 47행에서 `FileAccess.open`이 `null`이면 `FileAccess.get_open_error()`를 `user://drive_log_error.txt`에 남긴다. 지금은 실패해도 아무 흔적이 없다.

### 커밋하지 않은 `.png.import` 14개와 `.uid`
- `baby-ai-laya-probe-main`의 `godot/drive/baby/*.png.import` · `toys/*.png.import` 변경은 **줄 끝(LF ↔ CRLF)만 다르다**(`git diff --ignore-cr-at-eol` 비어 있음, `--numstat`도 비어 있음). 내용 변경이 없으므로 **버리는 것이 맞다**고 정했다.
  다만 작업 트리 변경을 버리는 명령(`git checkout -- …`)은 자동 권한 검사가 막아서 **아직 버리지 못했다** — MoKa가 허락하면 버린다.
- `.uid` 파일(스크립트 6개)은 main에 이미 커밋돼 있다(8개). 기본 폴더에서 "추적 안 됨"으로 보이는 것은 그 폴더가 옛 브랜치(`win/puzzle-mode`)에 있기 때문이다. 할 일 없음.

### itch.io 공개판
- 지금 공개판 **1116c** = 11-16 14:22(PST)에 내보낸 웹 빌드. Put next 리플레이가 들어 있고 `licenses.txt` 포함. 그 리플레이를 넣은 커밋 `2163932`(14:23, main 병합 `893344a`)의 작업본에서 내보낸 것으로 본다(빌드 시각이 커밋보다 1분 앞이라 "커밋 직전 작업본"이다). 그 뒤의 데스크톱 · 도움 시험 변경(`c7a2593` 이후)은 웹판에 없다.

## 6. MoKa가 정할 것 (정하지 않고 적기만)

[cloud]가 적은 것:
1. 미세조정한 가중치를 공개할지.
2. 데스크톱 판(Laya 실시간)을 itch.io에 올릴지 — 올리면 `licenses.txt`에 onnxruntime(MIT), ModernBERT · laya(Apache-2.0).
3. 물건 16개 최종 seed(60000~60299)를 쓸지.
4. 이미 병합된 브랜치 13개를 지울지.
5. 14단계 뒤 다음 과제(여러 방 · 문 · 열쇠).

[win]이 더한 것:
6. `win/stage14`를 main에 병합할지.
7. 60000대 거부를 `guarded_seeds`에도 넣을지(`seeds.md` 2절).
8. 다음 최종 확인용으로 80000~80299를 잡을지.
9. 다시 만들 수 없는 자료(Gemini · Jev 캐시, 교정 기록, 게임 기록)를 백업할지, 어디에.
10. `~/laya-ft` · `~/laya-venv`(11 GB, 이 저장소 것이 아닌 것으로 보임)를 그대로 둘지.
11. `.png.import` 줄 끝 변경 14개를 버려도 되는지(내용 변경 없음).
12. 드라이브 기록 진단용 한 줄을 넣을지, 먼저 게임 창에서 한 판 돌려 확인할지.
13. 체크포인트 64 GB 중 다시 쓸 일이 적은 것(예: n100 · n500 s1 · s2)을 지울지 — 다시 만들 수 있다.
14. 기본 작업 폴더를 main에 둘지(지금은 옛 브랜치).

## 하지 않은 것

실험, 최종 seed, 파일 · 브랜치 · 체크포인트 삭제, 거부 규칙 변경, 게임 기능 추가, `.png.import` 버리기(권한 검사에 막힘), `PUZZLE.md` 고치기([cloud] 몫).
