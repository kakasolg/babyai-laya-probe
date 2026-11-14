"""Checkpoint paths and the model side of the boundary: choose(state_text, mission, choices) -> choice."""
from __future__ import annotations

import os

from huggingface_hub import snapshot_download
from laya.revisions import PINNED_REVISIONS

from probe.laya_rows import QID, question, state_text
from probe.obs_text import CHOICES

BASE_REPO = "convaiinnovations/laya"  # english
BASE_REV = PINNED_REVISIONS[BASE_REPO]  # 55cf4c4…
FT_ROOT = os.path.expanduser("~/babyai-laya-ft")  # outside the repo
MASK = "(hidden)"


def base_dir() -> str:
    """Pinned english checkpoint (no alias -> no silent 'latest main')."""
    return snapshot_download(BASE_REPO, revision=BASE_REV,
                             allow_patterns=["rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*"])


class Chooser:
    def __init__(self, path: str, device: str = "cuda"):
        import laya
        self.agent = laya.load(path, device=device)

    def choose_batch(self, texts, missions, choices=CHOICES, mask_mission=False):
        """-> list of (choice, probabilities dict)."""
        states = [state_text(t, MASK if mask_mission else m) for t, m in zip(texts, missions)]
        if not states:
            return []
        res = self.agent.predict_batch(states, question(choices), batch_size=128)
        out = []
        for r in res:
            ans = r["answers"][QID]
            probs = ans.get("probabilities") or {}
            ch = ans.get("choice")
            if ch not in choices and probs:  # defensive: abstain/invalid -> argmax
                ch = max(probs, key=probs.get)
            out.append((ch, probs))
        return out
