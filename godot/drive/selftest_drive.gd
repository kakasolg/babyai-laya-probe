extends SceneTree
## Headless check of the drive engine:
##   Godot_v4.7.2-stable_win64_console.exe --headless --path godot --script res://drive/selftest_drive.gd
## 1) view() against 150 views computed in Python from MiniGrid's rules   2) scores() against 200 stored vectors per level
## 3) time per decision   4) rooms.gd: par and the autopilot alone on 150 generated rooms per level
## Expected (from the Python mirror, 2026-11-15): view mismatches 0; score difference below 1e-3 and the same action on
## all 200; level 3 alone solves roughly 90 % of generated rooms, level 2 fewer, level 1 fewer still.

const Autopilot := preload("res://drive/autopilot.gd")
const Rooms := preload("res://drive/rooms.gd")


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
	print("drive selftest: %s" % ("OK" if failures == 0 else "%d problem(s)" % failures))
	quit(0 if failures == 0 else 1)
