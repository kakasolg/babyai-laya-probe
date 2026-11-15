# drive 점검 결과

2026-11-15 [cloud]. `godot/drive/`의 GDScript를 처음으로 Godot에서 돌린 기록이다.

## 환경

- Godot `4.7.2.stable.official.ed1daf0bf` (Linux x86_64, `--headless`)
- 클라우드 `dsr-bot` 환경(Godot이 설치돼 있어 빌려 씀), Linux 6.18, CPU 4개
- 대상 커밋: `5749476` (`cloud/drive-engine`)

## 돌린 것

### 1. drive 점검

```
"$GODOT_PATH" --headless --path godot --script res://drive/selftest_drive.gd
```

두 번 돌렸고 두 번 다 종료 코드 0, 오류·경고 줄 없음. `--import`는 필요 없었다. 마지막(두 번째) 실행의 출력 전체:

```
Godot Engine v4.7.2.stable.official.ed1daf0bf - https://godotengine.org

view: 150 cases, mismatches 0
level 1: 200 vectors, max score difference 0.00005, same action 200/200, 25.7 ms per decision
level 1: 150 generated rooms, mean par 5.15, autopilot alone solved 97, stopped as stuck 53
level 2: 200 vectors, max score difference 0.00006, same action 200/200, 26.0 ms per decision
level 2: 150 generated rooms, mean par 5.15, autopilot alone solved 127, stopped as stuck 23
level 3: 200 vectors, max score difference 0.00011, same action 200/200, 26.5 ms per decision
level 3: 150 generated rooms, mean par 5.15, autopilot alone solved 141, stopped as stuck 9
drive selftest: OK
```

| 등급 | ms per decision (1회차) | ms per decision (2회차) | 혼자 푼 방 (150개 중) | 막혀서 멈춤 |
|---|---|---|---|---|
| 1 | 26.3 | 25.7 | 97 (65 %) | 53 |
| 2 | 26.2 | 26.0 | 127 (85 %) | 23 |
| 3 | 23.4 | 26.5 | 141 (94 %) | 9 |

- 걸음당 약 23~27 ms. 순수 Python 거울(약 75 ms)의 3분의 1쯤이다. 등급 사이의 차이는 실행마다 뒤바뀌므로 잡음이다(망 구조가 같다).
- 혼자 푼 방 수는 두 번 모두 같았다. README의 "Python 거울로 만든 방 150개에서 등급 3은 137개"와 숫자가 다른데,
  방을 만드는 난수가 달라 방이 다르기 때문으로 보인다(같은 방으로 비교해 보지는 않았다).

### 2. 기존 게임 점검 (`main.gd`는 손대지 않음)

```
"$GODOT_PATH" --headless --path godot -- --selftest
```

종료 코드 0. 마지막 줄:

```
selftest: episodes 35 steps 944  text mismatches 0  position mismatches 0  result mismatches 0
```

## GDScript에서 고친 것

없음. 문법·타입 오류 없이 처음 실행에서 끝까지 돌았다.

## 돌리지 않은 것 (확인 안 됨)

- 웹 빌드(브라우저)에서의 실행과 걸음당 시간 — 재지 않았다. 웹은 더 느릴 수 있다.
- Windows 실행 파일에서의 실행.
- 화면·조작·그리기 — 헤드리스라 아무것도 그리지 않았고, 드라이브 모드 UI는 아직 없다.
- `drivelog.gd` — 이 1차 실행(`5749476`)에서는 점검 스크립트가 이 파일을 불러오지 않아 한 줄도 실행되지 않았고,
  `--check-only`로 문법 검사만 했다. **처음 실행된 것은 아래 2차 실행**이다(기록 쓰기·읽기, 정비소, 35턴 규칙, 데스크톱 `export_file`).
- 점검 스크립트가 쓰는 것 이외의 seed·방.

---

## 2차 (2026-11-15) [cloud] — `drivelog.gd` 첫 실행

- 대상 커밋: `95a262c` (`cloud/drive-engine`). 환경은 1차와 같다(Godot `4.7.2.stable.official.ed1daf0bf`, Linux, `--headless`).
- `95a262c`가 Godot 없이 써 넣은 `_check_drivelog`와 `drivelog.gd`의 `static var path` / `garage_path`를 처음 돌렸다.

