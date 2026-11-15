extends Control
## BabyAI GoToLocal viewer/game.
## "Play": the player walks the same room with the same three moves the model has.
## "Watch Laya": replays of the fine-tuned Laya model (exported by probe/export_godot.py).
## "Correct": the stage-4 correction loop, live. The model runs in WSL (probe/correct_server.py, started
##         by the game if needed); corrections and memos are logged there, never trained on.

const CELL := 72
const DIR_VEC := [Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(0, -1)]
const DIR_NAME := ["east", "south", "west", "north"]
const ACTS := ["turn left", "turn right", "forward"]
const ACT_TXT := {"turn left": "turn left", "turn right": "turn right", "forward": "forward"}
const COLORS := {
	"red": Color("#e5484d"), "green": Color("#46a758"), "blue": Color("#3e7bfa"),
	"purple": Color("#9d5bd2"), "yellow": Color("#f5c518"), "grey": Color("#9aa0a6"),
}
const VIEW_TXT := ["text only (same as the AI)", "AI's view", "whole room"]
# keyboard hint badges under the board; arrow keys are drawn, not typed (the web default font has no arrow glyphs)
const ARROW_KEYS := {"up": Vector2(0, -1), "down": Vector2(0, 1), "left": Vector2(-1, 0), "right": Vector2(1, 0)}
const HINT_Y_PLAY := 702.0
const HINT_Y_WATCH := 748.0
const VIEW_MENU := ["View: text only", "View: AI's view", "View: whole room"]   # same order as VIEW_TXT
const UI_TEXT := Color("#d6dbe3")
const UI_MUTED := Color("#8b95a5")
const UI_KEY_BG := Color("#242830")
const UI_KEY_BORDER := Color("#4A5260")

var episodes: Array = []
var ep_idx := 0
var mode := "play"
var web := OS.has_feature("web")
const STUCK_SEED := 10014
const STUCK_STEP := 6
var view_mode := 1   # 0 text only, 1 view only, 2 whole room

# play state
var p_pos := Vector2i.ZERO
var p_dir := 0
var p_steps := 0
var p_result := ""
var p_trail: Array = []

# watch state
var w_i := 0
var w_playing := false
var w_timer := 0.0
var w_delay := 0.6
var demo := false
var demo_wait := 0.0
var btn_demo: Button

var board: Control
var bars: Control
var mission_label: Label
var info: RichTextLabel
var text_box: RichTextLabel
var text_title: Label
var seed_label: Label
var seed_sub: Label
var fail_tag: Control
var btn_play: Button
var btn_watch: Button
var btn_view: OptionButton
var btn_run: Button
var watch_bar: HBoxContainer
var key_hints: VBoxContainer
var hint_ctx := ""
var key_font: FontVariation
var start_screen: Control
# fix (correction loop) state
const SERVER := "http://127.0.0.1:18799"
const MEMO_TXT := {"1": "the answer is in the input but the model got it wrong", "2": "the input lacks the information", "3": "the text is confusing", "4": "other"}
var http: HTTPRequest
var fix_seeds: Array = []
var fix_idx := 0
var fix_state: Dictionary = {}
var fix_room: Dictionary = {}
var fix_trail: Array = []
var fix_busy := false
var fix_cb: Callable
var fix_status := ""
var fix_bot_shown := false
var fix_memo := ""
var fix_auto := false
var fix_timer := 0.0
var fix_retry := -1.0
var fix_wait := 0.0
var server_pid := 0
var quitting := false
var btn_fix: Button
var fix_bar: VBoxContainer
var shot_path := ""
var shot_frames := 0
var fix_script := ""   # self-check keys for fix mode: e model, a/d/w, b bot, 1-4 memo


func _ready() -> void:
	_load_episodes()
	_build_ui()
	get_tree().auto_accept_quit = false
	http = HTTPRequest.new()
	http.timeout = 60.0
	http.request_completed.connect(_on_http)
	add_child(http)
	var args := _user_args()
	if args.has("seed"):
		for i in episodes.size():
			if int(episodes[i]["seed"]) == int(args["seed"]):
				ep_idx = i
	_set_mode(args.get("mode", "play"))
	if mode == "watch" and args.has("step"):
		w_i = clampi(int(args["step"]), 0, _ep()["steps"].size())
	if args.has("view"):
		view_mode = int(args["view"])
	if args.has("moves"):
		for ch in String(args["moves"]):
			_play_act({"a": "turn left", "d": "turn right", "w": "forward"}.get(ch, ""))
	shot_path = args.get("shot", "")
	fix_script = args.get("fixmoves", "")
	if args.has("demo"):
		_set_demo(true)
	if args.has("selftest"):
		_selftest()
		get_tree().quit()
		return
	# the start screen only on a plain launch; scripted runs (seed/mode/shot/demo...) go straight in
	start_screen.visible = args.is_empty()
	_refresh()


## Replays every exported model walk through this file's rules: positions, results and the
## input text must match what the Python env produced.
func _selftest() -> void:
	var bad_text := 0
	var bad_pos := 0
	var bad_res := 0
	var n := 0
	for i in episodes.size():
		ep_idx = i
		mode = "play"
		_restart()
		var steps: Array = _ep()["steps"]
		for st in steps:
			n += 1
			if p_pos != Vector2i(int(st["x"]), int(st["y"])) or p_dir != int(st["dir"]):
				bad_pos += 1
			var want := String(st["input"])
			var got := "mission: %s\n%s" % [_ep()["mission"], _obs_text(p_pos, p_dir)]
			if got != want:
				bad_text += 1
				if bad_text <= 3:
					print("TEXT seed ", _ep()["seed"], "\n--want\n", want, "\n--got\n", got)
			_play_act(st["choice"])
		var want_res: String = _ep()["result"]
		if p_result != want_res:
			bad_res += 1
			print("RESULT seed ", _ep()["seed"], " want ", want_res, " got ", p_result)
	print("selftest: episodes %d steps %d  text mismatches %d  position mismatches %d  result mismatches %d"
		% [episodes.size(), n, bad_text, bad_pos, bad_res])


func _user_args() -> Dictionary:
	var d := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		d[kv[0]] = kv[1] if kv.size() > 1 else "1"
	return d


func _load_episodes() -> void:
	var txt := FileAccess.get_file_as_string("res://data/episodes.json")
	var parsed = JSON.parse_string(txt)
	if parsed is Dictionary:
		episodes = parsed["episodes"]


# ---------------------------------------------------------------- UI building

