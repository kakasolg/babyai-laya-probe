"""Demo dump -> Laya finetune rows ({state, questions, expected}), and the model/env boundary.

The only thing the model decides is `choose(state_text, mission, choices) -> choice`.
Everything else (env stepping, obs->text) stays outside.
"""
from __future__ import annotations

import json

from probe.obs_text import CHOICES

QID = "action"
INSTRUCTIONS = ("A grid agent must reach the object named in the mission. "
                "Pick its next action from what it can see now.")
CRITERIA = {
    "turn left": "rotate 90 degrees left, stay in place",
    "turn right": "rotate 90 degrees right, stay in place",
    "forward": "move one cell ahead",
}
assert list(CRITERIA) == CHOICES

# PickupDist (stage 8, MoKa 11-15 12:09): only the goal sentence and the fourth option differ from GoToLocal.
INSTRUCTIONS_PICKUP = ("A grid agent must pick up an object that matches the mission. "
                       "Pick its next action from what it can see now.")
CRITERIA_PICKUP = {**CRITERIA, "pick up": "pick up the object in the cell directly ahead"}
CHOICES_PICKUP = list(CRITERIA_PICKUP)  # turn left / turn right / forward / pick up


def question_pickup(choices=CHOICES_PICKUP) -> dict:
    return {QID: {"type": "choice", "instructions": INSTRUCTIONS_PICKUP,
                  "criteria": {c: CRITERIA_PICKUP[c] for c in choices}}}


def state_text(text: str, mission: str) -> str:
    return f"mission: {mission}\n{text}"


def question(choices=CHOICES) -> dict:
    return {QID: {"type": "choice", "instructions": INSTRUCTIONS,
                  "criteria": {c: CRITERIA[c] for c in choices}}}


def to_row(demo: dict) -> dict:
    return {"state": state_text(demo["text"], demo["mission"]), "questions": question(),
            "expected": {QID: demo["action_name"]}}


def write_rows(dump_path: str, out_path: str) -> int:
    n = 0
    with open(dump_path, encoding="utf-8") as f, open(out_path, "w", encoding="utf-8") as g:
        for line in f:
            g.write(json.dumps(to_row(json.loads(line))) + "\n")
            n += 1
    return n
