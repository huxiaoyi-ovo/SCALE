"""Protocol-derived deterministic geometry and schedule helpers (no planners)."""
from __future__ import annotations
import csv, hashlib, heapq, json, math, random
from pathlib import Path
import yaml
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, Point, box

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "configs/phase2/protocol.yaml"
def canonical_hash(v): return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def load_yaml(path):
    with Path(path).open() as f: return yaml.safe_load(f)
def profiles(p): return p["matrix"]["profiles"]
def validate_protocol(p):
    m,t,g=p["matrix"],p["timing"],p["layout_generation"]
    if m["planners"] != ["dwa","teb"] or len(profiles(p)) != 11: raise ValueError("matrix mismatch")
    if (t["planner_period"],t["execution_dt"],t["logical_duration"]) != (.05,.01,30.0): raise ValueError("timing mismatch")
    if p["provenance"] != "SYNTHETIC - NOT PHYSICALLY IDENTIFIED": raise ValueError("provenance mismatch")
    if (g["seed"],g["discovery_count"],g["holdout_count"],g["obstacle_count"]) != (20260820,20,20,6): raise ValueError("layout protocol mismatch")
    for x in profiles(p):
        values=[x[k] for k in ("delay","tau_x","tau_y","tau_w")]
        if x["id"] == "e0":
            if x["backend"] != "e0" or any(values): raise ValueError("invalid E0")
        elif x["backend"] != "e1" or sum(v>0 for v in values)!=1: raise ValueError("E1 not one-factor")
    return p
def _shape(x):
    return Point(x["x"],x["y"]).buffer(x["radius"],resolution=32) if x["type"]=="circle" else box(x["x"]-x["width"]/2,x["y"]-x["length"]/2,x["x"]+x["width"]/2,x["y"]+x["length"]/2)
def _pt(x): return Point(x["x"],x["y"])
def _params(p):
    g=p["layout_generation"]; return g,g["arena"],g["start"],g["goal"],g["path_grid_resolution"],g["footprint_circumscribed_radius"]+g["path_safety_margin"]
def _candidate(rng,p):
    g,a,s,z,_,_= _params(p); out=[]
    for _ in range(g["obstacle_count"]):
        circle=rng.random()<g["circle_probability"]
        if circle:
            r=round(rng.uniform(*g["circle_radius_range"]),3); xlo,xhi=g["boundary_margin"]+r,a["width"]-g["boundary_margin"]-r; ylo,yhi=g["boundary_margin"]+r,a["height"]-g["boundary_margin"]-r; item={"type":"circle","radius":r}
        else:
            w,l=round(rng.uniform(*g["rectangle_width_range"]),3),round(rng.uniform(*g["rectangle_length_range"]),3); xlo,xhi=g["boundary_margin"]+w/2,a["width"]-g["boundary_margin"]-w/2; ylo,yhi=g["boundary_margin"]+l/2,a["height"]-g["boundary_margin"]-l/2; item={"type":"rectangle","width":w,"length":l,"yaw":0.0}
        item.update(x=round(rng.uniform(xlo,xhi),3),y=round(rng.uniform(ylo,yhi),3)); shape=_shape(item)
        if shape.distance(_pt(s))<g["start_goal_exclusion"] or shape.distance(_pt(z))<g["start_goal_exclusion"] or any(shape.distance(_shape(old))<g["obstacle_separation"] for old in out): return None
        out.append(item)
    return out
def _simplify(points):
    out=[points[0]]
    for i,p in enumerate(points[1:-1],1):
        a,c=out[-1],points[i+1]
        if abs((p[0]-a[0])*(c[1]-p[1])-(p[1]-a[1])*(c[0]-p[0]))>1e-12: out.append(p)
    return out+[points[-1]]
def _path(obs,p):
    g,a,s,z,d,inflate=_params(p); nx,ny=round(a["width"]/d),round(a["height"]/d); blocked=[_shape(x).buffer(inflate) for x in obs]
    def free(n):
        x,y=(n[0]+.5)*d,(n[1]+.5)*d
        return inflate<=x<=a["width"]-inflate and inflate<=y<=a["height"]-inflate and not any(q.covers(Point(x,y)) for q in blocked)
    def node(x): return int(x["x"]/d-.5),int(x["y"]/d-.5)
    st,go=node(s),node(z)
    if not free(st) or not free(go): return None
    q=[(0.,st)]; parents={};cost={st:0.};moves=[(i,j) for i in (-1,0,1) for j in (-1,0,1) if i or j]
    while q:
        _,cur=heapq.heappop(q)
        if cur==go:
            raw=[cur]
            while cur in parents:cur=parents[cur];raw.append(cur)
            raw.reverse(); return _simplify([(s['x'],s['y'])]+[((i+.5)*d,(j+.5)*d) for i,j in raw[1:-1]]+[(z['x'],z['y'])])
        for dx,dy in moves:
            nxt=cur[0]+dx,cur[1]+dy
            if dx and dy and (not free((cur[0]+dx,cur[1])) or not free((cur[0],cur[1]+dy))): continue
            if not(0<=nxt[0]<nx and 0<=nxt[1]<ny) or not free(nxt): continue
            c=cost[cur]+d*math.hypot(dx,dy)
            if c+1e-12<cost.get(nxt,float('inf')):
                cost[nxt]=c;parents[nxt]=cur;heapq.heappush(q,(c+d*math.hypot(nxt[0]-go[0],nxt[1]-go[1]),nxt))
    return None