func _btn(parent: Node, text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.focus_mode = Control.FOCUS_NONE
	b.pressed.connect(cb)
	parent.add_child(b)
	return b


func _build_ui() -> void:
	var mono := SystemFont.new()
	mono.font_names = PackedStringArray(["D2Coding", "Consolas", "Malgun Gothic"])

	_build_top_bar()

	var help := Label.new()
	help.position = Vector2(16, 58)
	help.size = Vector2(1290, 50)
	help.add_theme_color_override("font_color", Color("#b8c0cc"))
	help.text = ("Rule: succeed by standing right in front of the object named in the mission, facing it, within 64 steps. Each step is one of 'turn left / turn right / forward'.\n"
		+ "The AI (Laya) never sees the picture, only the 7×7 cells ahead (bright cells) as English text. It picks one of three moves each step and has no memory.")
	add_child(help)

	board = Control.new()
	board.position = Vector2(16, 110)
	board.size = Vector2(CELL * 8, CELL * 8)
	board.draw.connect(_draw_board)
	add_child(board)

	key_font = FontVariation.new()
	key_font.base_font = ThemeDB.fallback_font
	key_font.variation_embolden = 0.7
	key_hints = VBoxContainer.new()
	key_hints.position = Vector2(16, HINT_Y_PLAY)
	key_hints.add_theme_constant_override("separation", 10)
	add_child(key_hints)

	watch_bar = HBoxContainer.new()
	watch_bar.position = Vector2(16, 700)
	watch_bar.add_theme_constant_override("separation", 6)
	add_child(watch_bar)
	_btn(watch_bar, "Start", func(): _watch_seek(0))
	_btn(watch_bar, "< Step", func(): _watch_seek(w_i - 1))
	btn_run = _btn(watch_bar, "Play", func(): _toggle_run())
	_btn(watch_bar, "Step >", func(): _watch_seek(w_i + 1))
	_btn(watch_bar, "Slower", func(): w_delay = minf(w_delay * 1.5, 3.0); _refresh())
	_btn(watch_bar, "Faster", func(): w_delay = maxf(w_delay / 1.5, 0.08); _refresh())
	btn_demo = _btn(watch_bar, "Auto-watch", func(): _set_demo(not demo))
	btn_demo.toggle_mode = true
	for b in watch_bar.get_children():
		_style_btn(b, UI_KEY_BG, UI_KEY_BORDER, UI_TEXT)
		for st in ["normal", "hover", "pressed", "hover_pressed", "disabled"]:
			var s: StyleBoxFlat = b.get_theme_stylebox(st)
			s.content_margin_left = 8
			s.content_margin_right = 8
	_style_toggle_on(btn_demo)

	fix_bar = VBoxContainer.new()
	fix_bar.position = Vector2(16, 696)
	fix_bar.add_theme_constant_override("separation", 6)
	add_child(fix_bar)
	var r1 := HBoxContainer.new()
	r1.add_theme_constant_override("separation", 6)
	fix_bar.add_child(r1)
	_btn(r1, "AI's choice (Enter)", func(): _fix_step(""))
	_btn(r1, "Turn left (A)", func(): _fix_step("turn left"))
	_btn(r1, "Turn right (D)", func(): _fix_step("turn right"))
	_btn(r1, "Forward (W)", func(): _fix_step("forward"))
	_btn(r1, "Show bot (B)", func(): fix_bot_shown = not fix_bot_shown; _refresh())
	var r2 := HBoxContainer.new()
	r2.add_theme_constant_override("separation", 6)
	fix_bar.add_child(r2)
	for code in ["1", "2", "3", "4"]:
		_btn(r2, "Memo %s" % code, func(): _fix_set_memo(code))
	_btn(r2, "AI to the end (R)", func(): _fix_set_auto(true))
	_btn(r2, "Next room (N)", func(): _change_ep(1))
	var r3 := Label.new()
	r3.add_theme_color_override("font_color", Color("#8b95a5"))
	r3.text = ("If the AI is right, press Enter. Otherwise an arrow key (screen-based: one cell if already facing that way, else turn toward it) = correction\n"
		+ "Memo (keys 1-4): 1 answer in input but wrong · 2 info missing · 3 confusing text · 4 other")
	fix_bar.add_child(r3)

	var rx := 620.0
	mission_label = Label.new()
	mission_label.position = Vector2(rx, 108)
	mission_label.size = Vector2(680, 40)
	mission_label.add_theme_font_size_override("font_size", 28)
	add_child(mission_label)

	info = RichTextLabel.new()
	info.bbcode_enabled = true
	info.position = Vector2(rx, 152)
	info.size = Vector2(680, 150)
	info.scroll_active = false
	info.add_theme_font_size_override("normal_font_size", 18)
	info.add_theme_font_size_override("bold_font_size", 18)
	add_child(info)

	bars = Control.new()
	bars.position = Vector2(rx, 306)
	bars.size = Vector2(680, 170)
	bars.draw.connect(_draw_bars)
	add_child(bars)

	text_title = Label.new()
	text_title.position = Vector2(rx, 486)
	text_title.add_theme_color_override("font_color", Color("#b8c0cc"))
	add_child(text_title)

	text_box = RichTextLabel.new()
	text_box.bbcode_enabled = true
	text_box.position = Vector2(rx, 514)
	text_box.size = Vector2(680, 330)
	text_box.add_theme_font_override("normal_font", mono)
	text_box.add_theme_font_size_override("normal_font_size", 22)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color("#161a21")
	sb.border_color = Color("#2d3440")
	sb.set_border_width_all(1)
	sb.set_content_margin_all(14)
	text_box.add_theme_stylebox_override("normal", sb)
	add_child(text_box)

	_build_start_screen()


## Top bar: mode switch | room navigator + failure tag | spacer | actions.
func _build_top_bar() -> void:
	var top := HBoxContainer.new()
	top.position = Vector2(16, 8)
	top.custom_minimum_size = Vector2(1288, 44)
	top.add_theme_constant_override("separation", 12)
	add_child(top)

	# mode switch: one segment lit at a time (ButtonGroup), instead of greyed-out "disabled" buttons
	var seg := PanelContainer.new()
	var seg_sb := _box(Color("#0d0f13"), Color("#2d3440"), 8)
	seg_sb.set_content_margin_all(3)
	seg.add_theme_stylebox_override("panel", seg_sb)
	top.add_child(seg)
	var seg_row := HBoxContainer.new()
	seg_row.add_theme_constant_override("separation", 2)
	seg.add_child(seg_row)
	var group := ButtonGroup.new()
	btn_play = _mode_btn(seg_row, group, "Play yourself", "play")
	btn_watch = _mode_btn(seg_row, group, "Watch Laya", "watch")
	btn_fix = _mode_btn(seg_row, group, "Correct", "fix")
	btn_fix.visible = not web

	# room navigator: < Room n of N / seed > in one box
	var nav := PanelContainer.new()
	var nav_sb := _box(Color("#1b1f26"), Color("#2d3440"), 8)
	nav_sb.set_content_margin_all(4)
	nav.add_theme_stylebox_override("panel", nav_sb)
	top.add_child(nav)
	var nav_row := HBoxContainer.new()
	nav_row.add_theme_constant_override("separation", 8)
	nav.add_child(nav_row)
	_chevron_btn(nav_row, -1, func(): _change_ep(-1))
	var labels := VBoxContainer.new()
	labels.add_theme_constant_override("separation", -2)
	labels.custom_minimum_size = Vector2(150, 0)
	nav_row.add_child(labels)
	seed_label = Label.new()
	seed_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	seed_label.add_theme_color_override("font_color", Color.WHITE)
	labels.add_child(seed_label)
	seed_sub = Label.new()
	seed_sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	seed_sub.add_theme_color_override("font_color", UI_MUTED)
	seed_sub.add_theme_font_size_override("font_size", 12)
	labels.add_child(seed_sub)
	_chevron_btn(nav_row, 1, func(): _change_ep(1))

	fail_tag = PanelContainer.new()
	var tag_sb := _box(Color("#3a1d1f"), Color("#3a1d1f"), 6)
	tag_sb.content_margin_left = 8
	tag_sb.content_margin_right = 8
	fail_tag.add_theme_stylebox_override("panel", tag_sb)
	var tag := Label.new()
	tag.text = "All 3 AIs failed"
	tag.add_theme_color_override("font_color", Color("#f09595"))
	tag.add_theme_font_size_override("font_size", 14)
	fail_tag.add_child(tag)
	top.add_child(fail_tag)

	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(spacer)

	_style_btn(_btn(top, "Next failure", func(): _next_hard()), UI_KEY_BG, UI_KEY_BORDER, UI_TEXT)
	_style_btn(_btn(top, "Stuck example", func(): _stuck_example()), Color("#2a1a14"), Color("#b5532a"), Color("#f0997b"))
	btn_view = OptionButton.new()
	btn_view.focus_mode = Control.FOCUS_NONE
	for t in VIEW_MENU:
		btn_view.add_item(t)
	btn_view.item_selected.connect(func(i: int): view_mode = i; _refresh())
	_style_btn(btn_view, UI_KEY_BG, UI_KEY_BORDER, UI_TEXT)
	top.add_child(btn_view)
	_style_btn(_btn(top, "Restart", func(): _restart()), UI_KEY_BG, UI_KEY_BORDER, UI_TEXT)
	if web:
		# engine license and third-party notices, shipped next to index.html in the web package
		var lic := LinkButton.new()
		lic.text = "Licenses"
		lic.focus_mode = Control.FOCUS_NONE
		lic.underline = LinkButton.UNDERLINE_MODE_ALWAYS
		lic.add_theme_color_override("font_color", UI_MUTED)
		lic.add_theme_color_override("font_hover_color", UI_TEXT)
		lic.pressed.connect(func(): OS.shell_open("licenses.txt"))
		top.add_child(lic)
	for c in top.get_children():
		(c as Control).size_flags_vertical = Control.SIZE_SHRINK_CENTER


func _box(bg: Color, border: Color, radius := 6, bw := 1) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.border_color = border
	sb.set_border_width_all(bw)
	sb.set_corner_radius_all(radius)
	sb.content_margin_left = 10
	sb.content_margin_right = 10
	sb.content_margin_top = 5
	sb.content_margin_bottom = 5
	return sb


## Bordered button with hover/pressed states, so it reads as clickable (the default theme looks like plain text here).
func _style_btn(b: Button, bg: Color, border: Color, fg: Color) -> void:
	b.add_theme_stylebox_override("normal", _box(bg, border))
	b.add_theme_stylebox_override("hover", _box(bg.lightened(0.08), border.lightened(0.25)))
	b.add_theme_stylebox_override("pressed", _box(bg.darkened(0.25), border))
	b.add_theme_stylebox_override("hover_pressed", _box(bg.darkened(0.25), border))
	b.add_theme_stylebox_override("disabled", _box(bg, border))
	b.add_theme_color_override("font_color", fg)
	b.add_theme_color_override("font_hover_color", fg.lightened(0.3))
	b.add_theme_color_override("font_pressed_color", fg)
	b.add_theme_color_override("font_hover_pressed_color", fg)


## A toggle that is on shows the same green as the lit mode segment.
func _style_toggle_on(b: Button) -> void:
	var on := Color("#2f7d4f")
	for st in ["pressed", "hover_pressed"]:
		var s := _box(on, on.lightened(0.2))
		s.content_margin_left = 8
		s.content_margin_right = 8
		b.add_theme_stylebox_override(st, s)
	b.add_theme_color_override("font_pressed_color", Color.WHITE)
	b.add_theme_color_override("font_hover_pressed_color", Color.WHITE)


func _mode_btn(parent: Node, group: ButtonGroup, label: String, m: String) -> Button:
	var b := _btn(parent, label, func():
		if mode != m:
			_set_mode(m))
	b.toggle_mode = true
	b.button_group = group
	var on := Color("#2f7d4f")
	b.add_theme_stylebox_override("normal", _box(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 6, 0))
	b.add_theme_stylebox_override("hover", _box(Color("#1b1f26"), Color(0, 0, 0, 0), 6, 0))
	b.add_theme_stylebox_override("pressed", _box(on, on, 6, 0))
	b.add_theme_stylebox_override("hover_pressed", _box(on.lightened(0.08), on, 6, 0))
	b.add_theme_color_override("font_color", Color("#9aa3b0"))
	b.add_theme_color_override("font_hover_color", UI_TEXT)
	b.add_theme_color_override("font_pressed_color", Color.WHITE)
	b.add_theme_color_override("font_hover_pressed_color", Color.WHITE)
	return b


## Square keycap-style button with a drawn chevron (the web default font has no arrow glyphs).
func _chevron_btn(parent: Node, dir: int, cb: Callable) -> Button:
	var b := _btn(parent, "", cb)
	b.custom_minimum_size = Vector2(30, 30)
	b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_style_btn(b, UI_KEY_BG, UI_KEY_BORDER, UI_TEXT)
	b.draw.connect(func():
		var m := b.size / 2.0
		var dx := 4.0 * dir
		b.draw_polyline(PackedVector2Array([m + Vector2(-dx, -6), m + Vector2(dx, 0), m + Vector2(-dx, 6)]), Color.WHITE, 2.0, true))
	return b


func _sync_top_bar() -> void:
	btn_play.set_pressed_no_signal(mode == "play")
	btn_watch.set_pressed_no_signal(mode == "watch")
	btn_fix.set_pressed_no_signal(mode == "fix")
	btn_view.select(view_mode)
	btn_view.set_item_disabled(0, mode != "play")   # watch/correct show the room, never text only


func _build_start_screen() -> void:
	start_screen = ColorRect.new()
	(start_screen as ColorRect).color = Color(0.06, 0.07, 0.09, 0.96)
	start_screen.position = Vector2.ZERO
	start_screen.size = Vector2(1320, 860)
	start_screen.mouse_filter = Control.MOUSE_FILTER_STOP
	start_screen.visible = false
	add_child(start_screen)

	var col := VBoxContainer.new()
	col.position = Vector2(160, 170)
	col.size = Vector2(1000, 520)
	col.alignment = BoxContainer.ALIGNMENT_CENTER
	col.add_theme_constant_override("separation", 22)
	start_screen.add_child(col)

	var title := Label.new()
	title.text = "BabyAI Laya: an AI in the room"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 40)
	col.add_child(title)

	var sub := Label.new()
	sub.text = "Reach the object named in the mission with three moves: turn left, turn right, forward."
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sub.add_theme_color_override("font_color", Color("#b8c0cc"))
	sub.add_theme_font_size_override("font_size", 20)
	col.add_child(sub)

	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 40)
	col.add_child(row)
	_start_choice(row, "Try it yourself", "Walk the room with the keyboard.", Color("#2f7d4f"),
		func(): _leave_start(); _set_mode("play"))
	_start_choice(row, "See Laya get stuck", "Replay a recorded failure: it keeps\nwalking forward into a wall.", Color("#b5532a"),
		func(): _leave_start(); _stuck_example())

	var note := Label.new()
	note.text = "Laya's walks are recorded playback, not live inference. You can switch at any time with the buttons at the top."
	note.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	note.add_theme_color_override("font_color", Color("#8b95a5"))
	note.add_theme_font_size_override("font_size", 16)
	col.add_child(note)


