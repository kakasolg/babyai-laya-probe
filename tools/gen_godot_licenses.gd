extends SceneTree

# Writes Godot's own license and third-party notices (from the running 4.7.2 binary) to the path after "--".

func _init() -> void:
	var out_path: String = OS.get_cmdline_user_args()[0]
	var v := Engine.get_version_info()
	var s := "Third-party notices for the web build of \"BabyAI Laya: an AI in the room\"\n"
	s += "==========================================================================\n\n"
	s += "This game runs on the Godot Engine %s (https://godotengine.org/license).\n" % v["string"]
	s += "The notices below were generated with Engine.get_license_text(), Engine.get_copyright_info()\n"
	s += "and Engine.get_license_info() from the official Godot %s editor binary; the web export\n" % v["string"]
	s += "template contains a subset of these components.\n\n"
	s += "These notices cover the engine only. They do not license the game's own code or its recorded data.\n\n"
	s += "--------------------------------------------------------------------------\nGodot Engine\n--------------------------------------------------------------------------\n\n"
	s += Engine.get_license_text() + "\n\n"
	s += "--------------------------------------------------------------------------\nThird-party components\n--------------------------------------------------------------------------\n\n"
	for c in Engine.get_copyright_info():
		s += "%s\n" % c["name"]
		for p in c["parts"]:
			for line in p["copyright"]:
				s += "    Copyright %s\n" % line
			s += "    License: %s\n" % p["license"]
		s += "\n"
	s += "--------------------------------------------------------------------------\nLicense texts\n--------------------------------------------------------------------------\n\n"
	var info := Engine.get_license_info()
	var names := info.keys()
	names.sort()
	for n in names:
		s += "License: %s\n\n%s\n\n" % [n, info[n]]
	var f := FileAccess.open(out_path, FileAccess.WRITE)
	f.store_string(s)
	f.close()
	print("wrote ", out_path, " ", s.length(), " chars, components ", Engine.get_copyright_info().size(), ", licenses ", names.size())
	quit()
