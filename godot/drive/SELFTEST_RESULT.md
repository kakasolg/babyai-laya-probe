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
- `drivelog.gd` — 점검 스크립트가 이 파일을 불러오지 않아 **한 줄도 실행되지 않았다**(기록 쓰기, 정비소, `export_file`, 35턴 규칙 모두).
  `--check-only --script res://drive/drivelog.gd`로 문법 검사만 했고 오류 출력은 없었다(`autopilot.gd`·`rooms.gd`도 같은 검사에서 출력 없음).
- 점검 스크립트가 쓰는 것 이외의 seed·방.