func _start_choice(parent: Node, label: String, desc: String, bg: Color, cb: Callable) -> void:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	parent.add_child(box)
	var b := _btn(box, label, cb)
	b.custom_minimum_size = Vector2(400, 120)
	b.add_theme_font_size_override("font_size", 30)
	for state in ["normal", "hover", "pressed"]:
		var st := StyleBoxFlat.new()
		st.bg_color = bg.lightened(0.15) if state == "hover" else (bg.darkened(0.15) if state == "pressed" else bg)
		st.set_corner_radius_all(10)
		b.add_theme_stylebox_override(state, st)
	var d := Label.new()
	d.text = desc
	d.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	d.add_theme_color_override("font_color", Color("#b8c0cc"))
	d.add_theme_font_size_override("font_size", 18)
	box.add_child(d)


func _leave_start() -> void:
	start_screen.visible = false


# ---------------------------------------------------------------- state

func _ep() -> Dictionary:
	if mode == "fix":
		return fix_room
	return episodes[ep_idx]


func _set_mode(m: String) -> void:
	if m == "fix" and web:
		return   # the browser build has no inference server (no WSL / Python / localhost)
	if m != "watch":
		demo = false
	mode = m
	view_mode = 1 if mode == "play" else 2
	fix_auto = false
	if mode == "fix":
		_refresh()
		if fix_seeds.is_empty():
			_fix_connect()
		else:
			_fix_reset()
		return
	_restart()