### 1. drive 점검

```
"$GODOT_PATH" --headless --path godot --script res://drive/selftest_drive.gd
```

한 번 돌렸고 종료 코드 **0**, 오류·경고 줄 없음. 출력 전체:

```
Godot Engine v4.7.2.stable.official.ed1daf0bf - https://godotengine.org

view: 150 cases, mismatches 0
level 1: 200 vectors, max score difference 0.00005, same action 200/200, 23.4 ms per decision
level 1: 150 generated rooms, mean par 5.15, autopilot alone solved 97, stopped as stuck 53
level 2: 200 vectors, max score difference 0.00006, same action 200/200, 24.3 ms per decision
level 2: 150 generated rooms, mean par 5.15, autopilot alone solved 127, stopped as stuck 23
level 3: 200 vectors, max score difference 0.00011, same action 200/200, 25.4 ms per decision
level 3: 150 generated rooms, mean par 5.15, autopilot alone solved 141, stopped as stuck 9
drivelog: wrote and read back 2 rooms, 35-turn rule, garage add/remove — OK
drive selftest: OK
```

`drivelog FAIL:` 줄은 하나도 없었다. 앞의 줄들은 1차와 같다(걸음당 시간만 잡음 범위에서 다름).

### 2. 기존 게임 점검

```
"$GODOT_PATH" --headless --path godot -- --selftest
```

종료 코드 0. 마지막 줄(1차와 같음):

```
selftest: episodes 35 steps 944  text mismatches 0  position mismatches 0  result mismatches 0
```

### 고친 것

- 동작을 바꾼 수정: **없음.** `drivelog.gd`와 `_check_drivelog`는 문법·타입 오류 없이 처음 실행에서 끝까지 돌았다
  (preload한 스크립트 상수로 `static var` 읽기·쓰기, `DirAccess.remove_absolute`, `split("\n")` 모두 문제없음).
- `selftest_drive.gd` 머리말 주석에 "5) drivelog.gd: ..." 두 줄 추가 — 새 점검 항목이 설명에 빠져 있어서(주석만, 코드 변화 없음).
- 이 문서: 2차 절 추가, 1차 절의 "`drivelog.gd`는 한 줄도 실행되지 않았다"를 "1차에서는 실행되지 않았고 2차에서 처음 실행됐다"로 고침.

### 점검이 남긴 파일 (`user://`)

실행 전에는 `~/.local/share/godot/` 자체가 없었다. 두 점검을 돌린 뒤
`~/.local/share/godot/app_userdata/BabyAI Laya- an AI in the room/` 안의 파일 전부:

```
logs/godot.log
logs/godot2026-11-15T14.10.22.log
```

둘 다 Godot 엔진이 실행마다 스스로 쓰는 로그다(점검 코드가 만든 게 아님).
`selftest_drive_log.jsonl`, `selftest_garage.json`, `drive_log.jsonl`, `garage.json`은 **없다** —
점검용 파일은 지워졌고 실제 기록 파일은 만들어지지도 건드려지지도 않았다.
(다만 이 컨테이너에는 원래 실제 기록이 없었으므로, "이미 있는 실제 기록이 그대로 남는다"를 직접 본 것은 아니다.
점검 중 경로가 `user://selftest_*`로 바뀌어 있다는 것과 끝난 뒤 실제 기록 파일이 생기지 않았다는 것까지만 확인했다.)

### 아직 돌리지 않은 것 (확인 안 됨)

- 웹 빌드(브라우저)에서의 실행과 걸음당 시간.
- Windows 실행 파일에서의 실행.
- 화면·조작·그리기 — 헤드리스라 아무것도 그리지 않았고, 드라이브 모드 UI는 아직 없다.
- 웹에서의 `export_file`(`JavaScriptBridge.download_buffer`) — 점검이 웹에서는 이 항목을 건너뛰며, 데스크톱 경로 반환만 확인했다.
- 웹의 `user://`(브라우저 저장소)에 기록이 실제로 남는지.
- 점검 스크립트가 쓰는 것 이외의 seed·방.
