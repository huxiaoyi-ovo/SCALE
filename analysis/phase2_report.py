#!/usr/bin/env python3
"""Locked, descriptive-only Phase-2 screening report and source-driven plots."""
from __future__ import annotations
import csv,gzip,hashlib,json,math,random,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/phase2_execution_screening';BOOTSTRAP_SEED=20260822
METRICS=('success','collision','timeout','planner_failure','capped_time_to_termination','path_length','min_clearance','final_xy_error')
FOREST=('capped_time_to_termination','path_length','min_clearance','final_xy_error')
def rows(p):return list(csv.DictReader(Path(p).open(newline='')))
def _canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _v(r,m):
    if m in ('success','collision'):return float(str(r.get(m,'false')).lower()=='true')
    if m=='timeout':return float(r.get('reason') in ('duration','logical_timeout'))
    if m=='planner_failure':return float(float(r.get('planner_failures',0))>0)
    if m=='capped_time_to_termination':return float(r.get('final_time',30.0))
    return float(r[m])
def _pct(x,p):
    x=sorted(x);q=(len(x)-1)*p;i=int(q);j=min(i+1,len(x)-1);return x[i]+(x[j]-x[i])*(q-i)
def paired_bootstrap(values,seed=BOOTSTRAP_SEED,resamples=5000):
    rng=random.Random(seed);samples=[sum(values[rng.randrange(len(values))] for _ in values)/len(values) for _ in range(resamples)]
    return sum(values)/len(values),_pct(samples,.025),_pct(samples,.975)
def _seed(*x):return BOOTSTRAP_SEED+int(hashlib.sha256('|'.join(x).encode()).hexdigest()[:8],16)%100000
def _write(p,data):
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]) if data else []);w.writeheader();w.writerows(data)
def _check(out):
    lock=json.loads((out/'lock.json').read_text());rs=rows(out/'episodes.csv');h=lock.get('lock_hash')
    core=lock.get('lock_core',{})
    if not lock.get('success') or _canonical(core)!=h:raise RuntimeError('invalid analysis lock')
    if not all(core.get('preflight',{}).get('contracts',{}).get(name) is True for name in ('timing','feedback','command_hold','collision','determinism')):raise RuntimeError('preflight contract is not locked as passed')
    if any(_file_hash(ROOT/path)!=digest for path,digest in core.get('code_hashes',{}).items()):raise RuntimeError('analysis source hash drift')
    if len(rs)!=880 or len({x['episode_id'] for x in rs})!=880 or any(x.get('valid')!='true' or x.get('lock_hash')!=h for x in rs):raise RuntimeError('report requires exactly 880 valid locked episodes')
    for r in rs:
        try:
            with gzip.open(out/'traces'/(r['episode_id']+'.json.gz'),'rt') as f:json.load(f)
        except (OSError,json.JSONDecodeError):raise RuntimeError('missing or unreadable locked trace')
        if not all(r.get(x)=='true' for x in ('time_contract','feedback_contract','command_hold_contract','collision_truth_contract')):raise RuntimeError('invalid experiment contract')
    return lock,rs
