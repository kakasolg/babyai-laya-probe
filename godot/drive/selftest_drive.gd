extends SceneTree
## Headless check of the drive engine:
##   Godot_v4.7.2-stable_win64_console.exe --headless --path godot --script res://drive/selftest_drive.gd
## 1) view() against 150 views computed in Python from MiniGrid's rules   2) scores() against 200 stored vectors per level
## 3) time per decision   4) rooms.gd: par and the autopilot alone on 150 generated rooms per level
## 5) drivelog.gd: writes two rooms and reads them back, the 35-turn rule, garage add/remove, export_file
##    (in user://selftest_* files, removed afterwards; the real drive_log.jsonl / garage.json are not touched)
## Expected (from the Python mirror, 2026-11-15): view mismatches 0; score difference below 1e-3 and the same action on
## all 200; level 3 alone solves roughly 90 % of generated rooms, level 2 fewer, level 1 fewer still.

const Autopilot := preload("res://drive/autopilot.gd")
const Rooms := preload("res://drive/rooms.gd")
const DriveLog := preload("res://drive/drivelog.gd")


func _init() -> void:
	var failures := 0
	var cases = JSON.parse_string(FileAccess.get_file_as_string("res://data/drive_view_test.json"))
	var bad := 0
	for c in cases:
		var v := Autopilot.view(c["room"], Vector2i(int(c["x"]), int(c["y"])), int(c["dir"]))
		var want: Array = c["view"]
		for k in 98:
			if v[k] != int(want[k]):
				bad += 1
				break
	print("view: %d cases, mismatches %d" % [cases.size(), bad])
	failures += bad
	for n in [1, 2, 3]:
		var ap = Autopilot.new()
		if not ap.load_level(n):
			print("level %d: could not load res://data/policy_l%d.json" % [n, n])
			failures += 1
			continue
		var vec = JSON.parse_string(FileAccess.get_file_as_string("res://data/policy_l%d_test.json" % n))
		var worst := 0.0
		var same := 0
		var t0 := Time.get_ticks_usec()
		for e in vec:
			var s: PackedFloat32Array = ap.scores(PackedInt32Array(e["view"]), int(e["color"]), int(e["kind"]))
			var best := 0
			for a in range(1, 3):
				if s[a] > s[best]:
					best = a
			if best == int(e["action"]):
				same += 1
			for a2 in 3:
				worst = maxf(worst, absf(s[a2] - float(e["logits"][a2])))
		var ms := float(Time.get_ticks_usec() - t0) / 1000.0 / float(vec.size())
		print("level %d: %d vectors, max score difference %.5f, same action %d/%d, %.1f ms per decision" % [n, vec.size(), worst, same, vec.size(), ms])
		if same != vec.size() or worst > 0.001:
			failures += 1
		var rng := RandomNumberGenerator.new()
		rng.seed = 11
		var solved := 0
		var stuck := 0
		var par_sum := 0
		for r in 150:
			var ep := Rooms.make(rng, 8, 8, "t%d" % r)
			par_sum += int(ep["par"])
			var pos := Vector2i(int(ep["start"]["x"]), int(ep["start"]["y"]))
			var dir := int(ep["start"]["dir"])
			ap.forget()
			for step in int(ep["max_steps"]):
				var d: Dictionary = ap.decide(ep, pos, dir)
				if d["stuck"]:
					stuck += 1
					break
				if int(d["action"]) == 0:
					dir = (dir + 3) % 4
				elif int(d["action"]) == 1:
					dir = (dir + 1) % 4
				else:
					var f: Vector2i = pos + Autopilot.DIR_VEC[dir]
					if Rooms.is_free(ep, f.x, f.y):
						pos = f
				var front: Vector2i = pos + Autopilot.DIR_VEC[dir]
				if Rooms.is_target(ep, front.x, front.y):
					solved += 1
					break
		print("level %d: 150 generated rooms, mean par %.2f, autopilot alone solved %d, stopped as stuck %d" % [n, float(par_sum) / 150.0, solved, stuck])
	failures += _check_drivelog()
	print("drive selftest: %s" % ("OK" if failures == 0 else "%d problem(s)" % failures))
	quit(0 if failures == 0 else 1)


func _expect(ok: bool, what: String) -> int:
	if not ok:
		print("  drivelog FAIL: ", what)
		return 1
	return 0


