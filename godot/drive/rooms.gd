extends RefCounted
## Fresh GoToLocal-style rooms in the same dictionary shape as data/episodes.json, so main.gd's helpers
## (_is_wall, _obj_at, _is_target, _play_act, _obs_text) work on them unchanged.
## Not MiniGrid's generator: objects are dropped at random and a room is kept only if a matching object can be reached.
## Mirrors tools/small_policy/gd_mirror.py (make_room, par).

const Autopilot := preload("res://drive/autopilot.gd")
const TYPES := ["key", "ball", "box"]
const COLORS := ["red", "green", "blue", "purple", "yellow", "grey"]
const DIR_VEC := [Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(0, -1)]


static func is_target(ep: Dictionary, x: int, y: int) -> bool:
	for p in ep["target"]["positions"]:
		if int(p[0]) == x and int(p[1]) == y:
			return true
	return false


static func is_free(ep: Dictionary, x: int, y: int) -> bool:
	return Autopilot.cell_code(ep, x, y) == Vector2i(1, 0)


## Fewest moves (turn left / turn right / forward) until a matching object is directly ahead; -1 if it cannot be done.
static func par(ep: Dictionary) -> int:
	var start := Vector3i(int(ep["start"]["x"]), int(ep["start"]["y"]), int(ep["start"]["dir"]))
	var seen := {start: true}
	var frontier: Array = [start]
	var depth := 0
	while not frontier.is_empty():
		var next: Array = []
		for s in frontier:
			var f: Vector2i = Vector2i(s.x, s.y) + DIR_VEC[s.z]
			if is_target(ep, f.x, f.y):
				return depth
			var moves: Array = [Vector3i(s.x, s.y, (s.z + 3) % 4), Vector3i(s.x, s.y, (s.z + 1) % 4)]
			if is_free(ep, f.x, f.y):
				moves.append(Vector3i(f.x, f.y, s.z))
			for m in moves:
				if not seen.has(m):
					seen[m] = true
					next.append(m)
		frontier = next
		depth += 1
	return -1


## A new room. `id` goes into "seed" (a label only — rooms are not reproducible from it; keep the dictionary to replay).
static func make(rng: RandomNumberGenerator, size := 8, n_objs := 8, id := "") -> Dictionary:
	while true:
		var cells: Array = []
		for x in range(1, size - 1):
			for y in range(1, size - 1):
				cells.append(Vector2i(x, y))
		for i in range(cells.size() - 1, 0, -1):          # Fisher-Yates with the caller's rng
			var j := rng.randi_range(0, i)
			var tmp: Vector2i = cells[i]
			cells[i] = cells[j]
			cells[j] = tmp
		var objs: Array = []
		for k in n_objs:
			var c: Vector2i = cells.pop_back()
			objs.append({"x": c.x, "y": c.y, "type": TYPES[rng.randi_range(0, 2)], "color": COLORS[rng.randi_range(0, 5)]})
		var sp: Vector2i = cells.pop_back()
		var t: Dictionary = objs[rng.randi_range(0, n_objs - 1)]
		var positions: Array = []
		for o in objs:
			if o["type"] == t["type"] and o["color"] == t["color"]:
				positions.append([o["x"], o["y"]])
		var ep := {
			"seed": id, "width": size, "height": size, "objects": objs,
			"target": {"type": t["type"], "color": t["color"], "positions": positions},
			"start": {"x": sp.x, "y": sp.y, "dir": rng.randi_range(0, 3)},
			"max_steps": size * size, "steps": [], "generated": true,
			"mission": "go to %s %s %s" % ["a" if positions.size() > 1 else "the", t["color"], t["type"]],
		}
		ep["par"] = par(ep)
		if int(ep["par"]) > 0:
			return ep
	return {}