def _poses(points,s,z):
    out=[]
    for i,(x,y) in enumerate(points):
        a,b=points[max(0,i-1)],points[min(len(points)-1,i+1)];out.append({'x':round(x,6),'y':round(y,6),'yaw':round(math.atan2(b[1]-a[1],b[0]-a[0]) if a!=b else 0.,6)})
    out[0]['yaw']=s.get('yaw',0.);out[-1]['yaw']=z.get('yaw',0.);return out
def validate_layouts(layouts,p):
    g,a,s,z,_,inflate=_params(p); items=layouts.get('layouts',[])
    if len(items)!=40 or sum(x['partition']=='discovery' for x in items)!=20 or sum(x['partition']=='holdout' for x in items)!=20: raise ValueError('count mismatch')
    footprint=p['robot']['footprint']; robot=box(-footprint['width']/2,-footprint['length']/2,footprint['width']/2,footprint['length']/2); inset=box(inflate,inflate,a['width']-inflate,a['height']-inflate)
    for item in items:
        obs=[_shape(x) for x in item['obstacles']]
        if len(obs)!=6 or item['start']!=s or item['goal']!=z: raise ValueError('layout mismatch')
        for shape in obs:
            if shape.distance(_pt(s))<g['start_goal_exclusion'] or shape.distance(_pt(z))<g['start_goal_exclusion']: raise ValueError('endpoint exclusion')
            lo=shape.bounds
            if lo[0]<g['boundary_margin'] or lo[1]<g['boundary_margin'] or lo[2]>a['width']-g['boundary_margin'] or lo[3]>a['height']-g['boundary_margin']:raise ValueError('boundary')
        if any(x.distance(y)<g['obstacle_separation'] for i,x in enumerate(obs) for y in obs[i+1:]):raise ValueError('separation')
        path=item['global_path']; pts=[(x['x'],x['y']) for x in path]
        if len(pts)<2 or pts[0]!=(s['x'],s['y']) or pts[-1]!=(z['x'],z['y']) or not all(math.isfinite(x['yaw']) for x in path):raise ValueError('path endpoint/yaw')
        if any(not inset.covers(LineString([x,y])) or any(LineString([x,y]).intersects(q.buffer(inflate)) for q in obs) for x,y in zip(pts,pts[1:])):raise ValueError('continuous path')
        endpoint_footprints=[translate(rotate(robot,e.get('yaw',0.),origin=(0,0),use_radians=True),xoff=e['x'],yoff=e['y']) for e in (s,z)]
        if any(body.intersects(obstacle) for body in endpoint_footprints for obstacle in obs):raise ValueError('physical endpoint collision')
        length=sum(math.hypot(b[0]-c[0],b[1]-c[1]) for c,b in zip(pts,pts[1:])); lo,hi=g['accepted_path_length_range']
        if not lo<=length<=hi:raise ValueError('path length')
    return True
def generate_layouts(protocol=None):
    p=validate_protocol(protocol or load_yaml(PROTOCOL_PATH));g,a,s,z,d,inflate=_params(p); rng=random.Random(g['seed']);out=[];idx=0
    while len(out)<40:
        idx+=1;obs=_candidate(rng,p)
        if not obs:continue
        path=_path(obs,p)
        if not path:continue
        length=sum(math.hypot(b[0]-c[0],b[1]-c[1]) for c,b in zip(path,path[1:]));lo,hi=g['accepted_path_length_range']
        if not lo<=length<=hi:continue
        part='discovery' if len(out)<20 else 'holdout';out.append({'layout_id':'{}_{:02d}'.format(part,len(out)%20+1),'partition':part,'candidate_index':idx,'candidate_seed':g['seed'],'arena':a,'start':s,'goal':z,'obstacles':obs,'global_path':_poses(path,s,z),'geometry_diagnostics':{'obstacle_count':6,'grid_resolution':d,'inflation_radius':inflate,'path_length':round(length,6)}})
    result={'schema_version':1,'layout_seed':g['seed'],'generation':g,'layouts':out};validate_layouts(result,p);return result
def make_schedule(p,layouts):
    rows=[{'episode_id':'{}__{}__{}__{}'.format(x['partition'],x['layout_id'],planner,pr['id']),'partition':x['partition'],'layout_id':x['layout_id'],'planner':planner,'profile_id':pr['id']} for x in layouts['layouts'] for planner in p['matrix']['planners'] for pr in profiles(p)]
    random.Random(p['randomization']['schedule_seed']).shuffle(rows)
    for i,x in enumerate(rows,1):x['schedule_index']=i
    return rows
def write_schedule(path,rows):
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=('schedule_index','episode_id','partition','layout_id','planner','profile_id'));w.writeheader();w.writerows(rows)
