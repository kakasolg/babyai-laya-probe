"""The stage 14 rule variants (probe/stage14.py `Rule`, unchanged) on the small CNN from the 11b addendum."""
import sys, json, random, time, numpy as np, torch, gymnasium as gym, minigrid
from cnn_curve import Policy, demos, train, botrun, mis, quiet, TASK
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from probe.stage14 import Rule, RUNS, true_state
def run(env,net,seeds,variant,rseed,nact,bs):
    U=env.unwrapped; out=[]; occl=0; trig_n=0
    with quiet(), torch.no_grad():
        for sd in seeds:
            obs,_=env.reset(seed=sd); m=torch.tensor([mis(obs["mission"])]); n=0; d=False
            rule=Rule(variant, random.Random(f"{variant}-{rseed}-{sd}") if rseed is not None else None); seen_full=set(); iv=0
            while not d:
                order=[str(a) for a in net(torch.tensor(obs["image"],dtype=torch.long)[None],m)[0].argsort(descending=True).tolist()]
                agent,full=true_state(U)
                key=agent if variant=="V6" else (obs["image"].tobytes(),int(obs["direction"]))
                a,trig=rule.choose(order,key,[str(i) for i in range(nact)])
                if trig:
                    iv+=1
                    if variant=="V1" and full not in seen_full: occl+=1
                seen_full.add(full)
                obs,r,te,tr,_=env.step(int(a)); n+=1; d=te or tr
            out.append((bool(te and r>0),n)); trig_n+=iv
    return out,trig_n,occl
if __name__=="__main__":
    task=sys.argv[1]; eid,nact=TASK[task]; env=gym.make(eid); EV=range(10000,10300)
    E=demos(env,range(10000),nact); bs=botrun(env,EV)
    for N in (100,1000,10000):
        D=[row for ep in E if ep[0][3]<N for row in ep]
        for seed in (0,1,2):
            net=train(D,nact,seed); base=None
            for v,rs in RUNS:
                t=time.time(); r,trig,occl=run(env,net,EV,v,rs,nact,bs)
                if v=="V0": base=r
                res={"task":task,"N":N,"seed":seed,"variant":v,"rng":rs,"success":int(sum(x[0] for x in r)),"within_2x":int(sum(x[0] and x[1]<=2*b for x,b in zip(r,bs))),
                     "saved":int(sum((not a[0]) and b[0] for a,b in zip(base,r))),"broken":int(sum(a[0] and not b[0] for a,b in zip(base,r))),"rule_steps":trig,"occluded_rule_steps":occl if v=="V1" else None,"secs":round(time.time()-t)}
                print(json.dumps(res),flush=True)
