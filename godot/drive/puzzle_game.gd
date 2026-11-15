extends "res://drive/drive_game.gd"
## Puzzle mode ("one move at a time"), designed in drive/PUZZLE.md. The level 1 autopilot drives rooms it cannot finish
## alone (data/puzzle_rooms_l1.json). When it stops, the moves the driver may make are shown; the driver makes exactly
## one, and the autopilot drives on with its record of where it has acted kept. Stars count the driver's moves against
## the room's fewest (`nudge_par`). A solved room lights the floor: from a lit cell, facing a lit side, that level's
## autopilot gets there alone — level 1 first, then 2 and 3 underneath.
##
## Rules (must match tools/small_policy/puzzle_pack.py word for word):
##   1. the autopilot never drives forward into a cell that is not free (autopilot.gd peek(..., true));
##   2. it stops when it is about to act from an (x, y, heading) it has already acted from in this room;
##   3. that record is never cleared in a room; the driver's moves are not added to it;
##   4. the driver's move: turn left, turn right, or forward when the cell ahead is free;
##   5. 64 turns in all (autopilot moves + the driver's); 6. success = a matching object directly ahead.
##
## Command line (after `--`):  --puzzlecheck[=N]   check the pack in Godot (all rooms; lit for every 10th), then quit
##                             --shot=file.png --scene=stuck|solved [--room=n]   one screenshot

const PACK := "res://data/puzzle_rooms_l1.json"
const KEEP := "res://data/puzzle_keep_l1.json"      # which pack rooms are played (written by --puzzlefilter)
const LIMIT := 64
const LIT_COLORS := [Color("#ffc94d"), Color("#3ddc84"), Color("#5b8cff")]   # levels 1, 2, 3
const LIT_AT := [0.25, 1.25, 2.25]                                          # seconds after the result when each shows

static var progress_path := "user://puzzle_progress.json"

var pack: Array = []
var pidx := 0
var best := {}               # room id -> most stars so far
var acted := {}              # Vector3i(x, y, heading) the autopilot has acted from in this room (rule 2, 3)
var nudges := 0
var stars := 0
var result := ""
var lit_t := 0.0
var lit_share := [0.0, 0.0, 0.0]
var move_rects := {}         # action -> Rect2 of its marker while stopped
var saving := true           # off for checks and screenshots


func _ready() -> void:
	get_tree().auto_accept_quit = true
	rng.randomize()
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(PACK))
	pack = parsed["rooms"] if parsed is Dictionary else []
	level = 1
	ap.load_level(1)
	view_mode = VIEW_WHOLE
	var args := _user_args()
	if args.has("puzzlecheck"):
		_puzzlecheck(int(args["puzzlecheck"]) if args["puzzlecheck"] != "1" else 0)
		get_tree().quit()
		return
	if args.has("puzzlefilter"):
		_puzzlefilter(int(args["puzzlefilter"]))
		get_tree().quit()
		return
	_apply_keep()
	_load_progress()
	_build_buttons()
	shot_path = args.get("shot", "")
	if shot_path != "":
		saving = false
		DriveLog.path = "user://shot_log.jsonl"
		DriveLog.garage_path = "user://shot_garage.json"
		pidx = clampi(int(args.get("room", "1")) - 1, 0, pack.size() - 1)
	_new_room()
	if shot_path != "":
		_puzzle_shot(String(args.get("scene", "stuck")))


func _build_buttons() -> void:
	var row := HBoxContainer.new()
	row.position = Vector2(W - 460, 26)
	row.size = Vector2(440, 40)
	row.alignment = BoxContainer.ALIGNMENT_END
	row.add_theme_constant_override("separation", 8)
	add_child(row)
	_button(row, "Drive", func(): _back_to_drive())
	_button(row, "Save log", func(): _save_log())


func _sync_buttons() -> void:
	pass


func _back_to_drive() -> void:
	_leave_room()
	get_tree().change_scene_to_file("res://drive/drive.tscn")


func _load_progress() -> void:
	if not FileAccess.file_exists(progress_path):
		return
	var p = JSON.parse_string(FileAccess.get_file_as_string(progress_path))
	if p is Dictionary:
		best = p.get("best", {})
		pidx = 0
		for i in pack.size():               # by room id, so a changed keep list does not skip rooms
			if pack[i]["seed"] == p.get("next_seed", ""):
				pidx = i


