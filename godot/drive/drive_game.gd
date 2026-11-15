extends Control
## Drive mode: the game's front screen. Arrow keys drive, Space hands the wheel to the autopilot and back.
## The autopilot is drive/autopilot.gd (a small CNN, **not Laya**). It stops itself when it sees a view it has already
## driven through ("stuck") and the driver takes over. Every room is written to DriveLog (this device only).
## Rooms that took 35 turns or more, or were not finished, go to the garage to be driven again.
## The research screens (input text, seeds, recorded Laya replays) are in main.tscn, opened with the "Lab" button.
##
## Command line (after `--`):  --drivecheck=N   autopilot + scripted driver through N rooms, headless, then quit
##                             --shot=file.png [--scene=drive|stuck|win|card|garage] [--level=n]   one screenshot

const Autopilot := preload("res://drive/autopilot.gd")
const Rooms := preload("res://drive/rooms.gd")
const DriveLog := preload("res://drive/drivelog.gd")
const Main := preload("res://main.gd")

const W := 1320.0
const H := 860.0
const CELL := 84.0
const BOARD := Vector2(324, 112)            # top-left of the 8x8 room
const DIR_VEC := [Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(0, -1)]
const COLORS := {
	"red": Color("#e5484d"), "green": Color("#46a758"), "blue": Color("#3e7bfa"),
	"purple": Color("#9d5bd2"), "yellow": Color("#f5c518"), "grey": Color("#9aa0a6"),
}
const C_BG := Color("#0a0d14")
const C_AUTO := Color("#3ddc84")
const C_STUCK := Color("#ffa53d")
const C_MANUAL := Color("#38c6f4")
const C_FAIL := Color("#ff4d5e")
const C_CAR := Color("#ff7a45")
const C_TEXT := Color("#d6dbe3")
const C_MUTED := Color("#7d8796")
const AUTO_STEP := 0.2                       # seconds between autopilot moves
const GLIDE := 0.15                          # seconds a move takes on screen
const BATCH := 10                            # rooms per result card
const VIEW_HEADLIGHT := 1                    # same numbers as main.gd's view_mode (1 = AI's view, 2 = whole room)
const VIEW_WHOLE := 2

var rng := RandomNumberGenerator.new()
var ap := Autopilot.new()
var level := 1
var dlog := DriveLog.new()
var room := {}
var room_no := 0
var garage_idx := -1                         # >= 0 while re-driving a garage room
var pos := Vector2i.ZERO
var dir := 0
var turns := 0
var takeovers := 0
var auto_steps := 0
var trail: Array = []
var state := "manual"                        # manual | auto | stuck
var view_mode := VIEW_HEADLIGHT
var phase := "drive"                         # drive | win | fail | card | garage
var phase_t := 0.0
var auto_t := 0.0
var batch: Array = []                        # finished rooms of this batch (not garage re-drives)
var last_card: Array = []

var glide_from := Vector2.ZERO
var angle_from := 0.0
var glide_t := 1.0
var particles: Array = []
var ring_t := -1.0
var shake := 0.0
var clock := 0.0
var toast := ""
var toast_t := 0.0
var garage_cards: Array = []                 # [Rect2, index] of the open garage overlay
var card_garage_rect := Rect2()              # the garage key on the result card; empty when the garage is

var btn_garage: Button
var btn_level: Button
var shot_path := ""
var shot_frames := 0


func _ready() -> void:
	get_tree().auto_accept_quit = true        # main.gd turns this off for its server; drive mode quits normally
	rng.randomize()
	var args := _user_args()
	level = clampi(int(args.get("level", "1")), 1, 3)
	ap.load_level(level)
	_build_buttons()
	if args.has("drivecheck"):
		_drivecheck(int(args["drivecheck"]))
		get_tree().quit()
		return
	_new_room()
	shot_path = args.get("shot", "")
	if shot_path != "":
		_shot_setup(String(args.get("scene", "drive")))


func _user_args() -> Dictionary:
	var d := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		d[kv[0]] = kv[1] if kv.size() > 1 else "1"
	return d


# ---------------------------------------------------------------- buttons (top right)

func _build_buttons() -> void:
	var row := HBoxContainer.new()
	row.position = Vector2(W - 560, 26)
	row.size = Vector2(540, 40)
	row.alignment = BoxContainer.ALIGNMENT_END
	row.add_theme_constant_override("separation", 8)
	add_child(row)
	btn_level = _button(row, "", func(): _cycle_level())
	btn_garage = _button(row, "", func(): _toggle_garage())
	_button(row, "Puzzle", func(): _open_puzzle())
	_button(row, "Save log", func(): _save_log())
	_button(row, "Lab", func(): _open_lab())
	_sync_buttons()