func _restart() -> void:
	if mode == "fix":
		_fix_reset()
		return
	var s: Dictionary = _ep()["start"]
	p_pos = Vector2i(int(s["x"]), int(s["y"]))
	p_dir = int(s["dir"])
	p_steps = 0
	p_result = ""
	p_trail = [p_pos]
	w_i = 0
	w_playing = false
	_refresh()


func _change_ep(d: int) -> void:
	if mode == "fix":
		if not fix_seeds.is_empty():
			fix_idx = posmod(fix_idx + d, fix_seeds.size())
			_fix_reset()
		return
	ep_idx = posmod(ep_idx + d, episodes.size())
	_restart()


## Seed 10014, step 6: the recorded AI keeps pushing forward into a wall (stage 3/4 reports).
func _stuck_example() -> void:
	for i in episodes.size():
		if int(episodes[i]["seed"]) == STUCK_SEED:
			ep_idx = i
			_set_mode("watch")
			_watch_seek(STUCK_STEP)
			return


func _next_hard() -> void:
	if mode == "fix":
		_change_ep(1)
		return
	for k in range(1, episodes.size() + 1):
		var i := posmod(ep_idx + k, episodes.size())
		if episodes[i]["result"] != "success":
			ep_idx = i
			break
	_restart()


func _cycle_view() -> void:
	if mode == "play":
		view_mode = (view_mode + 2) % 3   # view only -> text only -> whole room -> view only
	else:
		view_mode = 1 if view_mode == 2 else 2
	_refresh()


## Continuous watching: play the episode, pause 2 s at the end, then the next one.
func _set_demo(on: bool) -> void:
	demo = on
	if demo:
		if mode != "watch":
			_set_mode("watch")
		w_delay = 0.4
		w_playing = true
		demo_wait = 0.0
	_refresh()


func _toggle_run() -> void:
	if w_i >= _ep()["steps"].size():
		w_i = 0
	w_playing = not w_playing
	w_timer = 0.0
	_refresh()


func _watch_seek(i: int) -> void:
	w_i = clampi(i, 0, _ep()["steps"].size())
	_refresh()


func _agent() -> Array:
	if mode == "play":
		return [p_pos, p_dir]
	if mode == "fix":
		return [Vector2i(int(fix_state.get("x", 0)), int(fix_state.get("y", 0))), int(fix_state.get("dir", 0))]
	var steps: Array = _ep()["steps"]
	var s: Dictionary = steps[w_i] if w_i < steps.size() else _ep()["end"]
	return [Vector2i(int(s["x"]), int(s["y"])), int(s["dir"])]


func _is_wall(c: Vector2i) -> bool:
	var e := _ep()
	return c.x <= 0 or c.y <= 0 or c.x >= int(e["width"]) - 1 or c.y >= int(e["height"]) - 1


func _obj_at(c: Vector2i) -> Variant:
	for o in _ep()["objects"]:
		if int(o["x"]) == c.x and int(o["y"]) == c.y:
			return o
	return null


func _is_target(c: Vector2i) -> bool:
	for p in _ep()["target"]["positions"]:
		if int(p[0]) == c.x and int(p[1]) == c.y:
			return true
	return false


func _view_cells(pos: Vector2i, dir: int) -> Dictionary:
	var out := {}
	var e := _ep()
	for f in 7:
		for l in range(-3, 4):
			var c: Vector2i = pos + DIR_VEC[dir] * f + DIR_VEC[(dir + 1) % 4] * l
			if c.x >= 0 and c.y >= 0 and c.x < int(e["width"]) and c.y < int(e["height"]):
				out[c] = true
	return out


func _play_act(a: String) -> void:
	if a == "" or mode != "play" or p_result != "":
		return
	if a == "turn left":
		p_dir = (p_dir + 3) % 4
	elif a == "turn right":
		p_dir = (p_dir + 1) % 4
	else:
		var f: Vector2i = p_pos + DIR_VEC[p_dir]
		if not _is_wall(f) and _obj_at(f) == null:
			p_pos = f
	p_steps += 1
	p_trail.append(p_pos)
	if _is_target(p_pos + DIR_VEC[p_dir]):
		p_result = "success"
	elif p_steps >= int(_ep()["max_steps"]):
		p_result = "timeout"
	_refresh()


