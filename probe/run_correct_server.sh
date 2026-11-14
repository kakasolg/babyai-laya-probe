#!/usr/bin/env bash
# Started by the Godot game (교정 mode) via: wsl.exe -d Ubuntu --cd <repo> -- bash probe/run_correct_server.sh
cd "$(dirname "$0")/.." && HF_HUB_OFFLINE=1 exec ~/babyai-laya-venv/bin/python -m probe.correct_server "$@"