func _save_progress() -> void:
	if not saving:
		return
	var f := FileAccess.open(progress_path, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify({"next_seed": pack[pidx]["seed"], "best": best}))
		f.close()


# ---------------------------------------------------------------- rooms and rules

func _new_room(_ep := {}, _gidx := -1) -> void:
	room = (pack[pidx] as Dictionary).duplicate(true)
	garage_idx = -1
	pos = Vector2i(int(room["start"]["x"]), int(room["start"]["y"]))
	dir = int(room["start"]["dir"])
	turns = 0
	takeovers = 0
	auto_steps = 0
	nudges = 0
	acted.clear()
	trail = [pos]
	glide_from = Vector2(pos)
	angle_from = _angle(dir)
	glide_t = 1.0
	particles.clear()
	ring_t = -1.0
	state = "auto"
	auto_t = 0.0
	phase = "drive"
	result = ""
	lit_t = 0.0
	var free := 0
	for y in range(1, 7):
		for x in range(1, 7):
			if Rooms.is_free(room, x, y):
				free += 1
	for lv in 3:
		var bits := 0
		for v in room["lit"][str(lv + 1)]:
			bits += _bits(int(v))
		lit_share[lv] = float(bits) / float(maxi(1, free * 4))
	dlog.begin(room, 1, view_mode, {"mode": "puzzle", "nudge_par": int(room["nudge_par"])})


static func _bits(v: int) -> int:
	var n := 0
	for h in 4:
		if v & (1 << h):
			n += 1
	return n


func _leave_room() -> void:
	if phase != "drive" or turns == 0:
		return
	dlog.end("left", turns, nudges, {"nudges": nudges})


## Rule 2: stop before acting from a place already acted from. Rule 1 is in peek(..., true).
func _auto_tick() -> void:
	var key := Vector3i(pos.x, pos.y, dir)
	if acted.has(key):
		state = "stuck"
		return
	acted[key] = true
	var d := ap.peek(room, pos, dir, true)
	_act(int(d["action"]), "auto", d, false)


func _can_move(a: int) -> bool:
	if a != 2:
		return true
	var f: Vector2i = pos + DIR_VEC[dir]
	return Rooms.is_free(room, f.x, f.y)


## Rule 4: one move by the driver, then the autopilot drives on (its record kept, this place not added).
func _nudge(a: int) -> void:
	if phase != "drive" or state != "stuck" or not _can_move(a):
		return
	nudges += 1
	takeovers = nudges
	state = "auto"
	auto_t = 0.0
	_act(a, "driver", ap.peek(room, pos, dir, true), true)


func _finish(res: String) -> void:
	result = res
	stars = 0
	if res == "success":
		var par := int(room["nudge_par"])
		stars = 3 if nudges <= par else (2 if nudges == par + 1 else 1)
	dlog.end(res, turns, nudges, {"nudges": nudges})
	var id: String = room["seed"]
	if stars > int(best.get(id, 0)):
		best[id] = stars
	_save_progress()
	phase = "win" if res == "success" else "fail"
	phase_t = 0.0
	if res == "success":
		_burst()
	else:
		shake = 0.5


func _after_effect() -> void:
	phase = "result"
	lit_t = 0.0


func _next_room(step := 1) -> void:
	_leave_room()
	pidx = (pidx + step + pack.size()) % pack.size()
	_save_progress()
	_new_room()


func _retry() -> void:
	_leave_room()
	_new_room()


func _process(delta: float) -> void:
	super._process(delta)
	if phase == "result":
		lit_t += delta


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if phase == "result":
			_result_go()
		elif phase == "drive" and state == "stuck":
			for a in move_rects:
				if (move_rects[a] as Rect2).has_point(event.position):
					_nudge(a)
					return
		return
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	var k: int = event.keycode
	match k:
		KEY_LEFT, KEY_A:
			_nudge(0)
		KEY_RIGHT, KEY_D:
			_nudge(1)
		KEY_UP, KEY_W:
			_nudge(2)
		KEY_SPACE, KEY_ENTER:
			if phase == "result":
				_result_go()
		KEY_R:
			if phase == "drive" or phase == "result":
				_retry()
		KEY_N:
			if phase == "drive" or phase == "result":
				_next_room()
		KEY_V:
			view_mode = VIEW_WHOLE if view_mode == VIEW_HEADLIGHT else VIEW_HEADLIGHT