## Writes to user://selftest_*.json(l) only, and removes them afterwards.
func _check_drivelog() -> int:
	var bad := 0
	var keep_path: String = DriveLog.path
	var keep_garage: String = DriveLog.garage_path
	DriveLog.path = "user://selftest_drive_log.jsonl"
	DriveLog.garage_path = "user://selftest_garage.json"
	for f in [DriveLog.path, DriveLog.garage_path]:
		if FileAccess.file_exists(f):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(f))
	bad += _expect(DriveLog.read_all() == "", "an empty log reads as an empty string")
	bad += _expect(DriveLog.garage().is_empty(), "an empty garage is an empty list")
	var rng := RandomNumberGenerator.new()
	rng.seed = 5
	var ap = Autopilot.new()
	ap.load_level(1)
	var log = DriveLog.new()
	var last_room := {}
	for r in 2:
		var ep := Rooms.make(rng, 8, 8, "log%d" % r)
		last_room = ep
		var pos := Vector2i(int(ep["start"]["x"]), int(ep["start"]["y"]))
		var dir := int(ep["start"]["dir"])
		log.begin(ep, 1, 1)
		for step in 3:
			var m: Dictionary = ap.peek(ep, pos, dir)
			log.step(pos, dir, "auto" if step < 2 else "driver", int(m["action"]), int(m["action"]), m["scores"], step == 2, 1 + step % 2)
			dir = (dir + 1) % 4
		log.end("success" if r == 0 else "timeout", 3, r)
	var lines := DriveLog.read_all().strip_edges().split("\n")
	bad += _expect(lines.size() == 2, "two rooms written = two lines (got %d)" % lines.size())
	for i in lines.size():
		var rec = JSON.parse_string(lines[i])
		bad += _expect(rec is Dictionary, "line %d parses as a dictionary" % i)
		if not (rec is Dictionary):
			continue
		bad += _expect(int(rec["v"]) == 1 and int(rec["level"]) == 1 and int(rec["view_mode"]) == 1, "line %d header fields" % i)
		bad += _expect(String(rec["result"]) == ("success" if i == 0 else "timeout"), "line %d result" % i)
		bad += _expect(int(rec["turns"]) == 3 and int(rec["takeovers"]) == i, "line %d turns and takeovers" % i)
		bad += _expect(rec["room"]["objects"].size() == 8 and rec["room"].has("par"), "line %d keeps the room" % i)
		var steps: Array = rec["steps"]
		bad += _expect(steps.size() == 3, "line %d has three steps" % i)
		if steps.size() == 3:
			bad += _expect(String(steps[0]["by"]) == "auto" and String(steps[2]["by"]) == "driver", "line %d who drove" % i)
			bad += _expect(steps[2]["alarm"] == true and steps[0]["alarm"] == false, "line %d alarm flag" % i)
			bad += _expect(steps[1]["s"].size() == 3 and steps[1].has("m") and steps[1].has("a"), "line %d model scores and choices" % i)
			bad += _expect(int(steps[0]["vm"]) == 1 and int(steps[1]["vm"]) == 2, "line %d view at each step" % i)
	bad += _expect(not DriveLog.belongs_in_garage("success", 34), "34 turns and solved stays out of the garage")
	bad += _expect(DriveLog.belongs_in_garage("success", 35), "35 turns goes to the garage")
	bad += _expect(DriveLog.belongs_in_garage("timeout", 5), "an unfinished room goes to the garage")
	DriveLog.garage_add(last_room, "timeout", 64, 1)
	DriveLog.garage_add(last_room, "success", 40, 2)
	var g := DriveLog.garage()
	bad += _expect(g.size() == 2, "garage holds two rooms (got %d)" % g.size())
	if g.size() == 2:
		bad += _expect(g[0]["room"]["objects"].size() == 8 and int(g[1]["turns"]) == 40 and int(g[1]["level"]) == 2, "garage entries keep room, turns, level")
	DriveLog.garage_remove(0)
	bad += _expect(DriveLog.garage().size() == 1, "removing one leaves one")
	DriveLog.garage_remove(7)
	bad += _expect(DriveLog.garage().size() == 1, "removing a missing index changes nothing")
	if not OS.has_feature("web"):
		bad += _expect(FileAccess.file_exists(DriveLog.export_file()), "export_file returns a path that exists")
	for f2 in [DriveLog.path, DriveLog.garage_path]:
		if FileAccess.file_exists(f2):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(f2))
	DriveLog.path = keep_path
	DriveLog.garage_path = keep_garage
	print("drivelog: wrote and read back 2 rooms, 35-turn rule, garage add/remove — %s" % ("OK" if bad == 0 else "%d problem(s)" % bad))
	return bad
