"""Partial observation (7x7x3) -> short English text, relative to the agent.

MiniGrid encodes the view as image[i, j] = (object, color, state), i = column, j = row.
The agent sits at (3, 6) facing "up" (decreasing j), so for a cell (i, j):
  ahead = 6 - j, left = 3 - i (if i < 3), right = i - 3 (if i > 3).
Checked against env.get_view_coords() in probe/measure_env.py.

Text rules (see README "관측 → 글"):
  * line 1  "facing: <east|south|west|north>"  (obs["direction"])
  * one line per visible non-wall object, nearest first:
      "<color> <type>: 2 ahead, 1 left"   (zero parts dropped; "1 ahead" = right in front)
    no object visible -> "objects: none in view"
  * last line: nearest wall on each of the three straight lines from the agent
      "walls: 3 ahead, 1 left"  (a line with no visible wall is dropped;
       no wall on any line -> "walls: none in line")
Empty and unseen cells are never written. The mission is NOT used here.
"""
from __future__ import annotations

import numpy as np
from minigrid.core.constants import COLOR_TO_IDX, OBJECT_TO_IDX

IDX_TO_OBJECT = {v: k for k, v in OBJECT_TO_IDX.items()}
IDX_TO_COLOR = {v: k for k, v in COLOR_TO_IDX.items()}
DIRS = ["east", "south", "west", "north"]

# The three choices; MiniGrid action ids.
ACTIONS = {0: "turn left", 1: "turn right", 2: "forward"}
CHOICES = list(ACTIONS.values())

AX, AY = 3, 6  # agent cell in the view
_SKIP = {OBJECT_TO_IDX["unseen"], OBJECT_TO_IDX["empty"], OBJECT_TO_IDX["wall"], OBJECT_TO_IDX["agent"]}
_WALL = OBJECT_TO_IDX["wall"]


def rel(i: int, j: int) -> tuple[int, int]:
    """(ahead, side) with side < 0 = left, > 0 = right."""
    return AY - j, i - AX


def rel_text(ahead: int, side: int) -> str:
    parts = []
    if ahead:
        parts.append(f"{ahead} ahead")
    if side:
        parts.append(f"{abs(side)} {'left' if side < 0 else 'right'}")
    return ", ".join(parts)


def _nearest_wall(img: np.ndarray, cells) -> int | None:
    for n, (i, j) in enumerate(cells, start=1):
        if img[i, j, 0] == _WALL:
            return n
    return None


def obs_to_text(image, direction: int) -> str:
    img = np.asarray(image)
    lines = [f"facing: {DIRS[int(direction)]}"]

    objs = []
    for i in range(7):
        for j in range(7):
            o = int(img[i, j, 0])
            if o in _SKIP or (i, j) == (AX, AY):
                continue
            ahead, side = rel(i, j)
            name = f"{IDX_TO_COLOR[int(img[i, j, 1])]} {IDX_TO_OBJECT[o]}"
            objs.append((ahead + abs(side), ahead, side, name))
    if objs:
        for _, ahead, side, name in sorted(objs):
            lines.append(f"{name}: {rel_text(ahead, side)}")
    else:
        lines.append("objects: none in view")

    walls = []
    for label, cells in (
        ("ahead", [(AX, AY - k) for k in range(1, 7)]),
        ("left", [(AX - k, AY) for k in range(1, 4)]),
        ("right", [(AX + k, AY) for k in range(1, 4)]),
    ):
        n = _nearest_wall(img, cells)
        if n is not None:
            walls.append(f"{n} {label}")
    lines.append("walls: " + (", ".join(walls) if walls else "none in line"))
    return "\n".join(lines)