## Same rules as probe/obs_text.py (what the model reads), computed from the room.
func _obs_text(pos: Vector2i, dir: int) -> String:
	var lines := ["facing: " + DIR_NAME[dir]]
	var fwd: Vector2i = DIR_VEC[dir]
	var right: Vector2i = DIR_VEC[(dir + 1) % 4]
	var objs := []
	for f in 7:
		for l in range(-3, 4):
			if f == 0 and l == 0:
				continue
			var o: Variant = _obj_at(pos + fwd * f + right * l)
			if o != null:
				objs.append([f + absi(l), f, l, "%s %s" % [o["color"], o["type"]]])
	objs.sort_custom(func(a, b):
		for k in 4:
			if a[k] != b[k]:
				return a[k] < b[k]
		return false)
	for o in objs:
		var parts := []
		if o[1] != 0:
			parts.append("%d ahead" % o[1])
		if o[2] != 0:
			parts.append("%d %s" % [absi(o[2]), "left" if o[2] < 0 else "right"])
		lines.append("%s: %s" % [o[3], ", ".join(parts)])
	if objs.is_empty():
		lines.append("objects: none in view")
	var walls := []
	for spec in [["ahead", fwd, 6], ["left", -right, 3], ["right", right, 3]]:
		for k in range(1, spec[2] + 1):
			if _is_wall(pos + spec[1] * k):
				walls.append("%d %s" % [k, spec[0]])
				break
	lines.append("walls: " + (", ".join(walls) if not walls.is_empty() else "none in line"))
	return "\n".join(lines)


# ---------------------------------------------------------------- input / loop

func _input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed):
		return
	var k: int = event.keycode
	if start_screen.visible:
		get_viewport().set_input_as_handled()
		return
	if mode == "fix" and _fix_key(k, event.echo):
		get_viewport().set_input_as_handled()
		return
	if k == KEY_TAB:
		_set_mode({"play": "watch", "watch": "play" if web else "fix", "fix": "play"}[mode])
	elif k == KEY_PAGEUP or k == KEY_BRACKETLEFT:
		_change_ep(-1)
	elif k == KEY_PAGEDOWN or k == KEY_BRACKETRIGHT:
		_change_ep(1)
	elif k == KEY_V:
		_cycle_view()
	elif k == KEY_R:
		_restart()
	elif mode == "play" and not event.echo:
		match k:
			KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN: _play_act(_screen_key_action(p_dir, k))
			KEY_A: _play_act("turn left")
			KEY_D: _play_act("turn right")
			KEY_W: _play_act("forward")
			KEY_ENTER, KEY_KP_ENTER:
				if p_result != "":
					_set_mode("watch")
	elif mode == "watch":
		match k:
			KEY_SPACE: _toggle_run()
			KEY_LEFT: _watch_seek(w_i - 1)
			KEY_RIGHT: _watch_seek(w_i + 1)
			KEY_HOME: _watch_seek(0)
			KEY_END: _watch_seek(_ep()["steps"].size())
	get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	if mode == "watch" and w_playing:
		w_timer += delta
		if w_timer >= w_delay:
			w_timer = 0.0
			if w_i < _ep()["steps"].size():
				w_i += 1
			elif not demo:
				w_playing = false
			_refresh()
		if demo and w_i >= _ep()["steps"].size():
			demo_wait += delta
			if demo_wait >= 2.5:
				demo_wait = 0.0
				_change_ep(1)
				w_playing = true
	if mode == "fix":
		_fix_process(delta)
	if mode == "fix" and fix_script != "" and not fix_busy and not fix_room.is_empty():
		var ch := fix_script.substr(0, 1)
		fix_script = fix_script.substr(1)
		match ch:
			"e": _fix_step("")
			"a": _fix_step("turn left")
			"d": _fix_step("turn right")
			"w": _fix_step("forward")
			"b": fix_bot_shown = true; _refresh()
			"1", "2", "3", "4": _fix_set_memo(ch)
	if shot_path != "":
		if mode != "fix" or (fix_script == "" and not fix_busy and not fix_room.is_empty()):
			shot_frames += 1
		if shot_frames == 5:
			get_viewport().get_texture().get_image().save_png(shot_path)
			get_tree().quit()


# ---------------------------------------------------------------- refresh text

func _refresh() -> void:
	fix_bar.visible = mode == "fix"
	if mode == "fix":
		_refresh_fix()
		return
	if episodes.is_empty():
		mission_label.text = "godot/data/episodes.json is missing: run the export command from the README first"
		return
	var e := _ep()
	_sync_top_bar()
	seed_label.text = "Room %d of %d" % [ep_idx + 1, episodes.size()]
	seed_sub.text = "seed %d" % int(e["seed"])
	fail_tag.visible = bool(e["all_models_failed"])
	mission_label.text = "Mission: %s" % e["mission"]
	var ag := _agent()
	var bot_txt: String = ("%d steps" % int(e["bot_steps"])) if e["bot_steps"] != null else "failed"
	var ai_txt: String = ("[color=#46a758]success, %d steps[/color]" % e["steps"].size()) if e["result"] == "success" \
		else "[color=#e5484d]failed: used all 64 steps[/color]"
	watch_bar.visible = mode == "watch"
	_refresh_hints()
	btn_run.text = "Pause" if w_playing else "Play"
	btn_demo.set_pressed_no_signal(demo)

	if mode == "play":
		var s := "[b]Step %d / %d[/b]   facing: %s\n" % [p_steps, int(e["max_steps"]), DIR_NAME[ag[1]]]
		if p_result == "success":
			s += "[color=#46a758][b]Success![/b][/color] you %d steps · AI %s · expert bot %s\n" % [p_steps, ai_txt, bot_txt]
			s += "Press Enter to see how the AI walked this room."
		elif p_result == "timeout":
			s += "[color=#e5484d][b]Failed: all 64 steps used.[/b][/color] AI %s · bot %s\nEnter: see how the AI did" % [ai_txt, bot_txt]
		else:
			s += "View: [b]%s[/b]  (V to change)\n" % VIEW_TXT[view_mode]
			if view_mode == 0:
				s += "No picture. Move using only the text at the bottom right: it is all the AI gets each step."
			elif view_mode == 1:
				s += "Dark cells are outside the AI's view too. But you remember the path you took; the AI does not."
		info.text = s
		text_title.text = "What the AI would get now (mission + the 7×7 view as text):"
		text_box.text = "mission: %s\n%s" % [e["mission"], _obs_text(ag[0], ag[1])]
	else:
		var steps: Array = e["steps"]
		var s2 := "[color=#f5c518][b]Recorded Laya playback—not live inference.[/b][/color]\n"
		s2 += "[b]Step %d / %d[/b]   AI result in this room: %s · expert bot %s\n" % [w_i, steps.size(), ai_txt, bot_txt]
		if w_i < steps.size():
			var st: Dictionary = steps[w_i]
			var same: bool = st["bot"] == st["choice"]
			s2 += "AI choice: [b]%s[/b] (%d%%)\n" % [ACT_TXT.get(st["choice"], st["choice"]), roundi(float(st["probs"][st["choice"]]) * 100)]
			s2 += ("Expert bot also: [color=#46a758]%s[/color]" if same else "[color=#f5a524]Expert bot (one valid route): %s[/color]  <- they differ here") % ACT_TXT.get(st["bot"], st["bot"])
			text_box.text = st["input"]
		else:
			s2 += "[b]End.[/b] " + ("Reached the target." if e["result"] == "success" else "Did not get there in 64 steps. Yellow numbers count visits to the same cell: signs of going in circles.")
			text_box.text = ""
		s2 += "\nSpeed %.1f s/step" % w_delay
		info.text = s2
		text_title.text = "Text the AI got at this step (it chose from this alone):"
	board.queue_redraw()
	bars.queue_redraw()