func _button(parent: Node, text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.focus_mode = Control.FOCUS_NONE          # Space and arrows must reach the car, not a focused button
	b.add_theme_font_size_override("font_size", 16)
	for st in ["normal", "hover", "pressed"]:
		var sb := StyleBoxFlat.new()
		sb.bg_color = Color("#161b25") if st == "normal" else (Color("#202838") if st == "hover" else Color("#10141c"))
		sb.border_color = Color("#2c3546")
		sb.set_border_width_all(1)
		sb.set_corner_radius_all(8)
		sb.content_margin_left = 12
		sb.content_margin_right = 12
		sb.content_margin_top = 6
		sb.content_margin_bottom = 6
		b.add_theme_stylebox_override(st, sb)
	b.add_theme_color_override("font_color", C_TEXT)
	b.pressed.connect(cb)
	parent.add_child(b)
	return b


func _sync_buttons() -> void:
	btn_level.text = "Autopilot L%d" % level
	var n := DriveLog.garage().size()
	btn_garage.text = "Garage %d" % n if n > 0 else "Garage"


func _cycle_level() -> void:
	level = level % 3 + 1
	ap.load_level(level)
	_sync_buttons()
	_say("autopilot level %d" % level)


func _save_log() -> void:
	if DriveLog.read_all() == "":
		_say("no drives yet")
		return
	var where := DriveLog.export_file()
	_say("saved" if OS.has_feature("web") else where)


func _open_lab() -> void:
	_leave_room()
	Main.lab = true
	get_tree().change_scene_to_file("res://main.tscn")


func _open_puzzle() -> void:
	_leave_room()
	get_tree().change_scene_to_file("res://drive/puzzle.tscn")


func _say(t: String) -> void:
	toast = t
	toast_t = 2.5


# ---------------------------------------------------------------- rooms

func _new_room(ep := {}, gidx := -1) -> void:
	room_no += 1
	room = ep if not ep.is_empty() else Rooms.make(rng, 8, 8, "r%d" % room_no)
	garage_idx = gidx
	pos = Vector2i(int(room["start"]["x"]), int(room["start"]["y"]))
	dir = int(room["start"]["dir"])
	turns = 0
	takeovers = 0
	auto_steps = 0
	trail = [pos]
	glide_from = Vector2(pos)
	angle_from = _angle(dir)
	glide_t = 1.0
	if state == "stuck":
		state = "auto"
	ap.forget()
	auto_t = 0.0
	phase = "drive"
	dlog.begin(room, level, view_mode)


## The room ends without a result (skipped, garage picked, lab opened). Counts as unfinished if anything was driven.
func _leave_room() -> void:
	if phase != "drive" or turns == 0:
		return
	dlog.end("left", turns, takeovers)
	if garage_idx < 0:
		DriveLog.garage_add(room, "left", turns, level)
	_sync_buttons()


func _finish(result: String) -> void:
	dlog.end(result, turns, takeovers)
	if garage_idx >= 0:
		if result == "success":
			DriveLog.garage_remove(garage_idx)
	else:
		if DriveLog.belongs_in_garage(result, turns):
			DriveLog.garage_add(room, result, turns, level)
		batch.append({"result": result, "turns": turns, "par": int(room["par"]), "takeovers": takeovers,
			"auto": auto_steps})
	_sync_buttons()
	phase = "win" if result == "success" else "fail"
	phase_t = 0.0
	if result == "success":
		_burst()
	else:
		shake = 0.5


func _after_effect() -> void:
	if batch.size() >= BATCH:
		last_card = batch.duplicate()
		batch.clear()
		phase = "card"
		return
	_new_room()


# ---------------------------------------------------------------- moves

func _angle(d: int) -> float:
	return Vector2(DIR_VEC[d]).angle()


func _act(a: int, by: String, model: Dictionary, alarm: bool) -> void:
	dlog.step(pos, dir, by, a, int(model["action"]), model["scores"], alarm, view_mode)
	glide_from = _car_pos()
	angle_from = _car_angle()
	glide_t = 0.0
	if a == 0:
		dir = (dir + 3) % 4
	elif a == 1:
		dir = (dir + 1) % 4
	else:
		var f: Vector2i = pos + DIR_VEC[dir]
		if Rooms.is_free(room, f.x, f.y):
			pos = f
			trail.append(pos)
	turns += 1
	if by == "auto":
		auto_steps += 1
	var front: Vector2i = pos + DIR_VEC[dir]
	if Rooms.is_target(room, front.x, front.y):
		_finish("success")
	elif turns >= int(room["max_steps"]):
		_finish("timeout")


func _drive(a: int) -> void:
	if phase != "drive":
		return
	var alarm := state == "stuck"
	if state == "auto":
		takeovers += 1                       # the driver grabbed the wheel
	state = "manual"
	_act(a, "driver", ap.peek(room, pos, dir), alarm)


func _toggle_auto() -> void:
	if phase != "drive":
		return
	if state == "auto":
		takeovers += 1
		state = "manual"
	else:
		state = "auto"
		ap.forget()                          # a clean record after the driver had the wheel
		auto_t = AUTO_STEP


func _auto_tick() -> void:
	var d := ap.decide(room, pos, dir)
	if d["stuck"]:
		state = "stuck"                      # it would only repeat itself from here: hand over
		takeovers += 1
		return
	_act(int(d["action"]), "auto", d, false)


# ---------------------------------------------------------------- input and time

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if phase == "card":
			if card_garage_rect.has_point(event.position):
				_toggle_garage()
			else:
				phase = "drive"
				_new_room()
		elif phase == "garage":
			_garage_click(event.position)
		return
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	var k: int = event.keycode
	if phase == "card":
		if k in [KEY_SPACE, KEY_ENTER, KEY_ESCAPE]:
			_new_room()
		elif k == KEY_G and card_garage_rect.has_area():
			_toggle_garage()
		return
	if phase == "garage":
		if k in [KEY_G, KEY_ESCAPE]:
			_toggle_garage()
		return
	match k:
		KEY_UP, KEY_W:
			_drive(2)
		KEY_LEFT, KEY_A:
			_drive(0)
		KEY_RIGHT, KEY_D:
			_drive(1)
		KEY_SPACE:
			_toggle_auto()
		KEY_V:
			view_mode = VIEW_WHOLE if view_mode == VIEW_HEADLIGHT else VIEW_HEADLIGHT
		KEY_G:
			_toggle_garage()
		KEY_N:
			if phase == "drive":
				_leave_room()
				_new_room()


func _process(delta: float) -> void:
	clock += delta
	glide_t = minf(1.0, glide_t + delta / GLIDE)
	shake = maxf(0.0, shake - delta)
	toast_t = maxf(0.0, toast_t - delta)
	if ring_t >= 0.0:
		ring_t += delta
		if ring_t > 1.0:
			ring_t = -1.0
	for p in particles:
		p["v"] += Vector2(0, 260) * delta
		p["p"] += p["v"] * delta
		p["life"] -= delta
	particles = particles.filter(func(p): return p["life"] > 0.0)
	if phase == "drive" and state == "auto" and glide_t >= 1.0:
		auto_t += delta
		if auto_t >= AUTO_STEP:
			auto_t = 0.0
			_auto_tick()
	elif phase == "win" or phase == "fail":
		phase_t += delta
		if phase_t >= (1.2 if phase == "win" else 0.9):
			_after_effect()
	queue_redraw()
	if shot_path != "":
		shot_frames += 1
		if shot_frames == 12:
			get_viewport().get_texture().get_image().save_png(shot_path)
			for f in [DriveLog.path, DriveLog.garage_path]:      # the shot's own files, not the player's
				if FileAccess.file_exists(f):
					DirAccess.remove_absolute(ProjectSettings.globalize_path(f))
			get_tree().quit()


func _burst() -> void:
	var front: Vector2i = pos + DIR_VEC[dir]
	var c := _px(Vector2(front))
	var col: Color = COLORS.get(room["target"]["color"], Color.WHITE)
	for i in 70:
		var ang := rng.randf() * TAU
		var sp := rng.randf_range(90, 420)
		var pc: Color = [col, col.lightened(0.4), Color("#fff3c4"), Color.WHITE][i % 4]
		particles.append({"p": c, "v": Vector2(cos(ang), sin(ang)) * sp - Vector2(0, 120), "c": pc,
			"life": rng.randf_range(0.5, 1.1), "r": rng.randf_range(2.0, 5.0)})
	ring_t = 0.0


# ---------------------------------------------------------------- garage

func _toggle_garage() -> void:
	if phase == "garage":
		phase = "drive"
		return
	if phase == "card":
		_new_room()             # the batch is done; closing the garage drives this fresh room
	if phase != "drive":
		return
	phase = "garage"


func _garage_click(at: Vector2) -> void:
	for gc in garage_cards:
		if (gc[0] as Rect2).has_point(at):
			var items := DriveLog.garage()
			var i: int = gc[1]
			if i < items.size():
				phase = "drive"
				_leave_room()
				_new_room(items[i]["room"], i)
			return


# ---------------------------------------------------------------- drawing

func _px(cell: Vector2) -> Vector2:
	return BOARD + cell * CELL + Vector2(CELL, CELL) * 0.5


func _car_pos() -> Vector2:
	return glide_from.lerp(Vector2(pos), ease(glide_t, -2.0))


func _car_angle() -> float:
	return lerp_angle(angle_from, _angle(dir), ease(glide_t, -2.0))


func _in_view(c: Vector2i) -> bool:
	var rel: Vector2i = c - pos
	var f: int = rel.x * DIR_VEC[dir].x + rel.y * DIR_VEC[dir].y
	var r: Vector2i = DIR_VEC[(dir + 1) % 4]
	var s: int = rel.x * r.x + rel.y * r.y
	return f >= 0 and f <= 6 and absi(s) <= 3


func _glow(c: Vector2, r: float, col: Color, strength := 1.0) -> void:
	for i in 6:
		var k := 1.0 + i * 0.35
		draw_circle(c, r * k, Color(col, 0.07 * strength * (6 - i) / 6.0))


func _draw() -> void:
	draw_rect(Rect2(0, 0, W, H), C_BG)
	if room.is_empty():
		return
	var off := Vector2(rng.randf_range(-6, 6), rng.randf_range(-4, 4)) * shake if shake > 0.0 else Vector2.ZERO
	draw_set_transform(off)
	_draw_room()
	draw_set_transform(Vector2.ZERO)
	_draw_hud()
	_draw_hints()
	if phase == "fail":
		draw_rect(Rect2(0, 0, W, H), Color(C_FAIL, 0.18 * (1.0 - phase_t / 0.9)))
	if phase == "card":
		_draw_card()
	if phase == "garage":
		_draw_garage()
	if toast_t > 0.0:
		var font := get_theme_default_font()
		draw_string(font, Vector2(0, H - 70), toast, HORIZONTAL_ALIGNMENT_CENTER, W, 18,
			Color(C_TEXT, minf(1.0, toast_t)))


func _draw_room() -> void:
	var w := int(room["width"])
	var h := int(room["height"])
	var head := view_mode == VIEW_HEADLIGHT
	draw_rect(Rect2(BOARD - Vector2(10, 10), Vector2(w, h) * CELL + Vector2(20, 20)), Color("#0f131c"))
	for y in h:
		for x in w:
			var c := Vector2i(x, y)
			var r := Rect2(BOARD + Vector2(x, y) * CELL, Vector2(CELL, CELL))
			var lit := _in_view(c)
			var wall := x == 0 or y == 0 or x == w - 1 or y == h - 1
			var base := Color("#3b4252") if wall else Color("#1f2532")
			if head and not lit:
				base = Color("#0d1018") if not wall else Color("#151a24")
			elif head and lit:
				var rel: Vector2i = c - pos
				var dist := float(absi(rel.x) + absi(rel.y))
				base = base.lerp(Color("#3a3426"), clampf(0.55 - dist * 0.07, 0.0, 0.55))   # warm light near the car
			draw_rect(r.grow(-1.5), base)
	# the headlight edge
	if head:
		var col := Color(1.0, 0.86, 0.55, 0.25)
		for y in h:
			for x in w:
				var c := Vector2i(x, y)
				if not _in_view(c):
					continue
				for d in 4:
					var n: Vector2i = c + DIR_VEC[d]
					if _in_view(n) and n.x >= 0 and n.y >= 0 and n.x < w and n.y < h:
						continue
					var a := BOARD + Vector2(c) * CELL
					match d:
						0: draw_line(a + Vector2(CELL, 0), a + Vector2(CELL, CELL), col, 2.0)
						1: draw_line(a + Vector2(0, CELL), a + Vector2(CELL, CELL), col, 2.0)
						2: draw_line(a, a + Vector2(0, CELL), col, 2.0)
						3: draw_line(a, a + Vector2(CELL, 0), col, 2.0)
	# trail
	for i in range(maxi(0, trail.size() - 14), trail.size()):
		var t: Vector2i = trail[i]
		if head and not _in_view(t) and t != pos:
			continue
		draw_circle(_px(Vector2(t)), 4.0, Color(C_CAR, 0.25))
	for o in room["objects"]:
		var c := Vector2i(int(o["x"]), int(o["y"]))
		if head and not _in_view(c):
			continue
		_draw_object(o["type"], COLORS.get(o["color"], Color.WHITE), _px(Vector2(c)), CELL)
	if ring_t >= 0.0:
		var front: Vector2i = pos + DIR_VEC[dir]
		var col: Color = COLORS.get(room["target"]["color"], Color.WHITE)
		draw_arc(_px(Vector2(front)), CELL * (0.4 + ring_t * 2.2), 0, TAU, 48, Color(col, 1.0 - ring_t), 4.0)
	_draw_car()
	for p in particles:
		draw_circle(p["p"], p["r"], Color(p["c"], clampf(p["life"] * 1.5, 0.0, 1.0)))


## The goal sits on its own small plate (11-15, after reading three open-source Sokoban games: they mark the goal
## with a dedicated floor plate, no glow or motion). The plate is smaller than the cell so it reads as "this object",
## not "drive into this cell"; four corner marks in the target's colour stay visible around the object.
const PLATE := 62.0          # half of it, 31 px, clears a key or ball
const PLATE_MARK := 27.0
const PLATE_BOX := 74.0      # a box is 50 px wide, so its plate is larger
const PLATE_BOX_MARK := 33.0


func _is_target_px(m: Vector2) -> bool:
	for t in room["target"]["positions"]:
		if _px(Vector2(int(t[0]), int(t[1]))).distance_to(m) < 1.0:
			return true
	return false


func _draw_plate(m: Vector2, col: Color, kind: String) -> void:
	var size := PLATE_BOX if kind == "box" else PLATE
	var mark := PLATE_BOX_MARK if kind == "box" else PLATE_MARK
	var r := Rect2(m - Vector2(size, size) * 0.5, Vector2(size, size))
	_round(r, Color("#121722"), Color("#2a3242"), 9)
	var ink := Color(col, 0.95)
	for sx in [-1.0, 1.0]:
		for sy in [-1.0, 1.0]:
			var c := m + Vector2(sx, sy) * mark
			draw_line(c, c - Vector2(sx * 9, 0), ink, 3.0, true)
			draw_line(c, c - Vector2(0, sy * 9), ink, 3.0, true)


## Board objects without the base glow (only the goal plate speaks), with a small contact shadow so they sit on the floor.
func _draw_object(kind: String, col: Color, m: Vector2, cell: float) -> void:
	if cell == CELL:
		if _is_target_px(m):
			_draw_plate(m, col, kind)
		var sh := PackedVector2Array()
		for i in 20:
			var u := TAU * i / 20.0
			sh.append(m + Vector2(cos(u) * cell * 0.3, cell * 0.3 + sin(u) * cell * 0.08))
		draw_colored_polygon(sh, Color(0, 0, 0, 0.45))
	match kind:
		"ball":
			draw_circle(m, cell * 0.28, col)
			draw_circle(m + Vector2(-cell * 0.08, -cell * 0.08), cell * 0.08, Color(1, 1, 1, 0.35))
		"box":
			var r := Rect2(m - Vector2(cell * 0.3, cell * 0.3), Vector2(cell * 0.6, cell * 0.6))
			draw_rect(r, col.darkened(0.55))
			draw_rect(r, col, false, maxf(2.0, cell * 0.06))
			draw_line(r.position + Vector2(0, r.size.y * 0.35), r.position + Vector2(r.size.x, r.size.y * 0.35), col, maxf(1.5, cell * 0.04))
		"key":
			draw_circle(m + Vector2(-cell * 0.18, 0), cell * 0.14, col)
			draw_circle(m + Vector2(-cell * 0.18, 0), cell * 0.06, Color("#1f2532"))
			draw_rect(Rect2(m + Vector2(-cell * 0.05, -cell * 0.04), Vector2(cell * 0.33, cell * 0.08)), col)
			draw_rect(Rect2(m + Vector2(cell * 0.16, 0), Vector2(cell * 0.05, cell * 0.13)), col)
			draw_rect(Rect2(m + Vector2(cell * 0.24, 0), Vector2(cell * 0.05, cell * 0.1)), col)


func _draw_car() -> void:
	var m := _px(_car_pos())
	var ang := _car_angle()
	var f := Vector2.from_angle(ang)
	var p := Vector2(-f.y, f.x)
	var ring_col := _state_color()
	if state == "stuck":
		var pulse := 0.5 + 0.5 * sin(clock * 7.0)
		draw_arc(m, CELL * (0.46 + 0.05 * pulse), 0, TAU, 40, Color(C_STUCK, 0.5 + 0.5 * pulse), 4.0)
		_glow(m, CELL * 0.4, C_STUCK, 0.8 + pulse)
	else:
		_glow(m, CELL * 0.3, ring_col, 0.7)
	_glow(m, CELL * 0.2, C_CAR, 1.0)
	var pts := PackedVector2Array([m + f * CELL * 0.34, m - f * CELL * 0.26 + p * CELL * 0.27, m - f * CELL * 0.26 - p * CELL * 0.27])
	draw_colored_polygon(pts, C_CAR)
	pts.append(pts[0])
	draw_polyline(pts, Color("#ffe1cf"), 2.0, true)


func _state_color() -> Color:
	match state:
		"auto": return C_AUTO
		"stuck": return C_STUCK
	return C_MANUAL


func _draw_hud() -> void:
	var font := get_theme_default_font()
	# mission badge (top left): the target as a picture; dots = how many objects match
	var badge := Rect2(32, 22, 76, 76)
	_round(badge, Color("#161b25"), Color("#2c3546"))
	_draw_object(room["target"]["type"], COLORS.get(room["target"]["color"], Color.WHITE), badge.get_center(), 76)
	var n: int = room["target"]["positions"].size()
	if n > 1:
		for i in n:
			draw_circle(Vector2(badge.position.x + 10 + i * 10, badge.end.y + 10), 3.0, C_MUTED)
	if garage_idx >= 0:
		_wrench(Vector2(128, 40), 14, C_STUCK)
	# the indicator (top centre)
	var ic := Vector2(W / 2.0, 56)
	var col := _state_color()
	var k := 1.0
	if state == "stuck":
		k = 0.6 + 0.4 * (0.5 + 0.5 * sin(clock * 7.0))
	_glow(ic, 24, col, 1.4 * k)
	draw_circle(ic, 24, Color(col, 0.18 * k))
	draw_arc(ic, 24, 0, TAU, 40, Color(col, k), 3.0)
	match state:
		"auto": _chevrons(ic, col)
		"stuck": _wheel(ic, 13, col)
		_: _wheel(ic, 13, col)
	if state == "manual":
		draw_line(ic + Vector2(-15, 18), ic + Vector2(15, 18), Color(col, 0.6), 2.0)
	# batch progress: one dot per room of this batch
	for i in BATCH:
		var c := Vector2(W / 2.0 - (BATCH - 1) * 9.0 + i * 18.0, 98)
		if i < batch.size():
			draw_circle(c, 5.0, _result_color(batch[i]))
		else:
			draw_arc(c, 5.0, 0, TAU, 16, Color("#3a4354"), 1.5)
	# turns (left of board) and par
	var tc := C_TEXT if turns < 35 else C_STUCK
	draw_string(font, Vector2(150, 54), "%d" % turns, HORIZONTAL_ALIGNMENT_LEFT, -1, 30, tc)
	draw_string(font, Vector2(150, 80), "turns · par %d" % int(room["par"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, C_MUTED)


func _result_color(r: Dictionary) -> Color:
	if r["result"] != "success":
		return C_FAIL
	return C_AUTO if int(r["takeovers"]) == 0 else C_MANUAL


func _chevrons(c: Vector2, col: Color) -> void:
	for i in 2:
		var x := c.x - 7 + i * 9
		draw_polyline(PackedVector2Array([Vector2(x - 4, c.y - 8), Vector2(x + 4, c.y), Vector2(x - 4, c.y + 8)]), col, 3.0, true)


func _wheel(c: Vector2, r: float, col: Color) -> void:
	draw_arc(c, r, 0, TAU, 32, col, 3.0, true)
	draw_circle(c, r * 0.25, col)
	for a in [PI * 0.5, PI * 1.15, PI * 1.85]:
		draw_line(c, c + Vector2.from_angle(a) * r, col, 2.5, true)


func _wrench(c: Vector2, r: float, col: Color) -> void:
	draw_line(c + Vector2(-r, r), c + Vector2(r * 0.3, -r * 0.3), col, 4.0, true)
	draw_arc(c + Vector2(r * 0.45, -r * 0.45), r * 0.45, PI * 0.9, PI * 2.6, 16, col, 3.5, true)


func _round(r: Rect2, bg: Color, border: Color, radius := 12) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.border_color = border
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(radius)
	draw_style_box(sb, r)


func _keycap(at: Vector2, label: String, arrow := -1, width := 34.0) -> float:
	var r := Rect2(at, Vector2(width, 30))
	_round(r, Color("#161b25"), Color("#2c3546"), 6)
	var c := r.get_center()
	if arrow >= 0:
		var f := Vector2(DIR_VEC[arrow])
		var p := Vector2(-f.y, f.x)
		draw_colored_polygon(PackedVector2Array([c + f * 7, c - f * 5 + p * 6, c - f * 5 - p * 6]), C_TEXT)
	else:
		draw_string(get_theme_default_font(), Vector2(r.position.x, c.y + 6), label, HORIZONTAL_ALIGNMENT_CENTER, width, 15, C_TEXT)
	return width + 6


func _draw_hints() -> void:
	var y := H - 46
	var x := W / 2.0 - 250
	x += _keycap(Vector2(x, y), "", 2)
	x += _keycap(Vector2(x, y), "", 3)
	x += _keycap(Vector2(x, y), "", 0)
	x += 18
	x += _keycap(Vector2(x, y), "Space", -1, 70)
	_chevrons(Vector2(x + 14, y + 15), C_AUTO)
	x += 46
	x += _keycap(Vector2(x, y), "V")
	_eye(Vector2(x + 14, y + 15))
	x += 40
	x += _keycap(Vector2(x, y), "G")
	_wrench(Vector2(x + 14, y + 15), 8, C_MUTED)
	x += 40
	x += _keycap(Vector2(x, y), "N")
	draw_polyline(PackedVector2Array([Vector2(x + 6, y + 7), Vector2(x + 14, y + 15), Vector2(x + 6, y + 23)]), C_MUTED, 2.5, true)
	draw_line(Vector2(x + 18, y + 7), Vector2(x + 18, y + 23), C_MUTED, 2.5)


func _eye(c: Vector2) -> void:
	draw_arc(c + Vector2(0, 6), 11, PI * 1.15, PI * 1.85, 12, C_MUTED, 2.0, true)
	draw_arc(c - Vector2(0, 6), 11, PI * 0.15, PI * 0.85, 12, C_MUTED, 2.0, true)
	draw_circle(c, 3.0, C_MUTED)


func _draw_card() -> void:
	draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, 0.6))
	var r := Rect2(W / 2.0 - 330, 250, 660, 330)
	_round(r, Color("#121722"), Color("#2c3546"), 18)
	var font := get_theme_default_font()
	var tk := 0
	var au := 0
	var tu := 0
	var pa := 0
	var ok := 0
	for b in last_card:
		tk += int(b["takeovers"])
		au += int(b["auto"])
		tu += int(b["turns"])
		pa += int(b["par"])
		if b["result"] == "success":
			ok += 1
	var tiles := [Rect2(r.position + Vector2(30, 40), Vector2(180, 180)), Rect2(r.position + Vector2(240, 40), Vector2(180, 180)),
		Rect2(r.position + Vector2(450, 40), Vector2(180, 180))]
	for t in tiles:
		_round(t, Color("#1a2130"), Color("#2c3546"), 14)
	# 1. takeovers
	_wheel(tiles[0].get_center() - Vector2(0, 34), 26, C_MANUAL)
	draw_string(font, Vector2(tiles[0].position.x, tiles[0].position.y + 150), "%d" % tk, HORIZONTAL_ALIGNMENT_CENTER, 180, 40, C_TEXT)
	# 2. share of moves the autopilot made
	var share := float(au) / float(maxi(1, tu))
	var c2: Vector2 = tiles[1].get_center() - Vector2(0, 34)
	_glow(c2, 18, C_AUTO, 0.8)
	_chevrons(c2, C_AUTO)
	var bar := Rect2(tiles[1].position + Vector2(24, 112), Vector2(132, 10))
	draw_rect(bar, Color("#2a3242"))
	draw_rect(Rect2(bar.position, Vector2(bar.size.x * share, bar.size.y)), C_AUTO)
	draw_string(font, Vector2(tiles[1].position.x, tiles[1].position.y + 160), "%d%%" % roundi(share * 100), HORIZONTAL_ALIGNMENT_CENTER, 180, 30, C_TEXT)
	# 3. rooms: one dot each, and turns against the shortest route
	var c3: Vector2 = tiles[2].get_center() - Vector2(0, 40)
	draw_line(c3 + Vector2(-10, 22), c3 + Vector2(-10, -22), C_TEXT, 3.0)
	draw_colored_polygon(PackedVector2Array([c3 + Vector2(-10, -22), c3 + Vector2(16, -14), c3 + Vector2(-10, -6)]), C_STUCK)
	for i in last_card.size():
		draw_circle(Vector2(tiles[2].position.x + 18 + i * 16, tiles[2].position.y + 118), 5.0, _result_color(last_card[i]))
	draw_string(font, Vector2(tiles[2].position.x, tiles[2].position.y + 160), "%d / %d" % [tu, pa], HORIZONTAL_ALIGNMENT_CENTER, 180, 24, C_TEXT)
	var gn := DriveLog.garage().size()
	if gn == 0:
		card_garage_rect = Rect2()
		_keycap(Vector2(W / 2.0 - 35, r.end.y - 62), "Space", -1, 70)
		return
	var ky := r.end.y - 62
	_keycap(Vector2(W / 2.0 - 120, ky), "Space", -1, 70)
	_chevrons(Vector2(W / 2.0 - 34, ky + 15), C_AUTO)
	card_garage_rect = Rect2(Vector2(W / 2.0 + 10, ky), Vector2(110, 30))
	_keycap(card_garage_rect.position, "G")
	_wrench(Vector2(W / 2.0 + 64, ky + 15), 8, C_STUCK)
	draw_string(font, Vector2(W / 2.0 + 80, ky + 22), "%d" % gn, HORIZONTAL_ALIGNMENT_LEFT, -1, 18, C_STUCK)


func _draw_garage() -> void:
	draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, 0.72))
	_wrench(Vector2(W / 2.0, 70), 18, C_STUCK)
	garage_cards.clear()
	var items := DriveLog.garage()
	var font := get_theme_default_font()
	if items.is_empty():
		draw_string(font, Vector2(0, H / 2.0), "empty", HORIZONTAL_ALIGNMENT_CENTER, W, 22, C_MUTED)
		return
	var cols := 4
	var cw := 250.0
	var chh := 160.0
	var start := Vector2(W / 2.0 - (cols * (cw + 20) - 20) / 2.0, 120)
	var shown := mini(items.size(), 12)
	for i in shown:
		var idx := items.size() - 1 - i          # newest first
		var it: Dictionary = items[idx]
		var r := Rect2(start + Vector2((i % cols) * (cw + 20), (i / cols) * (chh + 20)), Vector2(cw, chh))
		var col := C_FAIL if it["result"] != "success" else C_STUCK
		_round(r, Color("#141a25"), col.darkened(0.3), 12)
		_mini_room(it["room"], r.position + Vector2(16, 16), 16.0)
		_draw_object(it["room"]["target"]["type"], COLORS.get(it["room"]["target"]["color"], Color.WHITE),
			r.position + Vector2(196, 50), 54)
		draw_string(font, Vector2(r.position.x + 160, r.position.y + 120), "%d" % int(it["turns"]), HORIZONTAL_ALIGNMENT_CENTER, 76, 26, col)
		draw_string(font, Vector2(r.position.x + 160, r.position.y + 144), "turns", HORIZONTAL_ALIGNMENT_CENTER, 76, 13, C_MUTED)
		draw_circle(r.position + Vector2(cw - 14, 14), 5.0, col)
		garage_cards.append([r, idx])
	if items.size() > shown:
		draw_string(font, Vector2(0, H - 80), "+%d" % (items.size() - shown), HORIZONTAL_ALIGNMENT_CENTER, W, 18, C_MUTED)


