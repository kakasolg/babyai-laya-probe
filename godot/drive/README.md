# drive — 반자동 자율주행 게임의 엔진 부분

2026-11-15 [cloud]가 엔진 부품을, [win]이 화면(`drive.tscn` · `drive_game.gd`)을 만들었다.
점검: Linux 헤드리스(`SELFTEST_RESULT.md`), Windows 데스크톱 결정당 14.8 ms, 웹 빌드(Chromium) 결정당 약 22 ms.

## 화면 (2026-11-15 [win], 시안 러프를 보고 MoKa가 "이대로 시작")

그냥 켜면 드라이브 화면이 먼저 뜬다(`main.gd`가 `drive/drive.tscn`으로 넘긴다). 기존 화면은 "Lab"(실험실)이다.

| 키 | 하는 일 |
|---|---|
| ↑ / W | 전진 · ← / A, → / D 제자리 회전 (자율주행 중에 누르면 넘겨받기) |
| Space | 자율주행 켜기 / 끄기 |
| V | 전조등 시야(기본, 앞 7×7칸만 밝음) ↔ 방 전체 |
| G | 정비소: 35턴 이상 걸렸거나 못 끝낸 방. 카드를 누르면 다시 달린다. 성공하면 정비소에서 빠진다 |
| N | 이 방 건너뛰기(못 끝낸 방으로 정비소에 들어간다) |

- 표시등(위 가운데): 초록 `>>` 자율주행 중 · 주황 운전대가 깜빡임 = 자율주행이 스스로 멈췄다(넘겨받으세요) · 파랑 운전대 = 직접 운전.
- 지시문은 왼쪽 위 그림 배지(맞는 물체가 여럿이면 아래 점). 숫자는 턴 수와 최소 턴(`par`). 35턴부터 주황.
- 성공: 대상에서 빛과 입자가 터지고 1.2초 뒤 다음 방. 실패(64턴): 화면이 붉게 흔들리고 다음 방.
- 위 점 10개: 이번 묶음의 방(초록 = 자율주행 혼자, 파랑 = 넘겨받아 성공, 빨강 = 실패). 10판마다 결과 카드:
  넘겨받은 횟수 · 자율주행이 움직인 비율 · 판별 점과 "턴 합 / par 합". Space로 계속.
- 넘겨받은 횟수 = 자율주행 중에 운전자가 키를 누르거나 Space로 끈 횟수 + 자율주행이 스스로 멈춘 횟수.
- 오른쪽 위: 자율주행 등급(누르면 1 → 2 → 3, 처음은 1) · 정비소 · "Save log"(웹은 내려받기, 데스크톱은 경로 표시) · Lab.
- 기록의 `view_mode`는 방을 시작할 때의 값이고, 걸음마다 그때의 시야가 `vm`으로 남는다(11-15 추가, 형식 `"v": 1` 그대로).
- 자율주행으로 끝난 방 뒤에는 다음 방도 자율주행으로 시작하고, 직접 운전으로 끝났으면 직접 운전으로 시작한다.

점검 (`-- --drivecheck=N`): 자율주행으로 N방을 달리고, 멈추면 대본 운전자(최단 경로)가 3걸음 몰고 돌려준다.
기록 줄 수와 "턴 = 기록된 걸음 수"를 확인한다. `user://drivecheck_*`에만 쓰고 지운다.
```
Godot_v4.7.2-stable_win64_console.exe --headless --path godot --scene res://drive/drive.tscn -- --drivecheck=200 [--level=3]
```
화면 사진: `-- --shot=파일.png --scene=drive|stuck|win|card|garage` (창이 잠깐 뜬다, `user://shot_*`만 쓰고 지움).

## 퍼즐 모드 (2026-11-15 [win], 설계는 [PUZZLE.md](PUZZLE.md))

- 들어가기: 드라이브 화면 오른쪽 위 **Puzzle** 버튼 → `puzzle.tscn`(`puzzle_game.gd`, 드라이브 화면을 물려받아 규칙·HUD만 바꿈).
  나가기는 **Drive** 버튼. 드라이브 화면의 동작과 기록은 그대로다(버튼 하나만 더해짐).
