# Provenance of `episodes.json`

**This is recorded playback, not live inference.** The game replays these walks; no model runs in the game or the web build.

| | |
|---|---|
| Fine-tuned checkpoint | `babyai-laya-ft/gotolocal-s0` (seed 0, stage 2b of this repo; `reports/stage3.md`) |
| Base model | [`convaiinnovations/laya`](https://huggingface.co/convaiinnovations/laya), english checkpoint, revision `55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851` |
| Laya package | `laya` 0.4.31 (PyPI) |
| Environment | `BabyAI-GoToLocal-v0`, `minigrid` 3.2.0 |
| Export script | `probe/export_godot.py` (added in commit `a3a591b`), run with its defaults on 2026-11-14 |
| Seeds (35, dev set only) | 10000–10029, plus the five rooms that all three fine-tuned models failed in stage 3.5 and that are not in that range: 10122, 10149, 10164, 10220, 10242 (`all_models_failed` marks all 12 such rooms). Seeds 20000–20299 (final check) are not used. |
| Per step | agent position and facing, the exact text given to the model, its three choice scores and its choice, and the choice of MiniGrid's expert bot (`BabyAIBot`) from the same state |

The only edit after export: the top-level `"model"` field held a local filesystem path and was replaced by the checkpoint identifier above. Every episode is byte-for-byte the same as exported.

**Regenerating this exact recording is not possible from a fresh clone.** The fine-tuned checkpoint is not distributed. With the checkpoint, the command is in the README ("게임으로 보기").

## License references

- Base model `convaiinnovations/laya`: Apache-2.0 (model card at the revision above). The model repository has no NOTICE file. The model itself is not redistributed here.
- `laya` package 0.4.31: Apache-2.0. Not redistributed here.
- `minigrid` 3.2.0: Apache-2.0 according to the repository's `LICENSE` file (the full Apache License 2.0 text, also shipped inside the PyPI package); its `pyproject.toml` and PyPI metadata say "MIT License". Checked 2026-11-15. Not redistributed here; the room layouts and expert moves in this file, and the demonstrations the drive policy was trained on, were produced with it.
- The web build of the game contains the Godot Engine (MIT, with third-party components). Its copyright and license notices must accompany any published build.

These references describe where the recording came from. They do not set a license for this repository or for this file; this repository has no license file of its own.