func _mini_room(ep: Dictionary, at: Vector2, c: float) -> void:
	var w := int(ep["width"])
	var h := int(ep["height"])
	for y in h:
		for x in w:
			var wall := x == 0 or y == 0 or x == w - 1 or y == h - 1
			draw_rect(Rect2(at + Vector2(x, y) * c, Vector2(c, c)).grow(-0.5), Color("#3b4252") if wall else Color("#1f2532"))
	for o in ep["objects"]:
		draw_circle(at + (Vector2(int(o["x"]), int(o["y"])) + Vector2(0.5, 0.5)) * c, c * 0.32, COLORS.get(o["color"], Color.WHITE))
	var s := Vector2(int(ep["start"]["x"]), int(ep["start"]["y"]))
	draw_circle(at + (s + Vector2(0.5, 0.5)) * c, c * 0.3, C_CAR)


# ---------------------------------------------------------------- headless check and screenshots

## Fewest-moves next action toward a matching object (the scripted "driver" for --drivecheck).
func _bfs_next(ep: Dictionary, p0: Vector2i, d0: int) -> int:
	var start := Vector3i(p0.x, p0.y, d0)
	var first := {start: -1}
	var frontier: Array = [start]
	while not frontier.is_empty():
		var nxt: Array = []
		for s in frontier:
			var f: Vector2i = Vector2i(s.x, s.y) + DIR_VEC[s.z]
			if Rooms.is_target(ep, f.x, f.y):
				return int(first[s]) if int(first[s]) >= 0 else 2
			var moves := [[0, Vector3i(s.x, s.y, (s.z + 3) % 4)], [1, Vector3i(s.x, s.y, (s.z + 1) % 4)]]
			if Rooms.is_free(ep, f.x, f.y):
				moves.append([2, Vector3i(f.x, f.y, s.z)])
			for m in moves:
				if not first.has(m[1]):
					first[m[1]] = m[0] if int(first[s]) < 0 else first[s]
					nxt.append(m[1])
		frontier = nxt
	return 2


