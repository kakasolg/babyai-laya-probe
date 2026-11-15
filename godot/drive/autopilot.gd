extends RefCounted
## The "autopilot": a small on-device policy for the GoToLocal room. **Not Laya** — a 66,787-parameter CNN that copied
## MiniGrid's BabyAI expert bot (tools/small_policy/). It sees only the 7x7 view in front of the agent and the mission's
## colour and type, and has no memory. Three levels = three amounts of training data (data/policy_l1..3.json).
##
## Use:  const Autopilot := preload("res://drive/autopilot.gd")
##       var ap := Autopilot.new();  ap.load_level(2)
##       var d := ap.decide(room, pos, dir)    # {"action": 0|1|2, "scores": [..], "stuck": bool}
## Written to mirror tools/small_policy/gd_mirror.py line by line; check with drive/selftest_drive.gd.

const OBJ_IDX := {"key": 5, "ball": 6, "box": 7}                      # MiniGrid OBJECT_TO_IDX (0 unseen, 1 empty, 2 wall)
const COLOR_IDX := {"red": 0, "green": 1, "blue": 2, "purple": 3, "yellow": 4, "grey": 5}
const KIND_IDX := {"ball": 0, "box": 1, "key": 2}                     # mission type index the policy was trained with
const DIR_VEC := [Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(0, -1)]   # same as main.gd
const ACTS := ["turn left", "turn right", "forward"]                 # index = MiniGrid action number

var level := 0
var ch := 16
var hid := 64
var info := {}          # the json's fields other than the weights (demo_episodes, solved_alone_of_300_fresh_rooms, ...)
var _t := {}            # tensor name -> PackedFloat32Array (flat, row-major)
var _seen := {}         # views the autopilot has already driven through since forget()


func load_level(n: int) -> bool:
	var txt := FileAccess.get_file_as_string("res://data/policy_l%d.json" % n)
	if txt == "":
		return false
	var parsed = JSON.parse_string(txt)
	if not (parsed is Dictionary):
		return false
	level = n
	ch = int(parsed["ch"])
	hid = int(parsed["hid"])
	_t.clear()
	var tensors: Dictionary = parsed["tensors"]
	for tname in tensors:
		_t[tname] = PackedFloat32Array(tensors[tname]["data"])
	parsed.erase("tensors")
	info = parsed
	_seen.clear()
	return true


## (object idx, colour idx) of a room cell; empty floor = (1, 0); the border and anything outside = wall (2, 5).
static func cell_code(ep: Dictionary, x: int, y: int) -> Vector2i:
	if x <= 0 or y <= 0 or x >= int(ep["width"]) - 1 or y >= int(ep["height"]) - 1:
		return Vector2i(2, 5)
	for o in ep["objects"]:
		if int(o["x"]) == x and int(o["y"]) == y:
			return Vector2i(int(OBJ_IDX[o["type"]]), int(COLOR_IDX[o["color"]]))
	return Vector2i(1, 0)


## The 7x7 view MiniGrid would give: 98 ints, [(i * 7 + j) * 2] = object idx, [+1] = colour idx.
## The agent is at i = 3, j = 6 looking toward j = 0; i grows to its right. Hidden cells are (0, 0).
static func view(ep: Dictionary, pos: Vector2i, dir: int) -> PackedInt32Array:
	var fwd: Vector2i = DIR_VEC[dir]
	var right: Vector2i = DIR_VEC[(dir + 1) % 4]
	var obj := PackedInt32Array()
	obj.resize(49)
	var col := PackedInt32Array()
	col.resize(49)
	for i in 7:
		for j in 7:
			var c: Vector2i = pos + fwd * (6 - j) + right * (i - 3)
			var code := cell_code(ep, c.x, c.y)
			obj[i * 7 + j] = code.x
			col[i * 7 + j] = code.y
	obj[27] = 1          # the agent's own cell (3 * 7 + 6) reads as empty floor
	col[27] = 0
	# visibility, the same sweep as MiniGrid's Grid.process_vis: walls are seen but nothing behind them
	var mask := PackedByteArray()
	mask.resize(49)
	mask.fill(0)
	mask[27] = 1
	for j in range(6, -1, -1):
		for i in range(0, 6):
			var p := i * 7 + j
			if mask[p] == 1 and obj[p] != 2:
				mask[p + 7] = 1
				if j > 0:
					mask[p + 6] = 1
					mask[p - 1] = 1
		for i2 in range(6, 0, -1):
			var q := i2 * 7 + j
			if mask[q] == 1 and obj[q] != 2:
				mask[q - 7] = 1
				if j > 0:
					mask[q - 8] = 1
					mask[q - 1] = 1
	var out := PackedInt32Array()
	out.resize(98)
	out.fill(0)
	for k in 49:
		if mask[k] == 1:
			out[k * 2] = obj[k]
			out[k * 2 + 1] = col[k]
	return out


