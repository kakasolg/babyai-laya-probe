"""Reference without torch or MiniGrid: (1) build the 7x7 egocentric view from a plain grid, (2) run the policy with numpy,
(3) the 'try an untried action on a repeated view' rule (R-reset). Port these three to the game.
A grid here is grid[x][y] = None (empty floor) or (object_idx, colour_idx); x grows right, y grows down, walls are (2, 5)."""
import json, numpy as np

UNSEEN, EMPTY, WALL = 0, 1, 2
OBJ = {"unseen": 0, "empty": 1, "wall": 2, "key": 5, "ball": 6, "box": 7}
COLOR = {"red": 0, "green": 1, "blue": 2, "purple": 3, "yellow": 4, "grey": 5}
KIND = {"ball": 0, "box": 1, "key": 2}                       # mission type index used by the policy
DIR_VEC = [(1, 0), (0, 1), (-1, 0), (0, -1)]                 # agent_dir 0 right, 1 down, 2 left, 3 up
LEFT, RIGHT, FORWARD = 0, 1, 2

def egocentric_view(grid, agent_pos, agent_dir, view=7):
    """→ image[i][j] = [object_idx, colour_idx, 0]; the agent sits at i = 3, j = 6 and looks toward j = 0.
    i grows to the agent's right. Cells outside the grid or hidden behind walls are [0, 0, 0]; empty floor is [1, 0, 0]."""
    W, H = len(grid), len(grid[0]); ax, ay = agent_pos; h = view // 2
    if agent_dir == 0:   tx, ty = ax, ay - h
    elif agent_dir == 1: tx, ty = ax - h, ay
    elif agent_dir == 2: tx, ty = ax - view + 1, ay - h
    else:                tx, ty = ax - h, ay - view + 1
    # slice in world orientation: out-of-bounds cells count as walls
    sl = [[(grid[tx + i][ty + j] if 0 <= tx + i < W and 0 <= ty + j < H else (WALL, 5)) for j in range(view)] for i in range(view)]
    for _ in range(agent_dir + 1):                                           # rotate left (counter-clockwise) agent_dir + 1 times
        sl = [[sl[view - 1 - j][i] for j in range(view)] for i in range(view)]
    sl[h][view - 1] = None                                                   # the agent's own cell (nothing carried)
    # visibility: same sweep as MiniGrid Grid.process_vis — light spreads from the agent, walls stop it
    mask = [[False] * view for _ in range(view)]; mask[h][view - 1] = True
    see = lambda c: c is None or c[0] != WALL
    for j in reversed(range(view)):
        for i in range(view - 1):
            if mask[i][j] and see(sl[i][j]):
                mask[i + 1][j] = True
                if j > 0: mask[i + 1][j - 1] = True; mask[i][j - 1] = True
        for i in reversed(range(1, view)):
            if mask[i][j] and see(sl[i][j]):
                mask[i - 1][j] = True
                if j > 0: mask[i - 1][j - 1] = True; mask[i][j - 1] = True
    return [[([UNSEEN, 0, 0] if not mask[i][j] else [EMPTY, 0, 0] if sl[i][j] is None else [sl[i][j][0], sl[i][j][1], 0]) for j in range(view)] for i in range(view)]

class Weights:
    def __init__(self, stem):
        man = json.load(open(stem + ".json")); raw = np.fromfile(stem + ".bin", dtype="<f4")
        self.meta = man; self.t = {n: raw[o:o + int(np.prod(s))].reshape(s) for n, (s, o) in man["tensors"].items()}

def conv3x3(x, w, b):
    """x [C, 7, 7], w [O, C, 3, 3], zero padding 1 → [O, 7, 7]"""
    C, Hh, Ww = x.shape; p = np.zeros((C, Hh + 2, Ww + 2), np.float32); p[:, 1:-1, 1:-1] = x
    out = np.zeros((w.shape[0], Hh, Ww), np.float32)
    for di in range(3):
        for dj in range(3):
            out += np.einsum("oc,chw->ohw", w[:, :, di, dj], p[:, di:di + Hh, dj:dj + Ww])
    return out + b[:, None, None]

def logits(W, image, color, kind):
    """One observation → 3 logits. image [7][7][3] ints, color 0..5, kind 0..2."""
    t = W.t; im = np.asarray(image)
    x = np.concatenate([t["eo.weight"][im[:, :, 0]], t["ec.weight"][im[:, :, 1]]], -1).transpose(2, 0, 1)   # [32, i, j]
    x = np.concatenate([x, t["xy"][0]], 0)                                                                    # [34, 7, 7]
    m = np.concatenate([t["mc.weight"][color], t["mt.weight"][kind]])                                         # [64]
    for c, f in (("c1", "f1"), ("c2", "f2"), ("c3", "f3")):
        gb = t[f + ".weight"] @ m + t[f + ".bias"]; ch = len(gb) // 2
        x = conv3x3(x, t[c + ".weight"], t[c + ".bias"])
        x = np.maximum(0, x * (1 + gb[:ch, None, None]) + gb[ch:, None, None])
    hdn = np.maximum(0, t["h1.weight"] @ x.reshape(-1) + t["h1.bias"])
    return t["h2.weight"] @ hdn + t["h2.bias"]

class RuleRReset:
    """Per episode: remember which actions were already taken from each exact view (+ heading). On a repeated view take the
    best-scoring action not yet tried there; when all three were tried, forget that view's record and continue."""
    def __init__(self): self.tried = {}
    def choose(self, scores, image, agent_dir):
        key = (json.dumps(image), agent_dir); t = self.tried.setdefault(key, set())
        order = sorted(range(3), key=lambda a: -scores[a]); cand = [a for a in order if a not in t]
        if not cand: t.clear(); cand = order
        t.add(cand[0]); return cand[0]