## Autopilot through n rooms; when it stops itself, a scripted driver takes the wheel for 3 moves and hands back.
## Writes to user://drivecheck_* only and removes them afterwards.
func _drivecheck(n: int) -> void:
	var keep := [DriveLog.path, DriveLog.garage_path]
	DriveLog.path = "user://drivecheck_log.jsonl"
	DriveLog.garage_path = "user://drivecheck_garage.json"
	for f in [DriveLog.path, DriveLog.garage_path]:
		if FileAccess.file_exists(f):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(f))
	rng.seed = 7
	var alone := 0
	var helped := 0
	var failed := 0
	var stuck_events := 0
	var t0 := Time.get_ticks_msec()
	for r in n:
		_new_room()
		state = "auto"
		ap.forget()
		var drive_left := 0
		while phase == "drive":
			if state == "auto":
				_auto_tick()
				if state == "stuck":
					stuck_events += 1
					drive_left = 3
			else:
				_drive(_bfs_next(room, pos, dir))
				drive_left -= 1
				if drive_left <= 0 and phase == "drive":
					_toggle_auto()
		var last: Dictionary = batch[-1] if not batch.is_empty() else {}
		if last.is_empty() or last["result"] != "success":
			failed += 1
		elif int(last["takeovers"]) == 0:
			alone += 1
		else:
			helped += 1
		if batch.size() >= BATCH:
			batch.clear()
		state = "manual"
	var lines := DriveLog.read_all().strip_edges().split("\n")
	var ok := lines.size() == n
	var steps_ok := true
	for ln in lines:
		var rec = JSON.parse_string(ln)
		if not (rec is Dictionary) or int(rec["turns"]) != rec["steps"].size():
			steps_ok = false
		elif rec["steps"].any(func(st): return not st.has("vm")):
			steps_ok = false
	print("drivecheck: level %d, %d rooms: autopilot alone %d, with takeover %d, failed %d, stuck events %d, garage %d, %d ms"
		% [level, n, alone, helped, failed, stuck_events, DriveLog.garage().size(), Time.get_ticks_msec() - t0])
	print("drivecheck: log lines %d (%s), turns == logged steps and a view on every step: %s"
		% [lines.size(), "ok" if ok else "WRONG", "ok" if steps_ok else "WRONG"])
	for f in [DriveLog.path, DriveLog.garage_path]:
		if FileAccess.file_exists(f):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(f))
	DriveLog.path = keep[0]
	DriveLog.garage_path = keep[1]
	print("drivecheck: %s" % ("OK" if ok and steps_ok else "problem"))