func _result_go() -> void:
	if result == "success":
		_next_room()
	else:
		_retry()


# ---------------------------------------------------------------- drawing

func _draw_room() -> void:
	super._draw_room()
	if phase == "result" and result == "success":
		_draw_lit()
		_draw_car()
	move_rects.clear()
	if phase == "drive" and state == "stuck" and glide_t >= 1.0:
		_draw_moves()


## Bit h of lit[level][(y-1)*6 + (x-1)]: from (x, y) facing h that level's autopilot gets there alone.
## Drawn as a small wedge pointing toward h; level 3 underneath, level 1 on top, each fading in at LIT_AT.
func _draw_lit() -> void:
	for lv in range(2, -1, -1):
		var a := clampf((lit_t - LIT_AT[lv]) / 0.5, 0.0, 1.0)
		if a <= 0.0:
			continue
		var cells: Array = room["lit"][str(lv + 1)]
		for i in 36:
			var v := int(cells[i])
			if v == 0:
				continue
			var c := _px(Vector2(i % 6 + 1, i / 6 + 1))
			for h in 4:
				if v & (1 << h) == 0:
					continue
				var f := Vector2(DIR_VEC[h])
				var p := Vector2(-f.y, f.x)
				draw_colored_polygon(PackedVector2Array([c + f * CELL * 0.43, c + f * CELL * 0.2 + p * CELL * 0.15,
					c + f * CELL * 0.2 - p * CELL * 0.15]), Color(LIT_COLORS[lv], 0.85 * a))


## The driver's choices while stopped: turn left, turn right, forward (only when the cell ahead is free).
func _draw_moves() -> void:
	var m := _px(Vector2(pos))
	var f := Vector2(DIR_VEC[dir])
	var p := Vector2(-f.y, f.x)          # the car's right
	var pulse := 0.6 + 0.4 * sin(clock * 5.0)
	var col := Color(C_MANUAL, pulse)
	for a in [0, 1, 2]:
		if not _can_move(a):
			continue
		var c: Vector2 = m + f * CELL if a == 2 else (m - p * CELL * 0.72 if a == 0 else m + p * CELL * 0.72)
		_glow(c, 16, C_MANUAL, 0.8)
		draw_circle(c, 21, Color("#0d1420", 0.92))
		draw_arc(c, 21, 0, TAU, 32, col, 2.0, true)
		if a == 2:
			draw_colored_polygon(PackedVector2Array([c + f * 12, c - f * 7 + p * 10, c - f * 7 - p * 10]), col)
		else:
			# a quarter turn drawn as the car would see it: up the forward side, then bending toward the new heading
			var side := -p if a == 0 else p
			var o := c - side * 7 - f * 3
			var a0 := (-side).angle()
			var diff := wrapf(f.angle() - a0, -PI, PI)
			draw_arc(o, 10, a0, a0 + diff, 12, col, 3.0, true)
			var tip := o + f * 10
			draw_colored_polygon(PackedVector2Array([tip + side * 8, tip + f * 6 - side * 1, tip - f * 6 - side * 1]), col)
		move_rects[a] = Rect2(c - Vector2(26, 26), Vector2(52, 52))


