extends Control
## Lab: Laya replays of the put-next task (BabyAI-PutNextLocal-v0, stage 10). Recorded once by
## probe/export_godot_putnext.py (checkpoint putnext-s0, no rule) and replayed; no model runs here.
## The room is drawn with the puzzle mode's baby and toy sprites (drive/baby, drive/toys).

const Main := preload("res://main.gd")
const DATA := "res://data/putnext_episodes.json"
const CELL := 80.0
const BOARD := Vector2(40, 112)
const PANEL_X := 740.0
const DIR_VEC := [Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(0, -1)]
const BABY_DIR := ["right", "down", "left", "up"]
const ACTS := ["turn left", "turn right", "forward", "pick up", "drop"]
const COLORS := {
	"red": Color("#e5484d"), "green": Color("#46a758"), "blue": Color("#3e7bfa"),
	"purple": Color("#9d5bd2"), "yellow": Color("#f5c518"), "grey": Color("#9aa0a6"),
}
const C_TEXT := Color("#d6dbe3")
const C_MUTED := Color("#8b95a5")
const C_CHOSEN := Color("#ff7a45")
const C_OK := Color("#46a758")
const C_FAIL := Color("#e5484d")
const C_KEY_BG := Color("#242830")
const C_KEY_BORDER := Color("#4A5260")

var episodes: Array = []
var ep_i := 0
var w_i := 0          # 0..steps.size(); steps[w_i] is the state before Laya's w_i-th choice, steps.size() = the end
var playing := false
var timer := 0.0
var delay := 0.5
var baby := {}
var toys := {}
var room_label: Label
var btn_run: Button


func _ready() -> void:
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	for n in ["up", "down", "left", "right", "grab", "cry"]:
		baby[n] = load("res://drive/baby/%s.png" % n)
	for n in ["ball", "key", "box"]:
		for v in ["a", "b"]:
			toys[n + "_" + v] = load("res://drive/toys/%s_%s.png" % [n, v])
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(DATA))
	episodes = parsed["episodes"] if parsed is Dictionary else []
	_build_bar()
	_set_ep(0)
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--putnextshot="):
			_shot(a.trim_prefix("--putnextshot="))


func _build_bar() -> void:
	var top := HBoxContainer.new()
	top.position = Vector2(16, 10)
	top.add_theme_constant_override("separation", 10)
	add_child(top)
	_btn(top, "< Lab", func(): Main.lab = true; get_tree().change_scene_to_file("res://main.tscn"))
	_btn(top, "<", func(): _set_ep(ep_i - 1))
	room_label = Label.new()
	room_label.custom_minimum_size = Vector2(170, 0)
	room_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	room_label.add_theme_color_override("font_color", Color.WHITE)
	top.add_child(room_label)
	_btn(top, ">", func(): _set_ep(ep_i + 1))
	_btn(top, "Next failure", func(): _next_failure())
	btn_run = _btn(top, "Play", func(): _toggle_run())
	_btn(top, "Restart", func(): w_i = 0; playing = false; _refresh())


func _btn(parent: Node, text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.focus_mode = Control.FOCUS_NONE
	var sb := StyleBoxFlat.new()
	sb.bg_color = C_KEY_BG
	sb.border_color = C_KEY_BORDER
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(6)
	sb.content_margin_left = 12
	sb.content_margin_right = 12
	sb.content_margin_top = 6
	sb.content_margin_bottom = 6
	for s in ["normal", "hover", "pressed"]:
		b.add_theme_stylebox_override(s, sb)
	b.add_theme_color_override("font_color", C_TEXT)
	b.pressed.connect(cb)
	parent.add_child(b)
	return b


func _ep() -> Dictionary:
	return episodes[ep_i] if not episodes.is_empty() else {}


func _set_ep(i: int) -> void:
	if episodes.is_empty():
		return
	ep_i = posmod(i, episodes.size())
	w_i = 0
	playing = false
	_refresh()


func _next_failure() -> void:
	for k in range(1, episodes.size() + 1):
		var j := (ep_i + k) % episodes.size()
		if episodes[j]["result"] != "success":
			_set_ep(j)
			return


func _toggle_run() -> void:
	if w_i >= _ep()["steps"].size():
		w_i = 0
	playing = not playing
	timer = 0.0
	_refresh()


func _refresh() -> void:
	if not episodes.is_empty():
		room_label.text = "Room %d of %d · seed %d" % [ep_i + 1, episodes.size(), int(_ep()["seed"])]
	btn_run.text = "Pause" if playing else "Play"
	queue_redraw()


func _process(delta: float) -> void:
	if not playing:
		return
	timer += delta
	if timer >= delay:
		timer = 0.0
		w_i += 1
		if w_i >= _ep()["steps"].size():
			w_i = _ep()["steps"].size()
			playing = false
		_refresh()


func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed):
		return
	var n: int = _ep()["steps"].size()
	match event.keycode:
		KEY_RIGHT, KEY_D:
			w_i = mini(w_i + 1, n)
			playing = false
		KEY_LEFT, KEY_A:
			w_i = maxi(w_i - 1, 0)
			playing = false
		KEY_SPACE:
			_toggle_run()
			return
		KEY_UP, KEY_W:
			_set_ep(ep_i - 1)
			return
		KEY_DOWN, KEY_S:
			_set_ep(ep_i + 1)
			return
		KEY_F:
			_next_failure()
			return
		KEY_ESCAPE:
			Main.lab = true
			get_tree().change_scene_to_file("res://main.tscn")
			return
		_:
			return
	_refresh()


