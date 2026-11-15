extends RefCounted
## What happened in each room, one JSON line per room, kept on this machine only (user://drive_log.jsonl — in the web
## build that is the browser's own storage). Nothing is sent anywhere. No reasons are asked for: only what was done.
##
## A line: {"v": 1, "when": unix seconds, "level": autopilot level, "view_mode": what the driver could see,
##          "room": the room dictionary (layout, target, start, par), "result": "success" | "timeout" | "left",
##          "turns": n, "takeovers": n, "steps": [
##             {"x", "y", "dir", "by": "auto" | "driver", "a": action taken (0 left, 1 right, 2 forward),
##              "m": what the autopilot would have done, "s": its three scores, "alarm": the autopilot had stopped itself here}]}

const PATH := "user://drive_log.jsonl"
const GARAGE := "user://garage.json"

var _rec := {}


func begin(ep: Dictionary, level: int, view_mode: int) -> void:
	_rec = {"v": 1, "when": int(Time.get_unix_time_from_system()), "level": level, "view_mode": view_mode,
		"room": ep, "steps": []}


func step(pos: Vector2i, dir: int, by: String, action: int, model_action: int, model_scores: Array, alarm: bool) -> void:
	if _rec.is_empty():
		return
	_rec["steps"].append({"x": pos.x, "y": pos.y, "dir": dir, "by": by, "a": action, "m": model_action,
		"s": model_scores, "alarm": alarm})


func end(result: String, turns: int, takeovers: int) -> void:
	if _rec.is_empty():
		return
	_rec["result"] = result
	_rec["turns"] = turns
	_rec["takeovers"] = takeovers
	var f: FileAccess = FileAccess.open(PATH, FileAccess.READ_WRITE) if FileAccess.file_exists(PATH) else FileAccess.open(PATH, FileAccess.WRITE)
	if f != null:
		f.seek_end()
		f.store_line(JSON.stringify(_rec))
		f.close()
	_rec = {}


static func read_all() -> String:
	return FileAccess.get_file_as_string(PATH) if FileAccess.file_exists(PATH) else ""


## Lets the player save their own record as a file (web: a browser download; desktop: returns the absolute path).
static func export_file() -> String:
	if OS.has_feature("web"):
		JavaScriptBridge.download_buffer(read_all().to_utf8_buffer(), "drive_log.jsonl", "application/json")
		return "drive_log.jsonl"
	return ProjectSettings.globalize_path(PATH)


# ---- the "garage": rooms that took 35 turns or more, or were not finished, kept to be driven again

static func garage() -> Array:
	if not FileAccess.file_exists(GARAGE):
		return []
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(GARAGE))
	return parsed if parsed is Array else []


static func _garage_save(items: Array) -> void:
	var f := FileAccess.open(GARAGE, FileAccess.WRITE)
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
