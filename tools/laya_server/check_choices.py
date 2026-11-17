"""Check the Windows ONNX Laya against the recorded PyTorch choices in godot/data/episodes.json (944 steps, dev seeds).
Usage: D:\\dev\\tools\\laya-win-venv\\Scripts\\python.exe tools/laya_server/check_choices.py <model dir> <laya_fp32.onnx>"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from probe.laya_model import OnnxChooser  # noqa: E402
from probe.laya_rows import QID, question  # noqa: E402
from probe.obs_text import CHOICES  # noqa: E402

root = pathlib.Path(__file__).resolve().parents[2]
steps = [s for e in json.load(open(root / "godot/data/episodes.json", encoding="utf-8"))["episodes"] for s in e["steps"]]
ch = OnnxChooser(sys.argv[1], sys.argv[2])
t = time.time()
res = ch.agent.predict_batch([s["input"] for s in steps], question(CHOICES), batch_size=32)
got = [max(p, key=p.get) for p in (r["answers"][QID].get("probabilities") or {} for r in res)]
same = sum(g == s["choice"] for g, s in zip(got, steps))
print(f"same choice as the recorded PyTorch run: {same}/{len(steps)}  ({time.time() - t:.0f} s)")
sys.exit(0 if same == len(steps) else 1)
