import gymnasium as gym, minigrid, numpy as np, torch, torch.nn as nn, io, contextlib, json, time, sys
from minigrid.utils.baby_ai_bot import BabyAIBot
torch.set_num_threads(1)
COL=["red","green","blue","purple","yellow","grey"]; TYP=["ball","box","key"]
quiet=lambda: contextlib.redirect_stdout(io.StringIO())
def half(w): return next((COL.index(x) for x in w if x in COL),6), next((TYP.index(x) for x in w if x in TYP),3)
def mis(m):
    w=m.split()
    if "next" in w: i=w.index("next"); return (*half(w[:i]),*half(w[i:]))
    return (*half(w),6,3)
class Policy(nn.Module):
    def __init__(s,nact,ch=16,hid=64):
        super().__init__(); s.eo=nn.Embedding(11,16); s.ec=nn.Embedding(6,16); s.mc=nn.Embedding(7,16); s.mt=nn.Embedding(4,16)
        yy,xx=torch.meshgrid(torch.linspace(-1,1,7),torch.linspace(-1,1,7),indexing="ij"); s.register_buffer("xy",torch.stack([xx,yy])[None])
        s.c=nn.ModuleList([nn.Conv2d(34,ch,3,padding=1),nn.Conv2d(ch,ch,3,padding=1),nn.Conv2d(ch,ch,3,padding=1)]); s.f=nn.ModuleList([nn.Linear(64,2*ch) for _ in range(3)])
        s.h1=nn.Linear(ch*49,hid); s.h2=nn.Linear(hid,nact)
    def forward(s,im,m):
        x=torch.cat([s.eo(im[...,0]),s.ec(im[...,1])],-1).permute(0,3,1,2); x=torch.cat([x,s.xy.expand(x.shape[0],-1,-1,-1)],1)
        mv=torch.cat([s.mc(m[:,0]),s.mt(m[:,1]),s.mc(m[:,2]),s.mt(m[:,3])],1)
        for c,f in zip(s.c,s.f):
            g,b=f(mv).chunk(2,1); x=torch.relu(c(x)*(1+g[:,:,None,None])+b[:,:,None,None])
        return s.h2(torch.relu(s.h1(x.flatten(1))))
def demos(env,seeds,nact):
    U=env.unwrapped; E=[]
    with quiet():
        for sd in seeds:
            obs,_=env.reset(seed=sd); bot=BabyAIBot(U); d=False; m=mis(obs["mission"]); rows=[]; bad=False
            while not d:
                a=int(bot.replan()); bad|=a>=nact; rows.append((obs["image"].copy(),m,a,sd)); obs,r,te,tr,_=env.step(a); d=te or tr
            if not bad and te and r>0: E.append(rows)
    return E
def train(D,nact,seed,epochs=15):
    torch.manual_seed(seed); rng=np.random.default_rng(seed); eps=sorted({r[3] for r in D}); val=set(rng.choice(eps,max(1,len(eps)//20),replace=False).tolist())
    T=lambda rs:(torch.tensor(np.array([r[0] for r in rs]),dtype=torch.long),torch.tensor([r[1] for r in rs]),torch.tensor([r[2] for r in rs]))
    tr=T([r for r in D if r[3] not in val]); va=T([r for r in D if r[3] in val]); net=Policy(nact); opt=torch.optim.AdamW(net.parameters(),1e-3,weight_decay=1e-2); best=(-1,None); n=len(tr[0])
    for ep in range(epochs):
        net.train(); perm=torch.randperm(n)
        for i in range(0,n,128):
            idx=perm[i:i+128]; loss=nn.functional.cross_entropy(net(tr[0][idx],tr[1][idx]),tr[2][idx]); opt.zero_grad(); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad(): acc=(net(va[0],va[1]).argmax(1)==va[2]).float().mean().item()
        if acc>=best[0]: best=(acc,{k:v.clone() for k,v in net.state_dict().items()})
    net.load_state_dict(best[1]); net.eval(); return net
def run(env,net,seeds,rule,nact):
    out=[]
    with quiet(), torch.no_grad():
        for sd in seeds:
            obs,_=env.reset(seed=sd); m=torch.tensor([mis(obs["mission"])]); tried={}; n=0; d=False
            while not d:
                order=net(torch.tensor(obs["image"],dtype=torch.long)[None],m)[0].argsort(descending=True).tolist(); a=order[0]
                if rule:
                    k=(obs["image"].tobytes(),int(obs["direction"])); t=tried.setdefault(k,set()); cand=[x for x in order if x not in t]
                    if not cand: t.clear(); cand=order
                    a=cand[0]; t.add(a)
                obs,r,te,tr,_=env.step(a); n+=1; d=te or tr
            out.append((bool(te and r>0),n))
    return out
def botrun(env,seeds):
    U=env.unwrapped; out=[]
    with quiet():
        for sd in seeds:
            obs,_=env.reset(seed=sd); bot=BabyAIBot(U); n=0; d=False
            while not d: obs,r,te,tr,_=env.step(int(bot.replan())); n+=1; d=te or tr
            out.append(n)
    return out
TASK={"goto":("BabyAI-GoToLocal-v0",3),"putnext":("BabyAI-PutNextLocal-v0",5)}
if __name__=="__main__":
    task=sys.argv[1]; eid,nact=TASK[task]; env=gym.make(eid); EV=range(10000,10300)
    E=demos(env,range(10000),nact); bs=botrun(env,EV)
    print(json.dumps({"task":task,"episodes_kept_of_10000":len(E),"params":sum(p.numel() for p in Policy(nact).parameters()),"bot_mean_steps":round(float(np.mean(bs)),2)}),flush=True)
    kept={r[0][3] for r in E}
    for N in (100,500,1000,5000,10000):
        D=[row for ep in E if ep[0][3]<N for row in ep]
        for seed in (0,1,2):
            t=time.time(); net=train(D,nact,seed); res={"task":task,"N":N,"seed":seed,"episodes":sum(1 for ep in E if ep[0][3]<N),"rows":len(D)}
            base=None
            for rl,key in ((False,"alone"),(True,"rule")):
                r=run(env,net,EV,rl,nact); res[key]=int(sum(x[0] for x in r)); res[key+"_2x"]=int(sum(x[0] and x[1]<=2*b for x,b in zip(r,bs)))
                if not rl: base=r
                else: res["broken"]=int(sum(a[0] and not b[0] for a,b in zip(base,r))); res["saved"]=int(sum((not a[0]) and b[0] for a,b in zip(base,r)))
            res["secs"]=round(time.time()-t); print(json.dumps(res),flush=True)
