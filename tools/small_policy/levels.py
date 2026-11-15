"""Pick autopilot levels for the game: train small nets, then simulate the game loop
(autopilot drives; when it revisits a view it has already driven through it stops and a stand-in driver — the expert bot —
makes one move; then the autopilot resumes)."""
import gymnasium as gym, minigrid, numpy as np, torch, torch.nn as nn, io, contextlib, json, time, sys, os
from minigrid.utils.baby_ai_bot import BabyAIBot
from model import Policy
torch.set_num_threads(4)
COL=["red","green","blue","purple","yellow","grey"]; TYP=["ball","box","key"]
env=gym.make("BabyAI-GoToLocal-v0"); U=env.unwrapped
mis=lambda obs:(COL.index(obs["mission"].split()[-2]),TYP.index(obs["mission"].split()[-1]))
quiet=lambda: contextlib.redirect_stdout(io.StringIO())
def demos(seeds):
    D=[]
    with quiet():
        for s in seeds:
            obs,_=env.reset(seed=s); bot=BabyAIBot(U); rows=[]; d=False; bad=False
            while not d:
                a=int(bot.replan()); bad|=a>2; c,t=mis(obs); rows.append((obs["image"].copy(),c,t,a,s)); obs,_,te,tr,_=env.step(a); d=te or tr
            if not bad: D+=rows
    return D
def train(D,ch,hid,seed=0,epochs=15):
    torch.manual_seed(seed); rng=np.random.default_rng(seed); eps=sorted({r[4] for r in D}); val=set(rng.choice(eps,max(1,len(eps)//20),replace=False).tolist())
    T=lambda rs:(torch.tensor(np.array([r[0] for r in rs]),dtype=torch.long),torch.tensor([r[1] for r in rs]),torch.tensor([r[2] for r in rs]),torch.tensor([r[3] for r in rs]))
    tr=T([r for r in D if r[4] not in val]); va=T([r for r in D if r[4] in val]); net=Policy(ch,hid); opt=torch.optim.AdamW(net.parameters(),1e-3,weight_decay=1e-2); best=(0,None); n=len(tr[0])
    for ep in range(epochs):
        net.train(); perm=torch.randperm(n)
        for i in range(0,n,128):
            idx=perm[i:i+128]; loss=nn.functional.cross_entropy(net(tr[0][idx],tr[1][idx],tr[2][idx]),tr[3][idx]); opt.zero_grad(); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad(): acc=(net(*va[:3]).argmax(1)==va[3]).float().mean().item()
        if acc>=best[0]: best=(acc,{k:v.clone() for k,v in net.state_dict().items()})
    net.load_state_dict(best[1]); net.eval(); return net
def game(net,seeds):
    """→ per room: (solved, turns, takeovers)"""
    out=[]
    with quiet(), torch.no_grad():
        for s in seeds:
            obs,_=env.reset(seed=s); seen=set(); n=0; take=0; ok=False; d=False
            while not d:
                k=(obs["image"].tobytes(),int(obs["direction"]))
                if k in seen:                                   # autopilot is looping → the driver makes one move
                    a=min(int(BabyAIBot(U).replan()),2); take+=1; seen=set()
                else:
                    seen.add(k); c,t=mis(obs); a=int(net(torch.tensor(obs["image"],dtype=torch.long)[None],torch.tensor([c]),torch.tensor([t]))[0].argmax())
                obs,r,te,tr,_=env.step(a); n+=1; d=te or tr; ok=bool(te and r>0)
            out.append((ok,n,take))
    return out
def plain(net,seeds):
    ok=0
    with quiet(), torch.no_grad():
        for s in seeds:
            obs,_=env.reset(seed=s); d=False
            while not d:
                c,t=mis(obs); a=int(net(torch.tensor(obs["image"],dtype=torch.long)[None],torch.tensor([c]),torch.tensor([t]))[0].argmax()); obs,r,te,tr,_=env.step(a); d=te or tr
            ok+=bool(te and r>0)
    return ok
def describe(net,seeds):
    g=game(net,seeds); n=len(g)
    return {"autopilot_alone_solved":plain(net,seeds),"rooms":n,"with_driver_solved":sum(x[0] for x in g),"rooms_needing_takeover":sum(x[2]>0 for x in g),"takeovers_total":sum(x[2] for x in g),
            "max_takeovers_in_a_room":max(x[2] for x in g),"rooms_35_turns_or_more_or_failed":sum((x[1]>=35) or (not x[0]) for x in g),"mean_turns":round(float(np.mean([x[1] for x in g])),2)}
if __name__=="__main__":
    DEV=range(10000,10300); D1=demos(range(1000)); D10=demos(range(10000)); res={}
    for name,D,ch,hid in (("998 demos, ch16",D1,16,64),("998 demos, ch32",D1,32,64),("10k demos, ch16",D10,16,64),("10k demos, ch24",D10,24,64)):
        t=time.time(); net=train(D,ch,hid); torch.save(net.state_dict(),f"cand_{name.split()[0]}_{ch}.pt"); r=describe(net,DEV); r["parameters"]=sum(p.numel() for p in net.parameters()); r["train_s"]=round(time.time()-t); res[name]=r; print(name,json.dumps(r),flush=True)
    json.dump(res,open("levels_candidates.json","w"),indent=1)