# ---------------------------------------------------------------- keyboard hints

## Rebuilds the keycap rows only when the context changes (mode, or a finished play room).
func _refresh_hints() -> void:
	key_hints.visible = mode == "play" or mode == "watch"
	key_hints.position = Vector2(16, HINT_Y_WATCH if mode == "watch" else HINT_Y_PLAY)
	var ctx := mode + ":" + (p_result if mode == "play" else "")
	if ctx == hint_ctx:
		return
	hint_ctx = ctx
	for c in key_hints.get_children():
		key_hints.remove_child(c)
		c.queue_free()
	if not key_hints.visible:
		return
	var r1 := _hint_row()
	var r2 := _hint_row()
	if mode == "play":
		_hint(r1, ["up", "down", "left", "right"], "Move / Turn (screen)")
		_hint_sep(r1)
		_hint(r1, ["W"], "Forward")
		_hint(r1, ["A"], "Left")
		_hint(r1, ["D"], "Right")
		_hint(r2, ["V"], "View mode")
		_hint_sep(r2)
		_hint(r2, ["R"], "Restart")
		_hint_sep(r2)
		_hint(r2, ["Tab"], "Watch Laya")
		if p_result != "":
			_hint(_hint_row(), ["Enter"], "Watch Laya's replay", COLORS["green"] if p_result == "success" else Color(0, 0, 0, 0))
	else:
		_hint(r1, ["Space"], "Play / Pause")
		_hint_sep(r1)
		_hint(r1, ["left", "right"], "Step back / forward")
		_hint(r2, ["V"], "View mode")
		_hint_sep(r2)
		_hint(r2, ["Tab"], "Play yourself")


func _hint_row() -> HBoxContainer:
	var r := HBoxContainer.new()
	r.add_theme_constant_override("separation", 12)
	key_hints.add_child(r)
	return r


func _hint_sep(row: HBoxContainer) -> void:
	var s := VSeparator.new()
	s.custom_minimum_size = Vector2(0, 26)
	row.add_child(s)


## Keycaps followed by a short label; a visible `accent` turns the whole hint into a highlighted badge.
func _hint(row: HBoxContainer, keys: Array, label: String, accent := Color(0, 0, 0, 0)) -> void:
	var on := accent.a > 0.0
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 4)
	row.add_child(h)
	for k in keys:
		h.add_child(_keycap(k, accent))
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(4, 0)
	h.add_child(gap)
	var l := Label.new()
	l.text = label
	l.add_theme_font_size_override("font_size", 17)
	l.add_theme_color_override("font_color", accent if on else Color("#B0B8C4"))
	if on:
		l.add_theme_font_override("font", key_font)
	h.add_child(l)


func _keycap(key: String, accent: Color) -> PanelContainer:
	var on := accent.a > 0.0
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color("#1d3326") if on else Color("#242830")
	sb.border_color = accent if on else Color("#4A5260")
	sb.set_border_width_all(2 if on else 1)
	sb.set_corner_radius_all(5)
	sb.content_margin_left = 6
	sb.content_margin_right = 6
	sb.content_margin_top = 2
	sb.content_margin_bottom = 2
	p.add_theme_stylebox_override("panel", sb)
	if ARROW_KEYS.has(key):
		var c := Control.new()
		c.custom_minimum_size = Vector2(10, 24)
		var d: Vector2 = ARROW_KEYS[key]
		c.draw.connect(func():
			var m := c.size / 2.0
			var n := Vector2(-d.y, d.x)
			c.draw_colored_polygon(PackedVector2Array([m + d * 6.0, m - d * 4.0 + n * 5.0, m - d * 4.0 - n * 5.0]), Color.WHITE))
		p.add_child(c)
	else:
		var l := Label.new()
		l.text = key
		l.add_theme_font_override("font", key_font)
		l.add_theme_font_size_override("font_size", 16)
		l.add_theme_color_override("font_color", accent if on else Color("#FFFFFF"))
		p.add_child(l)
	return p


# ---------------------------------------------------------------- drawing

func _draw_board() -> void:
	if mode == "fix" and fix_room.is_empty():
		board.draw_rect(Rect2(0, 0, CELL * 8, CELL * 8), Color("#11141a"))
		board.draw_string(board.get_theme_default_font(), Vector2(30, CELL * 4), fix_status,
			HORIZONTAL_ALIGNMENT_LEFT, CELL * 8 - 60, 22, Color("#8b95a5"))
		return
	if mode != "fix" and episodes.is_empty():
		return
	var e := _ep()
	var w := int(e["width"])
	var h := int(e["height"])
	var ag := _agent()
	var view := _view_cells(ag[0], ag[1])
	var font := board.get_theme_default_font()

	if mode == "play" and view_mode == 0:
		board.draw_rect(Rect2(0, 0, w * CELL, h * CELL), Color("#11141a"))
		board.draw_string(font, Vector2(40, h * CELL / 2.0 - 10), "No picture: move using only the text on the right",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 24, Color("#8b95a5"))
		board.draw_string(font, Vector2(40, h * CELL / 2.0 + 26), "(same as the AI. step %d)" % p_steps,
			HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color("#5d6675"))
		if p_result != "":
			board.draw_string(font, Vector2(40, h * CELL / 2.0 + 70), "Success!" if p_result == "success" else "Failed",
				HORIZONTAL_ALIGNMENT_LEFT, -1, 36, Color("#46a758") if p_result == "success" else Color("#e5484d"))
		return

	for y in h:
		for x in w:
			var c := Vector2i(x, y)
			var r := Rect2(x * CELL, y * CELL, CELL, CELL)
			if view_mode == 1 and not view.has(c):
				board.draw_rect(r, Color("#0d0f13"))
				continue
			board.draw_rect(r, Color("#545b68") if _is_wall(c) else Color("#262b34"))
			board.draw_rect(r, Color("#1b1f26"), false, 1.0)

	# trail + revisit counts
	var trail: Array = []
	if mode == "play":
		trail = p_trail
	elif mode == "fix":
		trail = fix_trail
	else:
		for i in mini(w_i + 1, e["steps"].size()):
			trail.append(Vector2i(int(e["steps"][i]["x"]), int(e["steps"][i]["y"])))
		if w_i >= e["steps"].size():
			trail.append(ag[0])
	var visits := {}
	for i in trail.size():
		visits[trail[i]] = visits.get(trail[i], 0) + 1
		if i > 0 and trail[i] != trail[i - 1]:
			board.draw_line(_center(trail[i - 1]), _center(trail[i]), Color(1, 0.55, 0.3, 0.35), 4.0)

	for o in e["objects"]:
		var c := Vector2i(int(o["x"]), int(o["y"]))
		if view_mode == 1 and not view.has(c):
			continue
		_draw_object(o, c)

	if mode != "play" or p_result != "":
		for p in e["target"]["positions"]:
			var c := Vector2i(int(p[0]), int(p[1]))
			board.draw_arc(_center(c), CELL * 0.46, 0, TAU, 40, Color("#ffffff"), 3.0)

	# dim outside the 7x7 view (whole-room view)
	if view_mode == 2:
		for y in h:
			for x in w:
				if not view.has(Vector2i(x, y)):
					board.draw_rect(Rect2(x * CELL, y * CELL, CELL, CELL), Color(0, 0, 0, 0.55))
	_draw_view_outline(view)

	for c in visits:
		if visits[c] >= 3:
			board.draw_string(font, Vector2(c.x * CELL + 4, c.y * CELL + 20), "×%d" % visits[c],
				HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color("#f5c518"))

	_draw_agent(ag[0], ag[1])


