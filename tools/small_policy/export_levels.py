"""Train the three autopilot levels and write everything godot/drive needs into an output folder:
    python export_levels.py <out_dir>        (needs torch, minigrid, numpy; CPU, a few minutes)
  policy_l{1,2,3}.json       weights as JSON (floats rounded to 6 significant digits)
  policy_l{1,2,3}_test.json  200 views with the PyTorch scores and chosen action
  drive_view_test.json       150 (room, position, heading) → view cases from the MiniGrid-checked reference
  levels_results.json        how each level did
Level n is the same 66,787-parameter network trained on the expert bot's demonstrations from seeds 0-999 / 0-2999 / 0-9999."""
import sys, os, json, random, numpy as np, torch
from levels import demos, train, plain, quiet, env, U, mis, BabyAIBot
import gd_mirror as G, reference_numpy as R
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
vec = []
with quiet():
    rng = np.random.default_rng(0)
    for s in range(50000, 50040):
        obs, _ = env.reset(seed=s); d = False; bot = BabyAIBot(U)
        while not d and len(vec) < 220:
            c, t = mis(obs); vec.append({"image": obs["image"].tolist(), "color": c, "kind": t})
            a = int(bot.replan()) if rng.random() < 0.6 else int(rng.integers(3)); a = min(a, 2); obs, _, te, tr, _ = env.step(a); d = te or tr
vec = vec[:200]
im = torch.tensor([v["image"] for v in vec], dtype=torch.long); cc = torch.tensor([v["color"] for v in vec]); kk = torch.tensor([v["kind"] for v in vec])
res = {}; nets = {}
for lvl, n in ((1, 1000), (2, 3000), (3, 10000)):
    D = demos(range(n)); net = train(D, 16, 64); nets[lvl] = net
    res[f"level{lvl}"] = {"demo_episodes": len({r[4] for r in D}), "demo_seeds": f"0-{n - 1}", "ch": 16, "hid": 64,
                          "parameters": sum(p.numel() for p in net.parameters()), "dev_10000_10299_autopilot_alone_solved": plain(net, range(10000, 10300))}
for lvl, net in nets.items():       # the fresh rooms are looked at only after all three networks are fixed
    r = res[f"level{lvl}"]; r["fresh_41000_41299_autopilot_alone_solved"] = plain(net, range(41000, 41300))
    json.dump({"what": "small instruction-conditioned CNN, behaviour-cloned from MiniGrid's BabyAI expert bot on GoToLocal. Not Laya.", "level": lvl,
               "demo_episodes": r["demo_episodes"], "solved_alone_of_300_fresh_rooms": r["fresh_41000_41299_autopilot_alone_solved"], "ch": 16, "hid": 64,
               "actions": ["turn left", "turn right", "forward"],
               "tensors": {k: {"shape": list(v.shape), "data": [float("%.6g" % float(x)) for x in v.numpy().ravel()]} for k, v in net.state_dict().items()}},
              open(f"{out}/policy_l{lvl}.json", "w"), separators=(",", ":"))
    with torch.no_grad(): lg = net(im, cc, kk).numpy()
    json.dump([{"view": [c for i in range(7) for j in range(7) for c in v["image"][i][j][:2]], "color": v["color"], "kind": v["kind"],
                "logits": [round(float(x), 5) for x in lg[k]], "action": int(lg[k].argmax())} for k, v in enumerate(vec)],
              open(f"{out}/policy_l{lvl}_test.json", "w"), separators=(",", ":"))
    m = G.Net(f"{out}/policy_l{lvl}.json"); tv = json.load(open(f"{out}/policy_l{lvl}_test.json"))[:80]
    r["mirror_same_action_of_80"] = sum(int(np.argmax(m.scores(v["view"], v["color"], v["kind"])) == v["action"]) for v in tv)
rng = random.Random(3); cases = []; bad = 0; tot = 0
for rid in range(120):
    ep = G.make_room(rng, rid=rid); g = [[None] * 8 for _ in range(8)]
    for x in range(8):
        for y in range(8):
            c = G.cell_code(ep, x, y); g[x][y] = None if c == (1, 0) else c
    for x in range(1, 7):
        for y in range(1, 7):
            if g[x][y] is not None: continue
            for d in range(4):
                ref = R.egocentric_view(g, (x, y), d); flat = [c for i in range(7) for j in range(7) for c in ref[i][j][:2]]
                tot += 1; bad += G.view(ep, (x, y), d) != flat
                if rng.random() < 0.012 and len(cases) < 150: cases.append({"room": ep, "x": x, "y": y, "dir": d, "view": flat})
json.dump(cases, open(f"{out}/drive_view_test.json", "w"), separators=(",", ":"))
res["view_mirror_vs_reference"] = {"states": tot, "mismatches": bad}
json.dump(res, open(f"{out}/levels_results.json", "w"), indent=1); print(json.dumps(res, indent=1))