- 자율주행 1등급 고정, 방 전체가 보이는 상태로 시작(V로 헤드라이트). 묶음 300방을 차례로 낸다.
- 자율주행이 멈추면 차 옆에 갈 수 있는 걸음이 뜬다(왼쪽 돌기 · 오른쪽 돌기 · 앞이 비었으면 전진). 키 ←/A · →/D · ↑/W 또는 표시를 클릭.
  한 걸음 두면 자율주행이 지나온 자리 기록을 지우지 않고 다시 몬다. 멈춰 있지 않을 때 키는 먹지 않는다.
- 위 가운데: 도와줄 수 있는 칸(`nudge_par`개의 빈 동그라미)이 쓴 만큼 채워진다. 넘으면 주황.
- 풀면 별(도와준 횟수 = `nudge_par` 별 3 · +1 별 2 · 그 이상 별 1)과 함께 바닥 불빛: 칸마다 방향별 쐐기 넷.
  1등급(노랑) → 2등급(초록) → 3등급(파랑)이 1초 간격으로 켜지며, 아래 등급이 위에 그려진다. 오른쪽에 등급별 켜진 비율.
- 키: R 다시, N 다음 방, Space/클릭 다음(실패면 다시). 진행(다음 방 번호, 방마다 최고 별)은 `user://puzzle_progress.json`.
- 기록: 같은 `drive_log.jsonl`에 `"mode": "puzzle"`, `"nudge_par"`, `"nudges"`가 더해진다(`"v": 1` 그대로). 운전자 걸음 = 도와준 걸음.
- 막힌 전진 금지는 `autopilot.gd` `peek(..., true)`로, 퍼즐에서만 켠다.

묶음 점검(`-- --puzzlecheck`): 게임의 규칙 코드 그대로 (a) 300방 모두 자율주행 혼자 멈추는지, (b) `nudge_solution`대로 두면
`nudge_par`번 · `nudge_turns`걸음에 끝나는지, (c) 10번째 방마다(30방) 세 등급의 `lit`을 Godot 계산으로 다시 내 맞는지,
기록 줄의 새 필드를 본다. 어긋나는 방은 고치지 않고 번호만 찍는다. 약 4분.
```
Godot_v4.7.2-stable_win64_console.exe --headless --path godot res://drive/puzzle.tscn -- --puzzlecheck
```
11-15 결과: (a) 300/300 · (b) 300/300 · (c) 90/90 · 기록 300줄 OK — 어긋난 방 없음.
화면 사진: `res://drive/puzzle.tscn -- --shot=파일.png --scene=stuck|solved --room=n`.

## MoKa가 정한 게임의 모습 (2026-11-15)

- 방향키대로 움직인다. 특정 키를 누르면 **자율주행**한다.
- 자율주행이 막히거나 사용자가 원하면 넘겨받고, 다시 자율주행을 켤 수 있다.
- 성공하면 특수 효과로 성공했다고 느끼게 하고, **자동으로 다음 판**으로 넘어간다.
- **35턴 이상 걸려 성공했거나 실패한 판**은 모아 두고 나중에 다시 플레이할 수 있게 한다.
- 게임 안에서 일일이 설명하지 않는다. 설명은 GitHub에 둔다.
- **반자동 자율주행차 같은 느낌.** 더 게임답게 만들어 거부감이 없게.
- 사용자가 직접 운전한 것도 저장한다 — 이유는 몰라도 "이렇게 했다"는 기록.

## 부품

| 파일 | 하는 일 |
|---|---|
| `autopilot.gd` | 자율주행. `load_level(1~3)`, `decide(room, pos, dir)` → `{action, scores, stuck}`, `peek(...)`(기억을 건드리지 않고 "모델이라면 무엇을"), `forget()` |
| `rooms.gd` | 새 방 만들기 `make(rng, 8, 8, id)` — `episodes.json`과 같은 사전 모양이라 `main.gd`의 `_is_wall` · `_obj_at` · `_is_target` · `_obs_text`가 그대로 통한다. `par(room)` = 최소 턴 수 |
| `drivelog.gd` | 운전 기록(`user://drive_log.jsonl`, 방마다 한 줄)과 정비소(`user://garage.json`). `belongs_in_garage(result, turns)` = 35턴 규칙 |
| `selftest_drive.gd` | 헤드리스 점검 |
| `../data/policy_l1~3.json` | 모델 가중치(각 약 0.7 MB). `../data/*_test.json`, `drive_view_test.json`은 점검용 |