## The state on screen: a step record, or the end of the episode.
func _state() -> Dictionary:
	var e := _ep()
	return e["steps"][w_i] if w_i < e["steps"].size() else e["end"]


func _look(kind: String) -> String:
	return "a" if (str(_ep().get("seed", "")) + kind).hash() % 2 == 0 else "b"


func _px(c: Vector2i) -> Vector2:
	return BOARD + Vector2(c) * CELL + Vector2(CELL, CELL) * 0.5


func _same(o, d: Dictionary) -> bool:
	return o is Dictionary and o["type"] == d["type"] and o["color"] == d["color"]


# ---------------------------------------------------------------- drawing

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("#0a0d14"))
	if episodes.is_empty():
		return
	_draw_room()
	_draw_panel()
	_draw_hints()


func _draw_room() -> void:
	var e := _ep()
	var st := _state()
	var w := int(e["width"])
	var h := int(e["height"])
	draw_rect(Rect2(BOARD - Vector2(8, 8), Vector2(w, h) * CELL + Vector2(16, 16)), Color("#0f131c"))
	for y in h:
		for x in w:
			var wall := x == 0 or y == 0 or x == w - 1 or y == h - 1
			var r := Rect2(BOARD + Vector2(x, y) * CELL, Vector2(CELL, CELL))
			draw_rect(r, Color("#3a404c") if wall else Color("#1c212a"))
			draw_rect(r, Color("#12161d"), false, 1.0)

	# the baby's path so far
	var steps: Array = e["steps"]
	for i in range(1, mini(w_i + 1, steps.size() + 1)):
		var a := Vector2i(int(steps[i - 1]["x"]), int(steps[i - 1]["y"]))
		var bst: Dictionary = steps[i] if i < steps.size() else e["end"]
		var b := Vector2i(int(bst["x"]), int(bst["y"]))
		if a != b:
			draw_line(_px(a), _px(b), Color(1, 0.55, 0.3, 0.3), 4.0)

	# toys; "1" = the toy to carry, "2" = the toy to put it next to
	var font := get_theme_default_font()
	for o in st["objects"]:
		var c := Vector2i(int(o["x"]), int(o["y"]))
		var col: Color = COLORS.get(o["color"], Color.WHITE)
		var tag := "1" if _same(o, e["move"]) else ("2" if _same(o, e["fixed"]) else "")
		if tag != "":
			_draw_corners(_px(c), col)
		_draw_toy(String(o["type"]), col, _px(c), 1.0)
		if tag != "":
			_badge(_px(c) + Vector2(CELL * 0.32, -CELL * 0.32), tag, col)

	# the baby: heading picks the sprite; at the end it grabs (success) or cries (timeout)
	var pos := Vector2i(int(st["x"]), int(st["y"]))
	var m := _px(pos)
	var pose: String = BABY_DIR[int(st["dir"])]
	if w_i >= steps.size():
		pose = "grab" if e["result"] == "success" else "cry"
	var sh := PackedVector2Array()
	for i in 20:
		var u := TAU * i / 20.0
		sh.append(m + Vector2(cos(u) * 26.0, 28.0 + sin(u) * 6.0))
	draw_colored_polygon(sh, Color(0, 0, 0, 0.45))
	var tex: Texture2D = baby.get(pose)
	if tex != null:
		var sz := tex.get_size() * 0.95
		draw_texture_rect(tex, Rect2(m + Vector2(-sz.x * 0.5, 34.0 - sz.y), sz), false)
	# facing: a small chevron on the cell edge
	var f := Vector2(DIR_VEC[int(st["dir"])])
	var p := Vector2(-f.y, f.x)
	var tip := m + f * CELL * 0.47
	draw_colored_polygon(PackedVector2Array([tip, tip - f * 10 + p * 8, tip - f * 10 - p * 8]), C_CHOSEN)
	# carried toy over the baby's head
	var carry = st.get("carrying")
	if carry is Dictionary:
		var cm := m + Vector2(0, -CELL * 0.48)
		draw_circle(cm, 21, Color("#0f131c"))
		draw_arc(cm, 21, 0, TAU, 32, Color("#f5c518"), 2.0)
		_draw_toy(String(carry["type"]), COLORS.get(carry["color"], Color.WHITE), cm, 0.62)
		if _same(carry, _ep()["move"]):
			_badge(cm + Vector2(19, -15), "1", COLORS.get(carry["color"], Color.WHITE))