def analyze(output=OUT,resamples=5000):
    out=Path(output);lock,rs=_check(out);dest=out/'analysis';dest.mkdir(parents=True,exist_ok=True);groups=defaultdict(list)
    for r in rs:groups[(r['partition'],r['planner'],r['profile_id'])].append(r)
    desc=[]
    for key,grp in sorted(groups.items()):
        for m in METRICS:
            x=[_v(r,m) for r in grp];mean=sum(x)/len(x);desc.append({'partition':key[0],'planner':key[1],'profile_id':key[2],'metric':m,'n':len(x),'mean':mean,'sd':math.sqrt(sum((z-mean)**2 for z in x)/(len(x)-1)) if len(x)>1 else 0.0,'median':_pct(x,.5),'min':min(x),'max':max(x)})
    for planner in ('dwa','teb'):
      for profile in sorted({r['profile_id'] for r in rs}):
       grp=[r for r in rs if r['planner']==planner and r['profile_id']==profile]
       for m in METRICS:
        x=[_v(r,m) for r in grp];mean=sum(x)/len(x);desc.append({'partition':'combined_descriptive','planner':planner,'profile_id':profile,'metric':m,'n':len(x),'mean':mean,'sd':math.sqrt(sum((z-mean)**2 for z in x)/(len(x)-1)) if len(x)>1 else 0.0,'median':_pct(x,.5),'min':min(x),'max':max(x)})
    index={(r['partition'],r['layout_id'],r['planner'],r['profile_id']):r for r in rs};effects=[];inter=[];success_ci=[]
    profiles=sorted({r['profile_id'] for r in rs if r['profile_id']!='e0'})
    for part in ('discovery','holdout'):
      layouts=sorted({r['layout_id'] for r in rs if r['partition']==part})
      for planner in ('dwa','teb'):
       for profile in sorted({r['profile_id'] for r in rs}):
        vals=[_v(index[(part,l,planner,profile)],'success') for l in layouts];e,lo,hi=paired_bootstrap(vals,_seed(part,planner,profile,'success'),resamples);success_ci.append({'partition':part,'planner':planner,'profile_id':profile,'metric':'success','estimate':e,'ci_low':lo,'ci_high':hi,'n_layouts':20})
       for profile in profiles:
        for m in METRICS:
         v=[_v(index[(part,l,planner,profile)],m)-_v(index[(part,l,planner,'e0')],m) for l in layouts];e,lo,hi=paired_bootstrap(v,_seed(part,planner,profile,m),resamples);effects.append({'partition':part,'planner':planner,'profile_id':profile,'metric':m,'estimate':e,'ci_low':lo,'ci_high':hi,'n_layouts':20})
      for profile in profiles:
       for m in METRICS:
        v=[(_v(index[(part,l,'teb',profile)],m)-_v(index[(part,l,'teb','e0')],m))-(_v(index[(part,l,'dwa',profile)],m)-_v(index[(part,l,'dwa','e0')],m)) for l in layouts];e,lo,hi=paired_bootstrap(v,_seed(part,profile,m),resamples);inter.append({'partition':part,'profile_id':profile,'metric':m,'contrast':'TEB-minus-DWA degradation','estimate':e,'ci_low':lo,'ci_high':hi,'n_layouts':20})
    _write(dest/'descriptive.csv',desc);_write(dest/'paired_effects.csv',effects);_write(dest/'bootstrap_ci.csv',success_ci);_write(dest/'interaction_contrasts.csv',inter)
    source=[]
    for r in rs:source.append({k:r.get(k,'') for k in ('episode_id','partition','layout_id','planner','profile_id','success','reason','collision','planner_failures','final_time','path_length','min_clearance','final_xy_error')})
    _write(dest/'figure_source_episodes.csv',source);_figures(dest,success_ci,effects,inter,rs)
    manifest={'estimator':'mean; sample SD in descriptives; paired layout percentile bootstrap where contrasted','confidence_interval':'95% percentile','unit':'layout','seed':BOOTSTRAP_SEED,'resamples':resamples,'sources':['episodes.csv','figure_source_episodes.csv','bootstrap_ci.csv','paired_effects.csv','interaction_contrasts.csv'],'packages':{'python':sys.version.split()[0],'matplotlib':__import__('matplotlib').__version__},'audience':'provisional general audience','journal_compliance_claim':False}
    (dest/'figure_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    attempts=rows(out/'attempts.csv') if (out/'attempts.csv').exists() else []
    outcomes=defaultdict(int)
    for r in rs:outcomes[r['reason']]+=1
    attempt_status=defaultdict(int)
    for r in attempts:attempt_status[r['status']]+=1
    report='# Phase 2 execution-profile screening\n\nSYNTHETIC — NOT PHYSICALLY IDENTIFIED. Descriptive screening only; no p-values, scientific interpretation, or GO/NO-GO decision.\n\n## Protocol and provenance\n\n- Lock: `{}`\n- Protocol/layout/schedule hashes: `{}` / `{}` / `{}`\n- Git head / Phase 1C base: `{}` / `{}`\n- Episodes: 880 valid locked traces (440 discovery, 440 holdout).\n- Bootstrap: layout-unit percentile 95% CI, {} fixed resamples, seed {}.\n- Preflight contracts: timing, executed odom, command hold, collision truth, and restart determinism passed before the lock was created.\n\n## Completion and outcomes\n\n- Terminal reasons: `{}`\n- Attempt ledger statuses: `{}`\n- Exclusions: none; algorithm failure, collision, and logical timeout remain valid terminal episodes.\n- Infrastructure retries are reported in `attempts.csv`; no algorithm outcome is selectively rerun.\n\n## Tables and figures\n\n- `descriptive.csv`: n, mean, sample SD, median, minimum, and maximum.\n- `bootstrap_ci.csv`: partitioned success-rate 95% bootstrap intervals.\n- `paired_effects.csv`: within-planner profile-minus-E0 paired changes.\n- `interaction_contrasts.csv`: TEB-minus-DWA degradation contrasts.\n- Five source-driven PNG/PDF figures, `figure_source_episodes.csv`, and `figure_manifest.json`.\n\nDiscovery and holdout remain separate for all bootstrap and interaction estimates; combined rows are descriptive only. The figures are provisional general-purpose scientific graphics, not a journal-compliance claim. This report stops at the scientific review gate and makes no scientific decision.\n'.format(lock['lock_hash'],lock['lock_core']['protocol_hash'],lock['lock_core']['layouts_hash'],lock['lock_core']['schedule_hash'],lock['lock_core']['git_head'],lock['lock_core']['phase1c_base'],resamples,BOOTSTRAP_SEED,dict(sorted(outcomes.items())),dict(sorted(attempt_status.items())))
    (dest/'REPORT.md').write_text(report);return {'episodes':880,'analysis':str(dest)}
def _save(fig,path):fig.savefig(str(path)+'.png',dpi=180);fig.savefig(str(path)+'.pdf');
def _figures(d,success,effects,inter,rs):
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm,ListedColormap
    profiles=sorted({r['profile_id'] for r in rs}); positions=list(range(len(profiles)))
    colors={'dwa':'#0072B2','teb':'#D55E00'};markers={'dwa':'o','teb':'s'}
    fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True,layout='constrained')
    for ax,part in zip(axes,('discovery','holdout')):
      for planner,offset in (('dwa',-.08),('teb',.08)):
        data=[next(r for r in success if r['partition']==part and r['planner']==planner and r['profile_id']==profile) for profile in profiles]
        estimate=[r['estimate'] for r in data]
        ax.errorbar([x+offset for x in positions],estimate,yerr=[[r['estimate']-r['ci_low'] for r in data],[r['ci_high']-r['estimate'] for r in data]],color=colors[planner],marker=markers[planner],linestyle='none',capsize=2,label=planner.upper())
      ax.set_ylim(0,1);ax.set_ylabel(part+' success rate');ax.legend()
    axes[-1].set_xticks(positions);axes[-1].set_xticklabels(profiles,rotation=45,ha='right');_save(fig,d/'success_rates');plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True,layout='constrained');cats=('collision','timeout','planner_failure');hatches=('//','\\\\','xx')
    for ax,part in zip(axes,('discovery','holdout')):
      for planner,offset in (('dwa',-.2),('teb',.2)):
        bottom=[0.]*len(profiles)
        for category,hatch in zip(cats,hatches):
          values=[]
          for profile in profiles:
            group=[r for r in rs if r['partition']==part and r['planner']==planner and r['profile_id']==profile]
            values.append(sum(_v(r,category) for r in group)/len(group))
          ax.bar([x+offset for x in positions],values,.36,bottom=bottom,color=colors[planner],alpha=.78,hatch=hatch,edgecolor='white',label='{} {}'.format(planner.upper(),category));bottom=[a+b for a,b in zip(bottom,values)]
      ax.set_ylim(0,1);ax.set_ylabel(part+' outcome rate');ax.legend(ncol=3,fontsize=7)
    axes[-1].set_xticks(positions);axes[-1].set_xticklabels(profiles,rotation=45,ha='right');_save(fig,d/'failure_modes');plt.close(fig)
    for name,data in (('paired_degradation',effects),('interaction_contrasts',inter)):
      fig,axes=plt.subplots(4,2,figsize=(13,11),sharex=False,layout='constrained')
      for column,part in enumerate(('discovery','holdout')):
       for row,metric in enumerate(FOREST):
        ax=axes[row,column];ax.axhline(0,color='#555555',lw=.7)
        if name=='paired_degradation':
         for planner,offset in (('dwa',-.08),('teb',.08)):
          selected=[next(r for r in data if r['partition']==part and r['planner']==planner and r['profile_id']==profile and r['metric']==metric) for profile in profiles if profile!='e0'];xx=[x+offset for x in range(len(selected))]
          ax.errorbar(xx,[r['estimate'] for r in selected],yerr=[[r['estimate']-r['ci_low'] for r in selected],[r['ci_high']-r['estimate'] for r in selected]],color=colors[planner],marker=markers[planner],linestyle='none',capsize=2,label=planner.upper())
        else:
          selected=[next(r for r in data if r['partition']==part and r['profile_id']==profile and r['metric']==metric) for profile in profiles if profile!='e0'];ax.errorbar(range(len(selected)),[r['estimate'] for r in selected],yerr=[[r['estimate']-r['ci_low'] for r in selected],[r['ci_high']-r['estimate'] for r in selected]],color='#009E73',marker='D',linestyle='none',capsize=2,label='TEB-DWA degradation')
        ax.set_title('{} — {}'.format(part,metric));ax.set_xticks(range(len(profiles)-1));ax.set_xticklabels([p for p in profiles if p!='e0'],rotation=45,ha='right',fontsize=7);ax.set_ylabel('change vs E0' if name=='paired_degradation' else 'interaction contrast')
        if row==0:ax.legend(fontsize=8)
      _save(fig,d/name);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for ax,(part,planner) in zip(axes.flat,((a,b) for a in ('discovery','holdout') for b in ('dwa','teb'))):
      layouts=sorted({r['layout_id'] for r in rs if r['partition']==part});profiles=sorted({r['profile_id'] for r in rs}); matrix=[]
      for l in layouts:
       line=[]
       for p in profiles:
        r=next(x for x in rs if x['partition']==part and x['layout_id']==l and x['planner']==planner and x['profile_id']==p);line.append(0 if r['success']=='true' else 1 if r['collision']=='true' else 2 if r['reason'] in ('duration','logical_timeout') else 3)
       matrix.append(line)
      cmap=ListedColormap(['#009E73','#D55E00','#E69F00','#7A5195']);norm=BoundaryNorm([-.5,.5,1.5,2.5,3.5],cmap.N)
      image=ax.imshow(matrix,aspect='auto',norm=norm,cmap=cmap);ax.set_title(part+' '+planner.upper());ax.set_xticks(range(len(profiles)));ax.set_xticklabels(profiles,rotation=90,fontsize=6);ax.set_yticks(range(20));ax.set_yticklabels(layouts,fontsize=5)
    colorbar=fig.colorbar(image,ax=axes.ravel().tolist(),ticks=[0,1,2,3],shrink=.7);colorbar.ax.set_yticklabels(['success','collision','timeout','planner failure'])
    _save(fig,d/'outcome_heatmap');plt.close(fig)
if __name__=='__main__':print(json.dumps(analyze(),sort_keys=True))