자율주행은 **Laya가 아니다.** 파라미터 66,787개짜리 작은 합성곱망이 MiniGrid 전문가 봇의 시범을 따라 배운 것이고,
앞쪽 7×7칸과 지시문의 색·종류만 본다. 기억이 없다. 게임과 페이지에 Laya라고 적지 않는다(녹화 재생은 계속 Laya다).

### 자율주행 등급

같은 구조를 시범 수만 달리해 학습했다. 숫자는 MiniGrid `GoToLocal`에서 **혼자** 끝낸 판 수(300판, 걸음 제한 64).

| 등급 | 시범 | 개발용 seed 10000~10299 | 새 판 seed 41000~41299 (한 번) | 느낌 |
|---|---|---|---|---|
| 1 | 998판 | 199 | 197 (66 %) | 세 판에 한 번 막힌다 |
| 2 | 2,994판 | 263 | 265 (88 %) | 여덟 판에 한 번 |
| 3 | 9,976판 | 289 | 284 (95 %) | 스무 판에 한 번 |

- 학습은 등급마다 한 번(seed 0). 다시 학습하면 몇 판씩 달라진다.
- `rooms.gd`가 만드는 방은 MiniGrid의 방과 똑같지 않다. Python 거울로 만든 방 150개에서 등급 3은 137개를 혼자 풀었다.
- 반복 끊기 규칙(R-reset)을 붙이면 거의 다 풀려서 운전자가 할 일이 없어진다. **이 게임에서는 규칙을 고치는 데 쓰지 않고,
  감지에만 쓴다**: 자율주행이 이미 지나온 장면에 다시 서면 `stuck = true`를 돌려주고 멈춘다("운전대를 잡으세요").
- 넘겨받아 한 걸음만 움직이고 돌려주면 다시 같은 데서 막히는 방이 많다(Python 모의: 등급 1에서 넘겨받은 방당 평균 8번).
  몇 걸음 직접 몰고 가서 돌려줘야 한다 → 다시 켜는 것은 사용자가 정하는 게 맞다.

### 쓰는 순서 (한 판)

```gdscript
const Autopilot := preload("res://drive/autopilot.gd")
const Rooms := preload("res://drive/rooms.gd")
const DriveLog := preload("res://drive/drivelog.gd")

var ap := Autopilot.new();  ap.load_level(1)
var rng := RandomNumberGenerator.new();  rng.randomize()
var room := Rooms.make(rng, 8, 8, "r%d" % n)        # room["par"] = 최소 턴 수
var log := DriveLog.new();  log.begin(room, ap.level, view_mode)
ap.forget()

# 자율주행 한 걸음
var d := ap.decide(room, pos, dir)
if d["stuck"]:
    pass        # 움직이지 말고 자율주행을 끈다 + 표시등. 그다음 사용자가 움직이면 ap.forget()
else:
    # d["action"] 0 왼쪽 돌기 · 1 오른쪽 돌기 · 2 전진 → 기존 _play_act 규칙대로 적용
    log.step(pos, dir, "auto", d["action"], d["action"], d["scores"], false)

# 사용자가 한 걸음 (자율주행이 꺼져 있을 때)
var m := ap.peek(room, pos, dir)                     # 화면에는 안 보이게, 모델이라면 무엇을 했을지
log.step(pos, dir, "driver", user_action, m["action"], m["scores"], alarm_was_on)
ap.forget()

# 판이 끝나면
log.end(result, turns, takeovers)
if DriveLog.belongs_in_garage(result, turns):
    DriveLog.garage_add(room, result, turns, ap.level)
```