func _draw_toy(kind: String, col: Color, m: Vector2, scale: float) -> void:
	var tex: Texture2D = toys.get(kind + "_" + _look(kind))
	if tex == null:
		draw_circle(m, CELL * 0.28 * scale, col)
		return
	var sz := tex.get_size() * (CELL / 84.0) * scale
	draw_texture_rect(tex, Rect2(m - sz * 0.5, sz), false, col.lightened(0.15))


func _draw_corners(m: Vector2, col: Color) -> void:
	var k := CELL * 0.42
	for sx in [-1.0, 1.0]:
		for sy in [-1.0, 1.0]:
			var c := m + Vector2(sx, sy) * k
			draw_line(c, c - Vector2(sx * 10, 0), col, 3.0, true)
			draw_line(c, c - Vector2(0, sy * 10), col, 3.0, true)


func _badge(c: Vector2, t: String, col: Color) -> void:
	draw_circle(c, 11, Color("#0a0d14"))
	draw_arc(c, 11, 0, TAU, 24, col, 2.0)
	draw_string(get_theme_default_font(), c + Vector2(-5, 6), t, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color.WHITE)


func _draw_panel() -> void:
	var e := _ep()
	var font := get_theme_default_font()
	var x := PANEL_X
	var steps: Array = e["steps"]
	draw_string(font, Vector2(x, 128), String(e["mission"]), HORIZONTAL_ALIGNMENT_LEFT, 560, 22, Color.WHITE)
	draw_string(font, Vector2(x, 156), "1 = the toy to carry   2 = put it next to this one", HORIZONTAL_ALIGNMENT_LEFT, -1, 15, C_MUTED)
	var line := "Step %d of %d   ·   expert bot needs %s" % [mini(w_i + 1, steps.size()), steps.size(),
		str(int(e["bot_steps"])) if e["bot_steps"] != null else "—"]
	draw_string(font, Vector2(x, 186), line, HORIZONTAL_ALIGNMENT_LEFT, -1, 17, C_TEXT)
	if w_i >= steps.size():
		var ok: bool = e["result"] == "success"
		draw_string(font, Vector2(x + 390, 186), "Done!" if ok else "Out of steps (%d)" % int(e["max_steps"]),
			HORIZONTAL_ALIGNMENT_LEFT, -1, 18, C_OK if ok else C_FAIL)

	# five scores
	var y0 := 214.0
	draw_string(font, Vector2(x, y0), "Laya's scores for the five choices (longer bar = more confident)", HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color("#b8c0cc"))
	if w_i < steps.size():
		var st: Dictionary = steps[w_i]
		for i in ACTS.size():
			var a: String = ACTS[i]
			var pr: float = float(st["probs"].get(a, 0.0))
			var y := y0 + 14 + i * 40
			var chosen: bool = a == st["choice"]
			draw_string(font, Vector2(x, y + 24), a, HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color.WHITE if chosen else C_MUTED)
			draw_rect(Rect2(x + 110, y + 6, 300, 26), Color("#1b1f26"))
			draw_rect(Rect2(x + 110, y + 6, 300 * pr, 26), C_CHOSEN if chosen else Color("#4a5260"))
			draw_string(font, Vector2(x + 420, y + 26), "%d%%" % roundi(pr * 100), HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color.WHITE)
			if a == st["bot"]:
				draw_string(font, Vector2(x + 475, y + 26), "<- expert", HORIZONTAL_ALIGNMENT_LEFT, -1, 16, C_OK)

	# the exact text Laya was given
	var ty := 446.0
	draw_rect(Rect2(x - 8, ty, 568, 300), Color("#11141a"))
	draw_rect(Rect2(x - 8, ty, 568, 300), Color("#2d3440"), false, 1.0)
	var title := "What Laya reads at this step" if w_i < steps.size() else "End of the room"
	draw_string(font, Vector2(x + 4, ty + 26), title, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, C_MUTED)
	if w_i < steps.size():
		var lines: PackedStringArray = String(steps[w_i]["input"]).split("\n")
		for i in mini(lines.size(), 10):
			draw_string(font, Vector2(x + 4, ty + 56 + i * 24), lines[i], HORIZONTAL_ALIGNMENT_LEFT, 548, 17,
				Color("#f5c518") if lines[i].begins_with("carrying") else C_TEXT)


func _draw_hints() -> void:
	var font := get_theme_default_font()
	var t := "Space play / pause    Left / Right one step    Up / Down room    F next failure    Esc back to Lab"
	draw_string(font, Vector2(BOARD.x, 806), t, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, C_MUTED)
	draw_string(font, Vector2(BOARD.x, 834),
		"Recorded walks of Laya (fine-tuned putnext-s0, no rule), replayed. The model does not run in this game.",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color("#5d6675"))


## --putnextshot=<path>[,room,step]: save one frame and quit (headless check).
func _shot(arg: String) -> void:
	var parts := arg.split(",")
	if parts.size() > 1:
		_set_ep(int(parts[1]))
	if parts.size() > 2:
		w_i = mini(int(parts[2]), _ep()["steps"].size())
		_refresh()
	await get_tree().process_frame
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(parts[0])
	get_tree().quit()
