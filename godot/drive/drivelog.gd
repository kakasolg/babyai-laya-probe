extends RefCounted
## What happened in each room, one JSON line per room, kept on this machine only (user://drive_log.jsonl — in the web
## build that is the browser's own storage). Nothing is sent anywhere. No reasons are asked for: only what was done.
##
## A line: {"v": 1, "when": unix seconds, "level": autopilot level, "view_mode": what the driver could see,
##          "room": the room dictionary (layout, target, start, par), "result": "success" | "timeout" | "left",
##          "turns": n, "takeovers": n, "steps": [
##             {"x", "y", "dir", "by": "auto" | "driver", "a": action taken (0 left, 1 right, 2 forward),
##              "m": what the autopilot would have done, "s": its three scores, "alarm": the autopilot had stopped itself here,
##              "vm": what the driver could see at this step (added 11-15; "view_mode" above is the room's start)}]}
## Puzzle mode (drive/PUZZLE.md) adds "mode": "puzzle", "nudge_par" (fewest nudges for the room) and "nudges" (how many
## the driver gave); its driver steps are those nudges. "v" stays 1.

## Where the files live. Static so a test can point them elsewhere (selftest_drive.gd does) without touching real records.
static var path := "user://drive_log.jsonl"
static var garage_path := "user://garage.json"

var _rec := {}


## extra: fields added to the line as they are (puzzle mode: "mode": "puzzle", "nudge_par").
func begin(ep: Dictionary, level: int, view_mode: int, extra := {}) -> void:
	_rec = {"v": 1, "when": int(Time.get_unix_time_from_system()), "level": level, "view_mode": view_mode,
		"room": ep, "steps": []}
	_rec.merge(extra)


## view: what the driver could see at this step (same numbers as view_mode); -1 leaves it out.
func step(pos: Vector2i, dir: int, by: String, action: int, model_action: int, model_scores: Array, alarm: bool,
		view := -1) -> void:
	if _rec.is_empty():
		return
	var st := {"x": pos.x, "y": pos.y, "dir": dir, "by": by, "a": action, "m": model_action,
		"s": model_scores, "alarm": alarm}
	if view >= 0:
		st["vm"] = view
	_rec["steps"].append(st)


func end(result: String, turns: int, takeovers: int, extra := {}) -> void:
	if _rec.is_empty():
		return
	_rec["result"] = result
	_rec["turns"] = turns
	_rec["takeovers"] = takeovers
	_rec.merge(extra, true)
	var f: FileAccess = FileAccess.open(path, FileAccess.READ_WRITE) if FileAccess.file_exists(path) else FileAccess.open(path, FileAccess.WRITE)
	if f != null:
		f.seek_end()
		f.store_line(JSON.stringify(_rec))
		f.close()
	_rec = {}


static func read_all() -> String:
	return FileAccess.get_file_as_string(path) if FileAccess.file_exists(path) else ""


## Lets the player save their own record as a file (web: a browser download; desktop: returns the absolute path).
static func export_file() -> String:
	if OS.has_feature("web"):
		JavaScriptBridge.download_buffer(read_all().to_utf8_buffer(), "drive_log.jsonl", "application/json")
		return "drive_log.jsonl"
	return ProjectSettings.globalize_path(path)


# ---- the "garage": rooms that took 35 turns or more, or were not finished, kept to be driven again

static func garage() -> Array:
	if not FileAccess.file_exists(garage_path):
		return []
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(garage_path))
	return parsed if parsed is Array else []


static func _garage_save(items: Array) -> void:
	var f := FileAccess.open(garage_path, FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(items))
		f.close()


static func garage_add(ep: Dictionary, result: String, turns: int, level: int) -> void:
	var items := garage()
	items.append({"room": ep, "result": result, "turns": turns, "level": level, "when": int(Time.get_unix_time_from_system())})
	_garage_save(items)


static func garage_remove(index: int) -> void:
	var items := garage()
	if index >= 0 and index < items.size():
		items.remove_at(index)
		_garage_save(items)


## The rule MoKa set (2026-11-15): a room goes to the garage when it took 35 turns or more, or was not finished.
static func belongs_in_garage(result: String, turns: int) -> bool:
	return result != "success" or turns >= 35