방 사전은 `main.gd`의 `episodes`에 넣으면 기존 그리기·이동 코드가 그대로 쓴다(`steps`는 빈 배열, `generated: true`).

## 처음 제안한 10항목 ([cloud], 11-15) — 위 "화면"에 모두 반영. 10번(등급)은 버튼으로 고르게만 두었고 자동으로 오르지 않는다

1. **드라이브 모드**: 시작하면 바로 방 하나. 방향키(위 = 전진, 좌우 = 제자리 회전) · 자율주행 켜고 끄는 키 하나.
   자율주행 중 걸음 간격 0.15~0.25 s, 칸에서 칸으로 미끄러지듯.
2. **표시등 하나**: 자율주행 중 / 넘겨받으세요(`stuck`) / 직접 운전. 글 대신 색과 모양으로.
3. **전조등 시야를 기본으로**: 방은 어둡고 앞쪽 7×7칸만 밝게(지금의 "AI's view"). 사람과 모델이 같은 것을 보게 된다.
   `view_mode`는 기록에 남는다.
4. **지시문은 그림으로**: "go to the red key" 대신 빨간 열쇠 그림 하나.
5. **성공 효과 → 자동으로 다음 판.** 실패(걸음 제한)도 짧게 표시하고 넘어간다.
6. **점수**: 넘겨받은 횟수, 자율주행이 움직인 걸음의 비율, 최소 턴(`par`) 대비 턴 수. 10판 묶음 끝에 짧은 결과 카드.
7. **정비소**: `DriveLog.garage()`의 방을 골라 다시 달린다. 성공하면 `garage_remove`.
8. **연구용 화면(입력 글, seed, 녹화 재생, 교정)은 "실험실"로 분리**해 기본 화면에서 뺀다.
9. **기록 내려받기** 버튼 하나(`DriveLog.export_file()`). 기록은 그 기기에만 남고 어디로도 보내지 않는다.
10. 등급은 처음엔 1. 고르게 할지, 잘하면 올라가게 할지는 정하지 않았다.

## 점검 (먼저 돌려 달라)

```
Godot_v4.7.2-stable_win64_console.exe --headless --path godot --script res://drive/selftest_drive.gd
```

기대하는 출력: `view: 150 cases, mismatches 0` · 등급마다 `same action 200/200`, 점수 차 0.001 미만 ·
`ms per decision`(이 숫자를 알려 달라 — 순수 Python 거울은 걸음당 약 75 ms였다. 웹 빌드에서도 한 번) ·
만든 방 150개에서 혼자 푼 수(등급 3이 가장 많아야 한다) · 마지막 줄 `drive selftest: OK`.
문법 오류가 나면 그대로 알려 달라. [cloud]가 실행 없이 쓴 코드다.

## 다시 만들기

`tools/small_policy/export_levels.py <폴더>` — 시범 생성 → 세 등급 학습 → JSON · 점검 파일 쓰기(CPU, 몇 분, torch · minigrid 필요).
2026-11-15에 다시 돌려 `godot/data/`의 `policy_l1~3.json` · `policy_l1_test.json` · `drive_view_test.json`과
바이트 단위로 같은 파일이 나오는 것을 확인했다. 결과 숫자는 `tools/small_policy/levels_results.json`.

## 한계

- 8×8 방, 물체 8개(공·상자·열쇠, 여섯 색)에서만 학습하고 쟀다. 다른 크기에서는 성적을 모른다.
- 봇을 흉내 낸 모델이라 봇보다 잘할 수 없다.
- 운전 기록에는 사람이 본 것(보기 방식)이 섞인다. 방 전체를 보고 운전한 기록은 모델이 볼 수 없는 정보에 기대고 있을 수 있다.
- MiniGrid의 라이선스 표기는 두 곳이 다르다: 저장소 `LICENSE` 파일은 Apache License 2.0 전문, `pyproject.toml`과 PyPI 메타데이터는
  `MIT License`(2026-11-15 확인). `godot/data/PROVENANCE.md`에는 MIT로만 적혀 있다 — 공개 배포물의 표기를 정할 때 같이 봐 달라.