func _draw_hud() -> void:
	var font := get_theme_default_font()
	var badge := Rect2(32, 22, 76, 76)
	_round(badge, Color("#161b25"), Color("#2c3546"))
	_draw_object(room["target"]["type"], COLORS.get(room["target"]["color"], Color.WHITE), badge.get_center(), 76)
	var n: int = room["target"]["positions"].size()
	if n > 1:
		for i in n:
			draw_circle(Vector2(badge.position.x + 10 + i * 10, badge.end.y + 10), 3.0, C_MUTED)
	# which puzzle, and the most stars it has had
	draw_string(font, Vector2(150, 54), "%d" % (pidx + 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 30, C_TEXT)
	draw_string(font, Vector2(150, 80), "/ %d" % pack.size(), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, C_MUTED)
	var had := int(best.get(String(room["seed"]), 0))
	for i in 3:
		_star(Vector2(160 + i * 22, 104), 8, C_STUCK if i < had else Color("#2c3546"))
	# the indicator (top centre)
	var ic := Vector2(W / 2.0, 56)
	if phase == "result" or phase == "win" or phase == "fail":
		for i in 3:
			_star(ic + Vector2((i - 1) * 54, 0), 22, C_STUCK if i < stars else Color("#2c3546"), true)
	else:
		var col := _state_color()
		var k := 1.0
		if state == "stuck":
			k = 0.6 + 0.4 * (0.5 + 0.5 * sin(clock * 7.0))
		_glow(ic, 24, col, 1.4 * k)
		draw_circle(ic, 24, Color(col, 0.18 * k))
		draw_arc(ic, 24, 0, TAU, 40, Color(col, k), 3.0)
		if state == "auto":
			_chevrons(ic, col)
		else:
			_wheel(ic, 13, col)
	# the driver's moves so far against the fewest: one slot per move of nudge_par, filled as they are used
	var par := int(room["nudge_par"])
	var slots := maxi(par, nudges)
	for i in slots:
		var c := Vector2(W / 2.0 - (slots - 1) * 11.0 + i * 22.0, 100)
		if i < nudges:
			draw_circle(c, 6.0, C_MANUAL if i < par else C_STUCK)
		else:
			draw_arc(c, 6.0, 0, TAU, 16, Color(C_MANUAL, 0.45), 1.5)
	# turns used of the 64
	draw_string(font, Vector2(150, 140), "%d / %d" % [turns, LIMIT], HORIZONTAL_ALIGNMENT_LEFT, -1, 15, C_MUTED)
	# the lit share per level, shown as each level's light comes on
	if phase == "result" and result == "success":
		for lv in 3:
			var a := clampf((lit_t - LIT_AT[lv]) / 0.5, 0.0, 1.0)
			if a <= 0.0:
				continue
			var y := 330.0 + lv * 70.0
			var x := BOARD.x + 8 * CELL + 40
			var c := Vector2(x + 14, y)
			draw_colored_polygon(PackedVector2Array([c + Vector2(14, 0), c + Vector2(-6, -11), c + Vector2(-6, 11)]),
				Color(LIT_COLORS[lv], a))
			draw_string(font, Vector2(x + 40, y + 8), "%d" % (lv + 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color(C_TEXT, a))
			draw_string(font, Vector2(x + 70, y + 8), "%d%%" % roundi(lit_share[lv] * 100), HORIZONTAL_ALIGNMENT_LEFT, -1, 22,
				Color(LIT_COLORS[lv], a))


func _star(c: Vector2, r: float, col: Color, glow := false) -> void:
	if glow and col != Color("#2c3546"):
		_glow(c, r * 0.8, col, 0.9)
	var pts := PackedVector2Array()
	for i in 10:
		var ang := -PI / 2 + i * PI / 5
		pts.append(c + Vector2.from_angle(ang) * (r if i % 2 == 0 else r * 0.45))
	draw_colored_polygon(pts, col)


func _draw_hints() -> void:
	var y := H - 46
	var x := W / 2.0 - 200
	var stuck := phase == "drive" and state == "stuck"
	for a in [0, 2, 1]:
		var on := stuck and _can_move(a)
		var r := Rect2(Vector2(x, y), Vector2(34, 30))
		_round(r, Color("#161b25"), C_MANUAL if on else Color("#2c3546"), 6)
		var c := r.get_center()
		var fv := Vector2([Vector2.LEFT, Vector2.RIGHT, Vector2.UP][a])
		var pv := Vector2(-fv.y, fv.x)
		draw_colored_polygon(PackedVector2Array([c + fv * 7, c - fv * 5 + pv * 6, c - fv * 5 - pv * 6]),
			C_TEXT if on else Color(C_MUTED, 0.5))
		x += 40
	x += 18
	x += _keycap(Vector2(x, y), "V")
	_eye(Vector2(x + 14, y + 15))
	x += 40
	x += _keycap(Vector2(x, y), "R")
	draw_arc(Vector2(x + 14, y + 15), 8, 0.3, TAU - 0.6, 16, C_MUTED, 2.5, true)
	x += 40
	x += _keycap(Vector2(x, y), "N")
	draw_polyline(PackedVector2Array([Vector2(x + 6, y + 7), Vector2(x + 14, y + 15), Vector2(x + 6, y + 23)]), C_MUTED, 2.5, true)
	draw_line(Vector2(x + 18, y + 7), Vector2(x + 18, y + 23), C_MUTED, 2.5)
	if phase == "result":
		x += 40
		var go := Rect2(Vector2(x, y), Vector2(70, 30))
		_round(go, Color("#161b25"), C_STUCK if result == "success" else Color("#2c3546"), 6)
		draw_string(get_theme_default_font(), Vector2(x, y + 21), "Space", HORIZONTAL_ALIGNMENT_CENTER, 70, 15, C_TEXT)


# ---------------------------------------------------------------- headless check and screenshots

## (a) every room: the autopilot alone stops (not done, not out of turns);
## (b) every room: the stored answer, one move per stop, ends in success with nudge_par moves and nudge_turns turns;
## (c) every 10th room (or N rooms when given): "lit" recomputed for levels 1-3 with Godot's own arithmetic.
## Runs the game's own rule code for (a) and (b). Mismatching rooms are listed, not fixed.
func _puzzlecheck(n_lit: int) -> void:
	var t0 := Time.get_ticks_msec()
	saving = false
	var keep := DriveLog.path
	DriveLog.path = "user://puzzlecheck_log.jsonl"
	var bad_a: Array = []
	var bad_b: Array = []
	for i in pack.size():
		pidx = i
		_new_room()
		while phase == "drive" and state == "auto":
			_auto_tick()
		if not (phase == "drive" and state == "stuck"):
			bad_a.append("%s(%s, %d turns)" % [room["seed"], result if result != "" else phase, turns])
		_new_room()
		var sol: Array = room["nudge_solution"]
		var k := 0
		var guard := 0
		while phase == "drive" and guard < 200:
			guard += 1
			if state == "auto":
				_auto_tick()
			elif k < sol.size():
				_nudge(int(sol[k]))
				k += 1
			else:
				break
		var ok := result == "success" and nudges == int(room["nudge_par"]) and turns == int(room["nudge_turns"]) and k == sol.size()
		if not ok:
			bad_b.append("%s(%s, %d moves of %d, %d turns of %d)" % [room["seed"], result if result != "" else "stopped",
				nudges, int(room["nudge_par"]), turns, int(room["nudge_turns"])])
	var t1 := Time.get_ticks_msec()
	print("puzzlecheck: %d rooms; (a) autopilot alone stops: %d ok, %d not; (b) stored answer: %d ok, %d not; %d ms"
		% [pack.size(), pack.size() - bad_a.size(), bad_a.size(), pack.size() - bad_b.size(), bad_b.size(), t1 - t0])
	if not bad_a.is_empty():
		print("  (a) mismatch: ", ", ".join(bad_a))
	if not bad_b.is_empty():
		print("  (b) mismatch: ", ", ".join(bad_b))
	var pilots := []
	for lv in [1, 2, 3]:
		var p := Autopilot.new()
		p.load_level(lv)
		pilots.append(p)
	var idxs: Array = []
	if n_lit > 0:
		for i in mini(n_lit, pack.size()):
			idxs.append(i)
	else:
		for i in range(0, pack.size(), 10):
			idxs.append(i)
	var bad_c: Array = []
	for i in idxs:
		var ep: Dictionary = pack[i]
		for lv in 3:
			var cache := {}
			var want: Array = ep["lit"][str(lv + 1)]
			var diff := 0
			for c in 36:
				var x := c % 6 + 1
				var y := c / 6 + 1
				var got := 0
				if Rooms.is_free(ep, x, y):
					for h in 4:
						if _home_alone(pilots[lv], ep, cache, Vector2i(x, y), h):
							got |= 1 << h
				if got != int(want[c]):
					diff += 1
			if diff > 0:
				bad_c.append("%s L%d (%d cells)" % [ep["seed"], lv + 1, diff])
	print("puzzlecheck: lit recomputed for %d rooms x 3 levels: %d ok, %d not; %d ms"
		% [idxs.size(), idxs.size() * 3 - bad_c.size(), bad_c.size(), Time.get_ticks_msec() - t1])
	if not bad_c.is_empty():
		print("  (c) mismatch: ", ", ".join(bad_c))
	var lines := DriveLog.read_all().strip_edges().split("\n")
	var logged_ok := true
	for ln in lines:
		var rec = JSON.parse_string(ln)
		if not (rec is Dictionary) or rec.get("mode") != "puzzle" or not rec.has("nudges") or not rec.has("nudge_par") or int(rec["v"]) != 1:
			logged_ok = false
	print("puzzlecheck: log lines %d (%s: mode, nudge_par, nudges on every line, v 1)" % [lines.size(), "ok" if logged_ok else "NOT ok"])
	var all_ok := bad_a.is_empty() and bad_b.is_empty() and bad_c.is_empty() and logged_ok
	print("puzzlecheck: ", "OK" if all_ok else "MISMATCH (rooms listed above, not fixed)")
	if FileAccess.file_exists(DriveLog.path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(DriveLog.path))
	DriveLog.path = keep


## Only the rooms listed in KEEP are played (pack order kept). No KEEP file = all rooms.
func _apply_keep() -> void:
	if not FileAccess.file_exists(KEEP):
		return
	var k = JSON.parse_string(FileAccess.get_file_as_string(KEEP))
	if not (k is Dictionary):
		return
	var ids := {}
	for s in k["keep"]:
		ids[s] = true
	pack = pack.filter(func(e): return ids.has(e["seed"]))


## MoKa 11-15: stopping with the target only a few moves away makes people angry, not curious. Replays each room's
## stored answer with the game's rule code and keeps a room only when, at every stop, the target is more than
## `near` moves away (fewest turn/forward moves until it is directly ahead). Writes KEEP.
func _puzzlefilter(near: int) -> void:
	saving = false
	var keep_path := DriveLog.path
	DriveLog.path = "user://puzzlefilter_log.jsonl"
	var keep: Array = []
	var dropped: Array = []
	for i in pack.size():
		pidx = i
		_new_room()
		var sol: Array = room["nudge_solution"]
		var k := 0
		var closest := 999
		while phase == "drive":
			if state == "auto":
				_auto_tick()
			elif k < sol.size():
				var e := room.duplicate()
				e["start"] = {"x": pos.x, "y": pos.y, "dir": dir}
				closest = mini(closest, Rooms.par(e))
				_nudge(int(sol[k]))
				k += 1
			else:
				break
		if closest > near:
			keep.append(room["seed"])
		else:
			dropped.append(room["seed"])
	var out := {"what": "puzzle rooms played: at every stop on the stored answer the target is more than `near` moves away",
		"near": near, "pack": PACK, "kept": keep.size(), "dropped": dropped.size(), "keep": keep}
	var f := FileAccess.open(ProjectSettings.globalize_path(KEEP), FileAccess.WRITE)
	f.store_string(JSON.stringify(out))
	f.close()
	print("puzzlefilter: near %d -> kept %d, dropped %d of %d" % [near, keep.size(), dropped.size(), pack.size()])
	if FileAccess.file_exists(DriveLog.path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(DriveLog.path))
	DriveLog.path = keep_path


## From (p, h) with a clean record, does this autopilot get there alone under rules 1, 2, 5, 6?
func _home_alone(pilot, ep: Dictionary, cache: Dictionary, p: Vector2i, h: int) -> bool:
	var seen := {}
	var t := 0
	while t < LIMIT:
		var f: Vector2i = p + DIR_VEC[h]
		if Rooms.is_target(ep, f.x, f.y):
			return true
		var key := Vector3i(p.x, p.y, h)
		if seen.has(key):
			return false
		seen[key] = true
		if not cache.has(key):
			cache[key] = int(pilot.peek(ep, p, h, true)["action"])
		var a: int = cache[key]
		if a == 0:
			h = (h + 3) % 4
		elif a == 1:
			h = (h + 1) % 4
		elif Rooms.is_free(ep, f.x, f.y):
			p = f
		t += 1
	var f2: Vector2i = p + DIR_VEC[h]
	return Rooms.is_target(ep, f2.x, f2.y)


func _puzzle_shot(scene: String) -> void:
	while phase == "drive" and state == "auto":
		_auto_tick()
	if scene == "solved":
		var sol: Array = room["nudge_solution"]
		var k := 0
		while phase == "drive":
			if state == "auto":
				_auto_tick()
			elif k < sol.size():
				_nudge(int(sol[k]))
				k += 1
			else:
				break
		particles.clear()
		ring_t = -1.0
		_after_effect()
		lit_t = 4.0
	glide_t = 1.0
	_say("")
	toast_t = 0.0
