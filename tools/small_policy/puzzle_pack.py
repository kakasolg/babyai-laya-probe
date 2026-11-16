"""Build godot/data/puzzle_rooms_l1.json: rooms where the level 1 autopilot stops by itself and 1-4 single moves by the
driver ("nudges") are enough, with the fewest nudges, one best answer, and for each level the places from which that
level's autopilot gets home alone ("lit"). See godot/drive/PUZZLE.md for the rules this file follows.

Puzzle rules (must be the same in the game):
  - the autopilot never drives forward into a blocked cell: it takes the better-scoring of the two turns instead;
  - it stops when it is about to act from a (x, y, heading) it has already acted from in this room;
  - the driver then makes exactly one move (turn left, turn right, or forward if the cell ahead is free);
    the autopilot's record of where it has acted is kept, and it drives on;
  - 64 turns in all (autopilot moves + nudges).
Every room is checked twice, with float32 and float64 arithmetic; a room is dropped if the two disagree anywhere."""
import sys, os, json, random, collections, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gd_mirror as G
from model import Policy
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
LIMIT, MAX_NUDGES, N_ROOMS, SEED = 64, 4, 300, 20261115

class Pilot:
    def __init__(s, level, double):
        d = json.load(open(os.path.join(ROOT, "godot", "data", "policy_l%d.json" % level)))
        s.m = Policy(d["ch"], d["hid"]); sd = s.m.state_dict()
        for k, v in d["tensors"].items(): sd[k] = torch.tensor(v["data"], dtype=torch.float32).reshape(sd[k].shape)
        s.m.load_state_dict(sd); s.m.eval(); s.dt = torch.float64 if double else torch.float32
        if double: s.m.double()
        s.cache = {}
    def choose(s, ep, pos, d):
        """the autopilot's move at this place: best score, forward left out when the cell ahead is blocked"""
        v = G.view(ep, pos, d); key = (tuple(v), ep["target"]["color"], ep["target"]["type"])
        if key not in s.cache:
            im = torch.tensor(v).reshape(1, 7, 7, 2); im = torch.cat([im, torch.zeros(1, 7, 7, 1, dtype=torch.long)], -1)
            with torch.no_grad():
                s.cache[key] = s.m(im, torch.tensor([G.COLOR_IDX[ep["target"]["color"]]]), torch.tensor([G.KIND_IDX[ep["target"]["type"]]]))[0].tolist()
        sc = s.cache[key]; order = sorted(range(3), key=lambda a: -sc[a])
        if not ahead_free(ep, pos, d): order = [a for a in order if a != 2]
        return order[0]

def ahead(pos, d): return (pos[0] + G.DIR_VEC[d][0], pos[1] + G.DIR_VEC[d][1])
def ahead_free(ep, pos, d): return G.free(ep, *ahead(pos, d))
def done(ep, pos, d): return G.is_target(ep, *ahead(pos, d))
def step(ep, pos, d, a):
    if a == 0: return pos, (d + 3) % 4
    if a == 1: return pos, (d + 1) % 4
    return (ahead(pos, d) if ahead_free(ep, pos, d) else pos), d
def auto(p, ep, pos, d, acted, t):
    """drive until done / stuck / out of turns; `acted` (set of (pos, heading)) is updated"""
    while t < LIMIT:
        if done(ep, pos, d): return "done", pos, d, t
        if (pos, d) in acted: return "stuck", pos, d, t
        acted.add((pos, d)); pos, d = step(ep, pos, d, p.choose(ep, pos, d)); t += 1
    return ("done" if done(ep, pos, d) else "out"), pos, d, t
def solve(p, ep, pos, d, acted, t, budget):
    """fewest nudges (ties: fewer turns) → (nudges, turns, [nudge actions]); None if more than `budget` are needed"""
    st, pos, d, t = auto(p, ep, pos, d, acted, t)
    if st == "done": return (0, t, [])
    if st == "out" or budget == 0 or t + 1 >= LIMIT: return None
    best = None
    for a in ([0, 1, 2] if ahead_free(ep, pos, d) else [0, 1]):
        p2, d2 = step(ep, pos, d, a); r = solve(p, ep, p2, d2, set(acted), t + 1, budget - 1)
        if r is not None and (best is None or (r[0] + 1, r[1]) < best[:2]): best = (r[0] + 1, r[1], [a] + r[2])
    return best
def best(p, ep):
    s = (ep["start"]["x"], ep["start"]["y"]); d = ep["start"]["dir"]
    for b in range(MAX_NUDGES + 1):
        r = solve(p, ep, s, d, set(), 0, b)
        if r is not None: return r
    return None
def lit(p, ep):
    """36 numbers, cell (x, y) at index (y-1)*6 + (x-1): bit h set = from this cell facing heading h the autopilot gets home alone"""
    out = [0] * 36
    for y in range(1, 7):
        for x in range(1, 7):
            if G.free(ep, x, y):
                out[(y - 1) * 6 + (x - 1)] = sum(1 << h for h in range(4) if auto(p, ep, (x, y), h, set(), 0)[0] == "done")
    return out

if __name__ == "__main__":
    P = {(lv, dbl): Pilot(lv, dbl) for lv in (1, 2, 3) for dbl in (False, True)}
    rng = random.Random(SEED); rooms = []; made = 0; C = collections.Counter()
    while len(rooms) < N_ROOMS:
        ep = G.make_room(rng, rid=made); made += 1
        r = best(P[1, False], ep)
        if r is None: C["5 or more nudges (left out)"] += 1; continue
        if r[0] == 0: C["autopilot alone (left out)"] += 1; continue
        l32 = {lv: lit(P[lv, False], ep) for lv in (1, 2, 3)}
        if best(P[1, True], ep) != r or any(lit(P[lv, True], ep) != l32[lv] for lv in (1, 2, 3)):
            C["float32 / float64 disagree (left out)"] += 1; continue
        C["%d nudge(s)" % r[0]] += 1
        ep.update({"generated": True, "nudge_par": r[0], "nudge_turns": r[1], "nudge_solution": r[2], "lit": {str(lv): l32[lv] for lv in (1, 2, 3)}})
        rooms.append(ep)
    rooms.sort(key=lambda e: (e["nudge_par"], e["nudge_turns"]))
    for i, e in enumerate(rooms): e["seed"] = "p%03d" % (i + 1)
    share = {lv: sum(bin(v).count("1") for e in rooms for v in e["lit"][str(lv)]) / sum(4 * sum(G.free(e, x, y) for x in range(1, 7) for y in range(1, 7)) for e in rooms) for lv in (1, 2, 3)}
    out = {"what": "rooms where the level 1 autopilot stops by itself and 1-4 single moves by the driver are enough; see godot/drive/PUZZLE.md",
           "level": 1, "turn_limit": LIMIT, "rng_seed": SEED, "rooms_tried": made, "counts": dict(C),
           "lit_share": {str(k): round(v, 4) for k, v in share.items()}, "rooms": rooms}
    path = os.path.join(ROOT, "godot", "data", "puzzle_rooms_l1.json")
    json.dump(out, open(path, "w"), separators=(",", ":"))
    print("rooms tried", made, dict(C)); print("lit share", out["lit_share"]); print(os.path.getsize(path), "bytes")