func _center(c: Vector2i) -> Vector2:
	return Vector2(c.x * CELL + CELL / 2.0, c.y * CELL + CELL / 2.0)


func _draw_view_outline(view: Dictionary) -> void:
	var col := Color(0.55, 0.8, 1.0, 0.8)
	for c in view:
		for d in 4:
			if not view.has(c + DIR_VEC[d]):
				var a := Vector2(c.x * CELL, c.y * CELL)
				match d:
					0: board.draw_line(a + Vector2(CELL, 0), a + Vector2(CELL, CELL), col, 2.0)
					1: board.draw_line(a + Vector2(0, CELL), a + Vector2(CELL, CELL), col, 2.0)
					2: board.draw_line(a, a + Vector2(0, CELL), col, 2.0)
					3: board.draw_line(a, a + Vector2(CELL, 0), col, 2.0)


func _draw_object(o: Dictionary, c: Vector2i) -> void:
	var col: Color = COLORS.get(o["color"], Color.WHITE)
	var m := _center(c)
	match o["type"]:
		"ball":
			board.draw_circle(m, CELL * 0.3, col)
		"box":
			var r := Rect2(m - Vector2(CELL * 0.32, CELL * 0.32), Vector2(CELL * 0.64, CELL * 0.64))
			board.draw_rect(r, col, false, 5.0)
			board.draw_line(r.position + Vector2(0, r.size.y * 0.35), r.position + Vector2(r.size.x, r.size.y * 0.35), col, 3.0)
		"key":
			board.draw_circle(m + Vector2(-CELL * 0.18, 0), CELL * 0.14, col)
			board.draw_circle(m + Vector2(-CELL * 0.18, 0), CELL * 0.06, Color("#262b34"))
			board.draw_rect(Rect2(m + Vector2(-CELL * 0.05, -CELL * 0.04), Vector2(CELL * 0.33, CELL * 0.08)), col)
			board.draw_rect(Rect2(m + Vector2(CELL * 0.16, 0), Vector2(CELL * 0.05, CELL * 0.13)), col)
			board.draw_rect(Rect2(m + Vector2(CELL * 0.24, 0), Vector2(CELL * 0.05, CELL * 0.1)), col)


func _draw_agent(pos: Vector2i, dir: int) -> void:
	var m := _center(pos)
	var f := Vector2(DIR_VEC[dir])
	var p := Vector2(-f.y, f.x)
	var pts := PackedVector2Array([m + f * CELL * 0.36, m - f * CELL * 0.28 + p * CELL * 0.28, m - f * CELL * 0.28 - p * CELL * 0.28])
	board.draw_colored_polygon(pts, Color("#ff7a45"))
	pts.append(pts[0])
	board.draw_polyline(pts, Color("#ffffff"), 2.0)


func _draw_bars() -> void:
	var st: Dictionary
	if mode == "fix":
		if not fix_state.has("probs"):
			return
		st = fix_state
	else:
		if episodes.is_empty() or mode != "watch":
			return
		var steps: Array = _ep()["steps"]
		if w_i >= steps.size():
			return
		st = steps[w_i]
	var font := bars.get_theme_default_font()
	bars.draw_string(font, Vector2(0, 18), "AI scores for the three choices (longer bar = more confident)", HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color("#b8c0cc"))
	for i in ACTS.size():
		var a: String = ACTS[i]
		var pr: float = float(st["probs"].get(a, 0.0))
		var y := 34 + i * 44
		var chosen: bool = a == st["choice"]
		bars.draw_string(font, Vector2(0, y + 26), ACT_TXT[a], HORIZONTAL_ALIGNMENT_LEFT, -1, 19,
			Color.WHITE if chosen else Color("#8b95a5"))
		bars.draw_rect(Rect2(170, y + 6, 380, 28), Color("#1b1f26"))
		bars.draw_rect(Rect2(170, y + 6, 380 * pr, 28), Color("#ff7a45") if chosen else Color("#4a5260"))
		bars.draw_string(font, Vector2(560, y + 28), "%d%%" % roundi(pr * 100), HORIZONTAL_ALIGNMENT_LEFT, -1, 19, Color.WHITE)
		if a == st["bot"] and (mode == "watch" or fix_bot_shown):
			bars.draw_string(font, Vector2(615, y + 28), "<- expert", HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color("#46a758"))


# ---------------------------------------------------------------- fix (correction loop)

func _fix_get(path: String, cb: Callable) -> void:
	if fix_busy or web:   # web: never call the local inference server
		return
	fix_busy = true
	fix_cb = cb
	if http.request(SERVER + path) != OK:
		fix_busy = false
		_on_http(HTTPRequest.RESULT_CANT_CONNECT, 0, PackedStringArray(), PackedByteArray())