func _conv(x: PackedFloat32Array, cin: int, tname: String) -> PackedFloat32Array:
	var w: PackedFloat32Array = _t[tname + ".weight"]      # [ch, cin, 3, 3]
	var b: PackedFloat32Array = _t[tname + ".bias"]
	var out := PackedFloat32Array()
	out.resize(ch * 49)
	for o in ch:
		var base := o * 49
		var bo: float = b[o]
		for p in 49:
			out[base + p] = bo
		for c in cin:
			var wb := (o * cin + c) * 9
			var xb := c * 49
			for di in 3:
				var i0 := maxi(0, 1 - di)
				var i1 := mini(7, 8 - di)
				for dj in 3:
					var wv: float = w[wb + di * 3 + dj]
					var j0 := maxi(0, 1 - dj)
					var j1 := mini(7, 8 - dj)
					for i in range(i0, i1):
						var src := xb + (i + di - 1) * 7 + (dj - 1)
						var dst := base + i * 7
						for j in range(j0, j1):
							out[dst + j] += wv * x[src + j]
	return out


func _film(x: PackedFloat32Array, tname: String, m: PackedFloat32Array) -> PackedFloat32Array:
	var w: PackedFloat32Array = _t[tname + ".weight"]      # [2 * ch, 64]
	var b: PackedFloat32Array = _t[tname + ".bias"]
	for o in ch:
		var g: float = b[o]
		var be: float = b[ch + o]
		for k in 64:
			g += w[o * 64 + k] * m[k]
			be += w[(ch + o) * 64 + k] * m[k]
		for p in 49:
			var v: float = x[o * 49 + p] * (1.0 + g) + be
			x[o * 49 + p] = v if v > 0.0 else 0.0
	return x


## Scores of the three actions for one view (from view()), mission colour index and mission type index.
func scores(v: PackedInt32Array, color: int, kind: int) -> PackedFloat32Array:
	var eo: PackedFloat32Array = _t["eo.weight"]
	var ec: PackedFloat32Array = _t["ec.weight"]
	var xy: PackedFloat32Array = _t["xy"]
	var x := PackedFloat32Array()
	x.resize(34 * 49)
	for p in 49:
		var ob := v[p * 2]
		var co := v[p * 2 + 1]
		for k in 16:
			x[k * 49 + p] = eo[ob * 16 + k]
			x[(16 + k) * 49 + p] = ec[co * 16 + k]
		x[32 * 49 + p] = xy[p]
		x[33 * 49 + p] = xy[49 + p]
	var mc: PackedFloat32Array = _t["mc.weight"]
	var mt: PackedFloat32Array = _t["mt.weight"]
	var m := PackedFloat32Array()
	m.resize(64)
	for k2 in 32:
		m[k2] = mc[color * 32 + k2]
		m[32 + k2] = mt[kind * 32 + k2]
	x = _film(_conv(x, 34, "c1"), "f1", m)
	x = _film(_conv(x, ch, "c2"), "f2", m)
	x = _film(_conv(x, ch, "c3"), "f3", m)
	var n := ch * 49
	var w1: PackedFloat32Array = _t["h1.weight"]           # [hid, ch * 49]
	var b1: PackedFloat32Array = _t["h1.bias"]
	var h := PackedFloat32Array()
	h.resize(hid)
	for a in hid:
		var acc: float = b1[a]
		var wb := a * n
		for q in n:
			acc += w1[wb + q] * x[q]
		h[a] = acc if acc > 0.0 else 0.0
	var w2: PackedFloat32Array = _t["h2.weight"]           # [3, hid]
	var b2: PackedFloat32Array = _t["h2.bias"]
	var out := PackedFloat32Array()
	out.resize(3)
	for a2 in 3:
		var acc2: float = b2[a2]
		for q2 in hid:
			acc2 += w2[a2 * hid + q2] * h[q2]
		out[a2] = acc2
	return out


## What the autopilot would do here, without touching its memory (use it to log the model's choice while a person drives).
func peek(ep: Dictionary, pos: Vector2i, dir: int) -> Dictionary:
	var v := view(ep, pos, dir)
	var s := scores(v, int(COLOR_IDX[ep["target"]["color"]]), int(KIND_IDX[ep["target"]["type"]]))
	var best := 0
	for a in range(1, 3):
		if s[a] > s[best]:
			best = a
	return {"action": best, "scores": [s[0], s[1], s[2]], "key": "%d:%s" % [dir, v.to_byte_array().hex_encode()]}


## One autopilot move. "stuck" = it has already driven through this exact view (and heading) since forget(): the policy
## is deterministic, so from here it would only repeat itself. When stuck is true, do not apply the action — hand over.
func decide(ep: Dictionary, pos: Vector2i, dir: int) -> Dictionary:
	var d := peek(ep, pos, dir)
	d["stuck"] = _seen.has(d["key"])
	if not d["stuck"]:
		_seen[d["key"]] = true
	return d


## Call when a room starts and whenever the driver has taken over (the autopilot starts with a clean record afterwards).
func forget() -> void:
	_seen.clear()
