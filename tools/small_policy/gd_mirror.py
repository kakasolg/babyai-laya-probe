"""Line-by-line Python mirror of godot/drive/autopilot.gd and rooms.gd (flat arrays, same index arithmetic), used to
check the port's logic against reference_numpy and MiniGrid before it is run in Godot."""
import json, random, numpy as np
OBJ_IDX={"key":5,"ball":6,"box":7}; COLOR_IDX={"red":0,"green":1,"blue":2,"purple":3,"yellow":4,"grey":5}; KIND_IDX={"ball":0,"box":1,"key":2}
DIR_VEC=[(1,0),(0,1),(-1,0),(0,-1)]
def cell_code(ep,x,y):
    w,h=ep["width"],ep["height"]
    if x<=0 or y<=0 or x>=w-1 or y>=h-1: return (2,5)
    for o in ep["objects"]:
        if o["x"]==x and o["y"]==y: return (OBJ_IDX[o["type"]],COLOR_IDX[o["color"]])
    return (1,0)
def view(ep,pos,d):
    fwd=DIR_VEC[d]; right=DIR_VEC[(d+1)%4]; cells=[(1,0)]*49
    for i in range(7):
        for j in range(7):
            f=6-j; l=i-3; cells[i*7+j]=cell_code(ep,pos[0]+fwd[0]*f+right[0]*l,pos[1]+fwd[1]*f+right[1]*l)
    cells[3*7+6]=(1,0)
    mask=[False]*49; mask[3*7+6]=True
    for j in range(6,-1,-1):
        for i in range(0,6):
            if mask[i*7+j] and cells[i*7+j][0]!=2:
                mask[(i+1)*7+j]=True
                if j>0: mask[(i+1)*7+j-1]=True; mask[i*7+j-1]=True
        for i in range(6,0,-1):
            if mask[i*7+j] and cells[i*7+j][0]!=2:
                mask[(i-1)*7+j]=True
                if j>0: mask[(i-1)*7+j-1]=True; mask[i*7+j-1]=True
    out=[0]*98
    for p in range(49):
        if mask[p]: out[p*2]=cells[p][0]; out[p*2+1]=cells[p][1]
    return out
class Net:
    def __init__(s,path):
        d=json.load(open(path)); s.ch=d["ch"]; s.hid=d["hid"]; s.t={k:[float(x) for x in v["data"]] for k,v in d["tensors"].items()}
    def conv(s,x,cin,name):
        w=s.t[name+".weight"]; b=s.t[name+".bias"]; ch=s.ch; out=[0.0]*(ch*49)
        for o in range(ch):
            base=o*49
            for p in range(49): out[base+p]=b[o]
            for c in range(cin):
                wb=(o*cin+c)*9; xb=c*49
                for di in range(3):
                    for dj in range(3):
                        wv=w[wb+di*3+dj]
                        if wv==0.0: continue
                        i0=max(0,1-di); i1=min(7,8-di); j0=max(0,1-dj); j1=min(7,8-dj)
                        for i in range(i0,i1):
                            src=xb+(i+di-1)*7+(dj-1); dst=base+i*7
                            for j in range(j0,j1): out[dst+j]+=wv*x[src+j]
        return out
    def film(s,x,name,m):
        w=s.t[name+".weight"]; b=s.t[name+".bias"]; ch=s.ch
        for o in range(ch):
            g=b[o]; be=b[ch+o]
            for k in range(64): g+=w[o*64+k]*m[k]; be+=w[(ch+o)*64+k]*m[k]
            for p in range(49):
                v=x[o*49+p]*(1.0+g)+be; x[o*49+p]=v if v>0.0 else 0.0
        return x
    def scores(s,v,color,kind):
        t=s.t; x=[0.0]*(34*49)
        for p in range(49):
            ob=v[p*2]; co=v[p*2+1]
            for k in range(16): x[k*49+p]=t["eo.weight"][ob*16+k]; x[(16+k)*49+p]=t["ec.weight"][co*16+k]
            x[32*49+p]=t["xy"][p]; x[33*49+p]=t["xy"][49+p]
        m=[0.0]*64
        for k in range(32): m[k]=t["mc.weight"][color*32+k]; m[32+k]=t["mt.weight"][kind*32+k]
        x=s.film(s.conv(x,34,"c1"),"f1",m); x=s.film(s.conv(x,s.ch,"c2"),"f2",m); x=s.film(s.conv(x,s.ch,"c3"),"f3",m)
        n=s.ch*49; h=[0.0]*s.hid
        for a in range(s.hid):
            acc=t["h1.bias"][a]; wb=a*n
            for q in range(n): acc+=t["h1.weight"][wb+q]*x[q]
            h[a]=acc if acc>0.0 else 0.0
        out=[0.0]*3
        for a in range(3):
            acc=t["h2.bias"][a]
            for q in range(s.hid): acc+=t["h2.weight"][a*s.hid+q]*h[q]
            out[a]=acc
        return out
TYPES=["key","ball","box"]; COLORS=["red","green","blue","purple","yellow","grey"]
def is_target(ep,x,y): return any(p[0]==x and p[1]==y for p in ep["target"]["positions"])
def free(ep,x,y): return cell_code(ep,x,y)==(1,0)
def par(ep):
    """fewest moves (turn left / turn right / forward) until a matching object is directly ahead; -1 if impossible"""
    s=(ep["start"]["x"],ep["start"]["y"],ep["start"]["dir"]); seen={s}; q=[s]; depth=0
    while q:
        nq=[]
        for (x,y,d) in q:
            if is_target(ep,x+DIR_VEC[d][0],y+DIR_VEC[d][1]): return depth
            nx,ny=x+DIR_VEC[d][0],y+DIR_VEC[d][1]
            for st in ((x,y,(d+3)%4),(x,y,(d+1)%4),((nx,ny,d) if free(ep,nx,ny) else None)):
                if st is not None and st not in seen: seen.add(st); nq.append(st)
        q=nq; depth+=1
    return -1
def make_room(rng,size=8,n_objs=8,rid=0):
    while True:
        cells=[(x,y) for x in range(1,size-1) for y in range(1,size-1)]; rng.shuffle(cells); objs=[]
        for k in range(n_objs):
            x,y=cells.pop(); objs.append({"x":x,"y":y,"type":TYPES[rng.randrange(3)],"color":COLORS[rng.randrange(6)]})
        sx,sy=cells.pop(); t=objs[rng.randrange(n_objs)]
        pos=[[o["x"],o["y"]] for o in objs if o["type"]==t["type"] and o["color"]==t["color"]]
        ep={"seed":"r%d"%rid,"width":size,"height":size,"objects":objs,"target":{"type":t["type"],"color":t["color"],"positions":pos},
            "start":{"x":sx,"y":sy,"dir":rng.randrange(4)},"max_steps":size*size,"steps":[],
            "mission":"go to %s %s %s"%("a" if len(pos)>1 else "the",t["color"],t["type"])}
        ep["par"]=par(ep)
        if ep["par"]>0: return ep
