"""Stage 4 correction loop as a tiny local HTTP server, for the Godot game (godot/, "교정" mode).

Same rules as probe/correct_loop.py: the model picks, the person may replace the action (= correction,
only logged, never trained on), memo codes 1-4, escape rule OFF, seeds 20000-20299 refused.
Log rows go to data/correct_log.jsonl in the same format, with "source": "game".

Usage (WSL; the game starts it by itself if it is not running):
  python -m probe.correct_server [--port 18799] [--model ~/babyai-laya-ft/gotolocal-s0]
GET /seeds · /reset?seed=N · /step?action=turn%20left[&memo=1] · /end · /quit   (JSON replies)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import gymnasium as gym

from probe.correct_loop import ENV_ID, MEMOS, NAME_TO_ACT, bot_choice, default_seeds, failure_note
from probe.laya_model import Chooser, OnnxChooser
from probe.laya_rows import state_text
from probe.obs_text import obs_to_text
from probe.text_stats import categorize


class Session:
    def __init__(self, chooser: Chooser, log_path: str):
        self.chooser, self.log_path = chooser, log_path
        self.env = None
        self.rows: list[dict] = []
        self.result = None

    # ---- episode
    def reset(self, seed: int) -> dict:
        if 20000 <= seed < 20300:
            raise ValueError("20000-20299 are reserved for the final check (README)")
        self.end("skipped")
        self.env = gym.make(ENV_ID)
        self.obs, _ = self.env.reset(seed=seed)
        self.seed, self.rows, self.result = seed, [], None
        u = self.env.unwrapped
        d = u.instrs.desc
        self.target = {"type": d.type, "color": d.color}
        objs = []
        for x in range(u.width):
            for y in range(u.height):
                c = u.grid.get(x, y)
                if c is not None and c.type != "wall":
                    objs.append({"x": x, "y": y, "type": c.type, "color": c.color})
        self.room = {"seed": seed, "mission": self.obs["mission"], "width": u.width, "height": u.height,
                     "objects": objs, "max_steps": u.max_steps, "note": failure_note(seed),
                     "target": {**self.target, "positions": [[int(p[0]), int(p[1])] for p in d.obj_poss]}}
        self._decide()
        return self.state()

    def _decide(self) -> None:
        text = obs_to_text(self.obs["image"], self.obs["direction"])
        (c, probs), = self.chooser.choose_batch([text], [self.obs["mission"]])
        self.text, self.choice, self.probs = text, c, probs
        self.bot = bot_choice(self.env)

    def step(self, action: str, memo: str | None) -> dict:
        if self.env is None or self.result is not None:
            return self.state()
        u = self.env.unwrapped
        d = u.instrs.desc
        row = {"seed": self.seed, "step": len(self.rows), "mission": self.obs["mission"],
               "input": state_text(self.text, self.obs["mission"]), "probs": self.probs,
               "model_choice": self.choice, "bot_choice": self.bot, "memo": None,
               "target_visible": not categorize({"image": self.obs["image"], "target": self.target,
                                                 "n_matching": len(d.obj_poss)})["target_unseen"],
               "taken": action, "corrected": action != self.choice, "source": "game"}
        if memo in MEMOS:
            row["memo"] = {"code": int(memo), "label": MEMOS[memo]}
        self.rows.append(row)
        self.obs, r, term, trunc, _ = self.env.step(NAME_TO_ACT[action])
        if term or trunc:
            self.end("success" if term and r > 0 else "timeout")
        else:
            self._decide()
        return self.state()

    def end(self, result: str) -> None:
        if self.env is None or self.result is not None:
            return
        self.result = result
        now = datetime.datetime.now().isoformat(timespec="seconds")
        pathlib.Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as log:
            for r in self.rows:
                r["episode_result"], r["logged_at"] = result, now
                log.write(json.dumps(r, ensure_ascii=False) + "\n")

    def state(self) -> dict:
        if self.env is None:
            return {"ok": True, "room": None}
        u = self.env.unwrapped
        s = {"ok": True, "room": self.room, "x": int(u.agent_pos[0]), "y": int(u.agent_pos[1]),
             "dir": int(u.agent_dir), "step": len(self.rows), "result": self.result,
             "corrections": sum(r["corrected"] for r in self.rows),
             "memos": sum(r["memo"] is not None for r in self.rows)}
        if self.result is None:
            s.update({"input": state_text(self.text, self.obs["mission"]), "probs": self.probs,
                      "choice": self.choice, "bot": self.bot})
        return s


def _exit_with_parent(pid: int) -> None:
    """The game may end without sending /quit (crash, kill, scripted --shot run); don't outlive it."""
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if h:
        k32.WaitForSingleObject(h, 0xFFFFFFFF)
    os._exit(0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18799)
    ap.add_argument("--model", default=os.path.expanduser("~/babyai-laya-ft/gotolocal-s0"))
    ap.add_argument("--log", default="data/correct_log.jsonl")
    ap.add_argument("--onnx", default=None, help="run this ONNX export on the CPU instead of the PyTorch checkpoint")
    ap.add_argument("--root", default=None, help="folder holding reports/stage3_5 (the packaged server's own folder)")
    ap.add_argument("--parent-pid", type=int, default=0, help="Windows: exit when this process (the game) ends")
    a = ap.parse_args()
    if a.root:
        os.chdir(a.root)
    if a.parent_pid and os.name == "nt":
        threading.Thread(target=_exit_with_parent, args=(a.parent_pid,), daemon=True).start()
    sess = Session(OnnxChooser(a.model, a.onnx) if a.onnx else Chooser(a.model), a.log)
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            stop = False
            try:
                with lock:
                    if url.path == "/seeds":
                        body = {"ok": True, "seeds": [{"seed": s, "note": failure_note(s)} for s in default_seeds()],
                                "model": a.model, "log": a.log}
                    elif url.path == "/reset":
                        body = sess.reset(int(q["seed"]))
                    elif url.path == "/step":
                        if q.get("action") not in NAME_TO_ACT:
                            raise ValueError(f"bad action {q.get('action')!r}")
                        body = sess.step(q["action"], q.get("memo"))
                    elif url.path == "/end":
                        sess.end("skipped")
                        body = sess.state()
                    elif url.path == "/quit":
                        sess.end("quit")
                        body, stop = {"ok": True}, True
                    else:
                        raise ValueError("unknown path")
            except Exception as ex:  # noqa: BLE001
                body = {"ok": False, "error": f"{type(ex).__name__}: {ex}"}
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            if stop:
                threading.Thread(target=srv.shutdown, daemon=True).start()

    srv = HTTPServer(("127.0.0.1", a.port), H)
    print(f"correct_server ready on 127.0.0.1:{a.port} (model {a.model}, log {a.log})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