func _on_http(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	fix_busy = false
	var data = null
	if result == HTTPRequest.RESULT_SUCCESS and code == 200:
		data = JSON.parse_string(body.get_string_from_utf8())
	if quitting:
		get_tree().quit()
		return
	if data == null:
		fix_cb.call(null)
		return
	if not data.get("ok", false):
		fix_status = "Server error: %s" % data.get("error", "?")
		fix_auto = false
		_refresh()
		return
	fix_cb.call(data)


## /seeds; if nothing answers, start the server in WSL and keep retrying (model load takes a while).
func _fix_connect() -> void:
	_fix_get("/seeds", func(d):
		if d == null:
			if server_pid == 0:
				_start_server()
			fix_retry = 1.0
			fix_status = "Starting the AI server… (loading Laya takes 20-40 s the first time)  %d s" % int(fix_wait)
			_refresh()
			return
		fix_seeds = d["seeds"]
		fix_idx = 0
		_fix_reset())


func _start_server() -> void:
	if web:   # no processes in the browser build
		return
	var root := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()   # repo root (Windows)
	var wsl_root := "/mnt/%s%s" % [root.substr(0, 1).to_lower(), root.substr(2).replace("\\", "/")]
	# no spaces in any argument: Windows command-line quoting of a multi-word "bash -c" string was unreliable
	# open_console=true: without a console of its own wsl.exe exits at once when started from the game
	server_pid = OS.create_process("wsl.exe", ["-d", "Ubuntu", "--cd", wsl_root, "--", "bash", "probe/run_correct_server.sh"], true)
	print("started AI server: pid ", server_pid, " in ", wsl_root)


func _fix_reset() -> void:
	if fix_seeds.is_empty():
		return
	fix_auto = false
	_fix_get("/reset?seed=%d" % int(fix_seeds[fix_idx]["seed"]), func(d):
		if d == null:
			fix_status = "Lost connection to the AI server"
			_refresh()
			return
		fix_room = d["room"]
		fix_state = d
		fix_trail = [Vector2i(int(d["x"]), int(d["y"]))]
		fix_bot_shown = false
		fix_memo = ""
		_refresh())


## action "" = take the model's choice. Any other action differing from it is a correction.
func _fix_step(action: String) -> void:
	if fix_busy or fix_room.is_empty() or fix_state.get("result") != null:
		return
	if action == "":
		action = fix_state["choice"]
	var q := "/step?action=%s" % action.uri_encode()
	if fix_memo != "":
		q += "&memo=" + fix_memo
	_fix_get(q, func(d):
		if d == null:
			fix_status = "Lost connection to the AI server"
			fix_auto = false
			_refresh()
			return
		fix_state = d
		fix_trail.append(Vector2i(int(d["x"]), int(d["y"])))
		fix_bot_shown = false
		fix_memo = ""
		if d.get("result") != null:
			fix_auto = false
		_refresh())


func _fix_set_memo(code: String) -> void:
	if fix_state.get("result") == null and not fix_room.is_empty():
		fix_memo = "" if fix_memo == code else code
		_refresh()


func _fix_set_auto(on: bool) -> void:
	fix_auto = on and fix_state.get("result") == null
	fix_timer = 0.0
	_refresh()


func _fix_process(delta: float) -> void:
	if fix_retry >= 0.0:
		fix_retry -= delta
		fix_wait += delta
		if fix_retry < 0.0:
			if fix_wait > 180.0:
				fix_status = "The AI server did not start. Run it in a WSL terminal: python -m probe.correct_server"
				_refresh()
			else:
				_fix_connect()
	if fix_auto and not fix_busy:
		fix_timer += delta
		if fix_timer >= 0.25:
			fix_timer = 0.0
			_fix_step("")


func _fix_key(k: int, echo: bool) -> bool:
	if echo:
		return false
	match k:
		KEY_ENTER, KEY_KP_ENTER, KEY_SPACE:
			if fix_state.get("result") != null:
				_change_ep(1)
			else:
				_fix_step("")
		KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN:
			if not fix_room.is_empty():
				_fix_step(_screen_key_action(int(fix_state.get("dir", 0)), k))
		KEY_A: _fix_step("turn left")
		KEY_D: _fix_step("turn right")
		KEY_W: _fix_step("forward")
		KEY_B:
			fix_bot_shown = not fix_bot_shown
			_refresh()
		KEY_1, KEY_2, KEY_3, KEY_4, KEY_KP_1, KEY_KP_2, KEY_KP_3, KEY_KP_4:
			_fix_set_memo(str((k - KEY_0) if k <= KEY_9 else (k - KEY_KP_0)))
		KEY_R: _fix_set_auto(not fix_auto)
		KEY_N: _change_ep(1)
		_: return false
	return true


func _refresh_fix() -> void:
	_sync_top_bar()
	fail_tag.visible = false
	seed_sub.text = ""
	watch_bar.visible = false
	_refresh_hints()
	board.queue_redraw()
	bars.queue_redraw()
	if fix_room.is_empty():
		seed_label.text = "Correct: connecting"
		mission_label.text = "Correction loop"
		info.text = fix_status
		text_box.text = ""
		text_title.text = ""
		return
	var st := fix_state
	seed_label.text = "Correct room %d of %d" % [fix_idx + 1, fix_seeds.size()]
	seed_sub.text = "seed %d" % int(fix_room["seed"])
	mission_label.text = "Mission: %s" % fix_room["mission"]
	var s := "[b]Step %d / %d[/b] · corrections %d · memos %d\n[color=#8b95a5]%s[/color]\n" % [int(st["step"]),
		int(fix_room["max_steps"]), int(st["corrections"]), int(st["memos"]), fix_room["note"]]
	if st.get("result") != null:
		var res: String = st["result"]
		s += ("[color=#46a758][b]Success![/b][/color]" if res == "success" else "[color=#e5484d][b]Failed: all 64 steps used.[/b][/color]")
		s += "  log saved (data/correct_log.jsonl)\n"
		if fix_idx == fix_seeds.size() - 1:
			s += "[color=#f5c518][b]All %d rooms done.[/b][/color] You can close the window (Enter/N starts over)" % fix_seeds.size()
		else:
			s += "Enter or N: next room"
		text_box.text = ""
	else:
		s += "AI chose: [b]%s[/b] (%d%%)" % [ACT_TXT[st["choice"]], roundi(float(st["probs"][st["choice"]]) * 100)]
		if fix_bot_shown:
			var same: bool = st["bot"] == st["choice"]
			s += ("   bot agrees: [color=#46a758]%s[/color]" if same else "   [color=#f5a524]the bot would: %s[/color]") % ACT_TXT.get(st["bot"], st["bot"])
		else:
			s += "   [color=#5d6675](B shows the bot's choice)[/color]"
		if fix_memo != "":
			s += "\nMemo for this step: [color=#f5c518]%s. %s[/color] (press again to cancel)" % [fix_memo, MEMO_TXT[fix_memo]]
		if fix_auto:
			s += "\n[color=#f5c518]Running the AI to the end (R stops)[/color]"
		text_box.text = st["input"]
	info.text = s
	text_title.text = "Text the AI got now (it chose from this alone):"


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		if server_pid != 0 and not quitting:
			# the server was started by this game: stop it (it also saves an unfinished episode as "quit")
			quitting = true
			fix_busy = false
			fix_cb = func(_d): pass
			http.cancel_request()
			http.request(SERVER + "/quit")
			get_tree().create_timer(2.0).timeout.connect(func(): get_tree().quit())
		else:
			get_tree().quit()


## Arrow keys are screen-based but still map to exactly one of the model's three actions:
## facing that way -> forward; it is on the agent's left -> turn left; right or behind -> turn right.
func _screen_key_action(cur_dir: int, key: int) -> String:
	var want: int = {KEY_RIGHT: 0, KEY_DOWN: 1, KEY_LEFT: 2, KEY_UP: 3}[key]
	if want == cur_dir:
		return "forward"
	if want == (cur_dir + 3) % 4:
		return "turn left"
	return "turn right"