func _shot_setup(scene: String) -> void:
	DriveLog.path = "user://shot_log.jsonl"
	DriveLog.garage_path = "user://shot_garage.json"
	rng.seed = 3
	_new_room()
	match scene:
		"stuck":
			for tries in 40:
				_new_room()
				state = "auto"
				ap.forget()
				while phase == "drive" and state == "auto":
					_auto_tick()
				if state == "stuck":
					break
			glide_t = 1.0
			particles.clear()
			ring_t = -1.0
		"win":
			state = "auto"
			while phase == "drive" and state == "auto":
				_auto_tick()
			phase_t = 0.25
			for p in particles:
				p["p"] += p["v"] * 0.25
		"card":
			for i in BATCH:
				batch.append({"result": "success" if i != 6 else "timeout", "turns": 5 + i % 4, "par": 5,
					"takeovers": 1 if i in [2, 5] else 0, "auto": 4 + i % 4})
			last_card = batch.duplicate()
			batch.clear()
			for i in 2:
				DriveLog.garage_add(Rooms.make(rng, 8, 8, "g%d" % i), "timeout", 40 + i, 1)
			phase = "card"
		"garage":
			for i in 5:
				DriveLog.garage_add(Rooms.make(rng, 8, 8, "g%d" % i), "timeout" if i % 2 == 0 else "success", 35 + i * 7, 1)
			_sync_buttons()
			phase = "garage"
		_:
			state = "auto"
			for i in 2:
				_auto_tick()
			glide_t = 1.0
