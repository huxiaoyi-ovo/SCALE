#!/usr/bin/env python3
"""Locked, resumable Phase-2 execution runner."""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,multiprocessing as mp,os,queue,signal,socket,subprocess,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.phase2_protocol import canonical_hash,generate_layouts,load_yaml,make_schedule,validate_layouts,validate_protocol,write_schedule
from simulation.execution import Pose2D
from simulation.geometry import collision, footprint, minimum_clearance, transform_footprint
from simulation.maps import load_layout
PROTOCOL=ROOT/'configs/phase2/protocol.yaml';LAYOUTS=ROOT/'configs/phase2/layouts.yaml';SCHEDULE=ROOT/'configs/phase2/schedule.csv';OUTPUT=ROOT/'data/phase2_execution_screening'
CONTRACT=('time_contract','feedback_contract','command_hold_contract'); PHASE1C_BASE='b778f11'

class ContractFailure(RuntimeError): pass
class InfrastructureFailure(RuntimeError): pass

def _now():return datetime.now(timezone.utc).isoformat()
def _hashfile(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _rows(p):return list(csv.DictReader(Path(p).open(newline=''))) if Path(p).exists() else []
def _atomic(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text);tmp.replace(path)
def _append(path,row):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True); exists=path.exists()
    with path.open('a',newline='') as f:
        w=csv.DictWriter(f,fieldnames=tuple(row));
        if not exists:w.writeheader()
        w.writerow(row);f.flush();os.fsync(f.fileno())
def _git_head():return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
def _dependency_versions():
    return {'python':sys.version.split()[0],'pyyaml':yaml.__version__,'shapely':__import__('shapely').__version__}

def generate(protocol_path=PROTOCOL,layouts_path=LAYOUTS,schedule_path=SCHEDULE):
    p=validate_protocol(load_yaml(protocol_path)); layouts=generate_layouts(p);_atomic(layouts_path,yaml.safe_dump(layouts,sort_keys=False));write_schedule(schedule_path,make_schedule(p,layouts))
    return {'layouts':40,'episodes':880,'layouts_hash':canonical_hash(layouts),'schedule_hash':canonical_hash(_rows(schedule_path))}
def static_preflight(protocol_path=PROTOCOL,layouts_path=LAYOUTS,schedule_path=SCHEDULE):
    p=validate_protocol(load_yaml(protocol_path));layouts=load_yaml(layouts_path);validate_layouts(layouts,p); rows=_rows(schedule_path);expected=make_schedule(p,layouts)
    if len(rows)!=880 or len({x['episode_id'] for x in rows})!=880 or {x['episode_id'] for x in rows}!={x['episode_id'] for x in expected}:raise RuntimeError('schedule mismatch')
    t=p['timing']
    if not math.isclose(round(t['planner_period']/t['execution_dt'])*t['execution_dt'],t['planner_period']):raise RuntimeError('timing divisibility')
    if subprocess.run(['git','merge-base','--is-ancestor',PHASE1C_BASE,'HEAD'],cwd=ROOT).returncode:raise RuntimeError('Phase 1C base is not an ancestor of HEAD')
    return {'static':True,'protocol_hash':canonical_hash(p),'layouts_hash':canonical_hash(layouts),'schedule_hash':canonical_hash(rows),'matrix_episodes':880}
def lock_core(static,evidence):
    paths=[ROOT/'experiments/phase2_runner.py',ROOT/'experiments/phase2_protocol.py',ROOT/'analysis/phase2_report.py',ROOT/'navigation/scale_planner_bridge/scripts/planner_execution_smoke.py']
    return {'protocol_hash':static['protocol_hash'],'layouts_hash':static['layouts_hash'],'schedule_hash':static['schedule_hash'],'git_head':_git_head(),'phase1c_base':PHASE1C_BASE,'code_hashes':{str(x.relative_to(ROOT)):_hashfile(x) for x in paths},'dependencies':_dependency_versions(),'preflight':evidence}
def _run_checked(command,timeout=600):
    x=subprocess.run(command,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout);return {'command':command,'returncode':x.returncode,'stdout':x.stdout[-12000:]}
def preflight(protocol_path=PROTOCOL,layouts_path=LAYOUTS,schedule_path=SCHEDULE,output=OUTPUT):
    """Real engineering gate. It writes no lock until every subprocess passes."""
    static=static_preflight(protocol_path,layouts_path,schedule_path);commands=[['.venv/bin/python','-m','pytest','-q'],['catkin_make','-C','build/scale_ros','--source','navigation']]
    evidence={'static':static,'commands':[_run_checked(x) for x in commands]}
    if any(x['returncode'] for x in evidence['commands']):raise RuntimeError('build/test preflight failure')
    protocol=load_yaml(protocol_path)
    pilot=load_yaml(ROOT/'configs/pilot.yaml')['layout'];pilot=dict(pilot,layout_id='engineering_fixture')
    probe_executor=RosExecutor(protocol,{'layouts':[pilot]},Path(output)/'engineering_probe')
    try:
        probe_executor.start();probe_summary,probe_trace=probe_executor({'episode_id':'engineering_fixture__dwa__e0','partition':'engineering','layout_id':'engineering_fixture','planner':'dwa','profile_id':'e0','_attempt':1})
    finally:
        probe_executor.close()
    if not all(probe_summary.get(key) is True for key in CONTRACT) or not probe_trace.get('execution_states'):raise RuntimeError('batch executor probe contract failure')
    evidence['batch_executor_probe']={'summary':probe_summary,'trace_states':len(probe_trace['execution_states'])}
    det=[]
    for planner in ('dwa','teb'):
      for execution in ('e0','e1'):
        x=_run_checked(['.venv/bin/python','navigation/scale_planner_bridge/scripts/determinism_regression.py','--planner',planner,'--execution',execution,'--runs','2','--tolerance','1e-9'],120)
        if x['returncode']:raise RuntimeError('determinism preflight failure')
        result=json.loads(x['stdout'].splitlines()[-1])
        if result['max_abs_difference']>1e-9:raise RuntimeError('determinism contract failure')
        det.append({'planner':planner,'execution':execution,'result':result,'command':x})
    evidence['determinism']=det;evidence['contracts']={'timing':True,'feedback':True,'command_hold':True,'collision':True,'determinism':True}
    core=lock_core(static,evidence); lock={'success':True,'lock_core':core,'lock_hash':canonical_hash(core),'created_at':_now()};out=Path(output);_atomic(out/'preflight.json',json.dumps(evidence,indent=2,sort_keys=True)+'\n');_atomic(out/'lock.json',json.dumps(lock,indent=2,sort_keys=True)+'\n');return lock

def classify_failure(summary=None,error=None):
    if isinstance(error,ContractFailure):return 'contract'
    if error is not None:return 'infrastructure'
    if not summary or not all(summary.get(x) is True for x in CONTRACT):return 'contract'
    return 'algorithm'
def _valid_done(output,lock_hash):
    done=set()
    for row in _rows(Path(output)/'episodes.csv'):
        trace=Path(output)/'traces'/(row['episode_id']+'.json.gz')
        try:
            if row.get('valid')=='true' and row.get('lock_hash')==lock_hash:
                with gzip.open(trace,'rt') as f:json.load(f)
                done.add(row['episode_id'])
        except (OSError,json.JSONDecodeError):pass
    return done
def _attempts(output,episode):return sum(x['episode_id']==episode for x in _rows(Path(output)/'attempts.csv'))
def _trace(output,episode,trace):
    p=Path(output)/'traces'/(episode+'.json.gz');p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp')
    with gzip.open(tmp,'wt') as f:json.dump(trace,f,sort_keys=True)
    tmp.replace(p);return p
def _episode_record(episode,summary,trace,lock_hash,raw_layout,robot_spec):
    states=trace.get('execution_states',[])
    if not states:raise InfrastructureFailure('trace contains no execution states')
    length=sum(math.hypot(b['x']-a['x'],b['y']-a['y']) for a,b in zip(states,states[1:])); final=states[-1]
    layout=load_layout(raw_layout);robot=footprint(robot_spec)
    shapes=[transform_footprint(robot,Pose2D(x['x'],x['y'],x['yaw'])) for x in states]
    collision_truth=any(collision(shape,layout['obstacles']) for shape in shapes)
    if collision_truth is not bool(summary['collision']):raise ContractFailure('benchmark collision truth mismatch')
    clearance=min(minimum_clearance(shape,layout['obstacles']) for shape in shapes)
    clean_episode={key:value for key,value in episode.items() if not key.startswith('_')}
    return dict(clean_episode,lock_hash=lock_hash,valid='true',success=str(bool(summary['success'])).lower(),reason='logical_timeout' if summary['reason']=='duration' else summary['reason'],raw_reason=summary['reason'],collision=str(collision_truth).lower(),planner_failures=summary['planner_failures'],planner_calls=summary['planner_calls'],execution_steps=summary['execution_steps'],final_xy_error=summary['final_xy_error'],final_yaw_error=summary['final_yaw_error'],final_time=final['time'],capped_time_to_termination=final['time'],path_length=length,min_clearance=clearance,compute_mean=summary['compute_seconds']['mean'],compute_max=summary['compute_seconds']['max'],time_contract=str(bool(summary['time_contract'])).lower(),feedback_contract=str(bool(summary['feedback_contract'])).lower(),command_hold_contract=str(bool(summary['command_hold_contract'])).lower(),collision_truth_contract='true')

def _accept_episode(out,episode,summary,trace,lock_hash,layout_by_id,robot_spec,existing_by_id):
    if classify_failure(summary)=='contract':raise ContractFailure(summary.get('reason','contract failure'))
    record=_episode_record(episode,summary,trace,lock_hash,layout_by_id[episode['layout_id']],robot_spec)
    previous=existing_by_id.get(episode['episode_id'])
    if previous:
        comparable=tuple(key for key in record if key not in ('schedule_index',))
        if any(str(previous.get(key,''))!=str(record.get(key,'')) for key in comparable):
            raise ContractFailure('resume replay differs from terminal record')
        attempt_status='infrastructure_recovery'
    else:attempt_status='algorithm'
    attempt=int(episode['_attempt'])
    _append(out/'attempts.csv',{'timestamp':_now(),'episode_id':episode['episode_id'],'attempt':attempt,'status':attempt_status,'detail':summary.get('reason','')})
    _trace(out,episode['episode_id'],trace)
    if not previous:_append(out/'episodes.csv',record);existing_by_id[episode['episode_id']]=record

def _record_failure(out,episode,error):
    attempt=int(episode['_attempt']);contract=isinstance(error,ContractFailure);status='contract' if contract else 'infrastructure'
    _append(out/'attempts.csv',{'timestamp':_now(),'episode_id':episode['episode_id'],'attempt':attempt,'status':status,'detail':str(error)})
    if contract:raise RuntimeError('contract failure: '+episode['episode_id']) from error
    if attempt>=3:raise RuntimeError('infrastructure retry exhaustion: '+episode['episode_id']) from error

def _run_serial(todo,protocol,layouts,out,lock_hash,layout_by_id,existing_by_id,executor=None):
    owned=executor is None;executor=executor or RosExecutor(protocol,layouts,out)
    if owned:executor.start()
    try:
      completed=0
      for ep in todo:
        while True:
            call_episode=dict(ep,_attempt=_attempts(out,ep['episode_id'])+1)
            try:
                summary,trace=executor(call_episode)
                _accept_episode(out,call_episode,summary,trace,lock_hash,layout_by_id,protocol['robot']['footprint'],existing_by_id)
            except Exception as error:
                _record_failure(out,call_episode,error)
                continue
            break
        completed+=1
        if (len(existing_by_id)%10==0 or completed==len(todo)):print('phase2 progress: {}/880'.format(len(existing_by_id)),flush=True)
    finally:
      if owned:executor.close()

def _master_ports(count):
    """Choose private master ports below Linux's ephemeral range."""
    try:ephemeral_start=int(Path('/proc/sys/net/ipv4/ip_local_port_range').read_text().split()[0])
    except (OSError,ValueError,IndexError):ephemeral_start=32768
    ports=[]
    for port in range(15000,min(ephemeral_start,32768)):
        try:
            with socket.socket() as probe:probe.bind(('127.0.0.1',port))
        except OSError:continue
        ports.append(port)
        if len(ports)==count:return ports
    raise RuntimeError('not enough private ROS master ports')

def _parallel_worker(worker_id,master_port,protocol,layouts,output,tasks,results):
    executor=RosExecutor(protocol,layouts,Path(output)/'workers'/'worker_{:02d}'.format(worker_id),master_port=master_port)
    try:
        try:executor.start()
        except Exception as error:
            results.put({'kind':'startup_error','worker':worker_id,'detail':str(error)});return
        results.put({'kind':'ready','worker':worker_id,'ros_master_uri':executor.env['ROS_MASTER_URI']})
        while True:
            episode=tasks.get()
            if episode is None:return
            try:
                summary,trace=executor(episode)
                results.put({'kind':'episode','status':'ok','worker':worker_id,'episode':episode,'summary':summary,'trace':trace})
            except ContractFailure as error:
                results.put({'kind':'episode','status':'contract','worker':worker_id,'episode':episode,'detail':str(error)})
            except Exception as error:
                results.put({'kind':'episode','status':'infrastructure','worker':worker_id,'episode':episode,'detail':str(error)})
    finally:executor.close()

def _parallel_message(results,processes):
    while True:
        try:return results.get(timeout=1)
        except queue.Empty:
            stopped=[(process.pid,process.exitcode) for process in processes if process.exitcode is not None]
            if stopped:raise InfrastructureFailure('parallel worker exited unexpectedly: {}'.format(stopped))

def _run_parallel(todo,protocol,layouts,out,lock_hash,layout_by_id,existing_by_id,workers):
    worker_count=min(workers,len(todo))
    if not worker_count:return
    context=mp.get_context('spawn');tasks=context.Queue();results=context.Queue();ports=_master_ports(worker_count)
    processes=[context.Process(target=_parallel_worker,args=(index,ports[index],protocol,layouts,out,tasks,results)) for index in range(worker_count)]
    clean=False
    try:
        for process in processes:process.start()
        ready=0
        while ready<worker_count:
            message=_parallel_message(results,processes)
            if message['kind']=='startup_error':raise InfrastructureFailure('worker {} startup failed: {}'.format(message['worker'],message['detail']))
            if message['kind']!='ready':raise InfrastructureFailure('unexpected worker startup message')
            ready+=1
        for ep in todo:tasks.put(dict(ep,_attempt=_attempts(out,ep['episode_id'])+1))
        remaining=len(todo)
        while remaining:
            message=_parallel_message(results,processes)
            if message.get('kind')!='episode':raise InfrastructureFailure('unexpected parallel worker message')
            episode=message['episode']
            try:
                if message['status']=='contract':raise ContractFailure(message['detail'])
                if message['status']=='infrastructure':raise InfrastructureFailure(message['detail'])
                _accept_episode(out,episode,message['summary'],message['trace'],lock_hash,layout_by_id,protocol['robot']['footprint'],existing_by_id)
            except Exception as error:
                _record_failure(out,episode,error)
                tasks.put(dict(episode,_attempt=int(episode['_attempt'])+1))
                continue
            remaining-=1
            if len(existing_by_id)%10==0 or remaining==0:print('phase2 progress: {}/880'.format(len(existing_by_id)),flush=True)
        for _ in processes:tasks.put(None)
        for process in processes:process.join(timeout=10)
        failed=[(process.pid,process.exitcode) for process in processes if process.exitcode!=0]
        if failed:raise InfrastructureFailure('parallel workers did not close cleanly: {}'.format(failed))
        clean=True
    finally:
        if not clean:
            for process in processes:
                if process.is_alive():process.terminate()
            for process in processes:process.join(timeout=5)

def run(protocol_path=PROTOCOL,layouts_path=LAYOUTS,schedule_path=SCHEDULE,output=OUTPUT,executor=None,workers=1):
    if workers<1:raise ValueError('workers must be at least one')
    if executor is not None and workers!=1:raise ValueError('an injected executor requires workers=1')
    out=Path(output); lock=json.loads((out/'lock.json').read_text());static=static_preflight(protocol_path,layouts_path,schedule_path)
    if canonical_hash(lock['lock_core'])!=lock['lock_hash'] or any(lock['lock_core'][k]!=static[k] for k in ('protocol_hash','layouts_hash','schedule_hash')):raise RuntimeError('immutable lock drift')
    if 'code_hashes' in lock['lock_core'] and any(_hashfile(ROOT / path) != digest for path,digest in lock['lock_core']['code_hashes'].items()):raise RuntimeError('source hash drift')
    episode_rows=_rows(out/'episodes.csv')
    if len(episode_rows)!=len({x['episode_id'] for x in episode_rows}):raise RuntimeError('duplicate terminal episode rows')
    if any(x.get('valid')!='true' or x.get('lock_hash')!=lock['lock_hash'] for x in episode_rows):raise RuntimeError('terminal episode lock/validity mismatch')
    existing_by_id={x['episode_id']:x for x in episode_rows}
    done=_valid_done(out,lock['lock_hash']); todo=[x for x in _rows(schedule_path) if x['episode_id'] not in done]
    protocol=load_yaml(protocol_path);layouts=load_yaml(layouts_path);layout_by_id={x['layout_id']:x for x in layouts['layouts']}
    if workers==1:_run_serial(todo,protocol,layouts,out,lock['lock_hash'],layout_by_id,existing_by_id,executor)
    else:_run_parallel(todo,protocol,layouts,out,lock['lock_hash'],layout_by_id,existing_by_id,workers)
    return {'completed':len(_valid_done(out,lock['lock_hash'])),'lock_hash':lock['lock_hash'],'workers':workers}

class RosExecutor:
    """Per-episode bridge process; roscore is private and persistent for batch."""
    def __init__(self,protocol,layouts,output,master_port=None):
        self.protocol,self.layouts,self.output=protocol,{x['layout_id']:x for x in layouts['layouts']},Path(output);self.master_port=master_port;self.core=None;self.temp=None;self.env=None
    def start(self):
        port=self.master_port if self.master_port is not None else self._port();self.temp=tempfile.TemporaryDirectory(prefix='scale_phase2_');ros_home=Path(self.temp.name)/'ros_home';ros_log=Path(self.temp.name)/'ros_log';ros_home.mkdir();ros_log.mkdir();self.env=os.environ.copy();self.env.update(ROS_MASTER_URI='http://127.0.0.1:{}'.format(port),ROS_IP='127.0.0.1',ROS_HOME=str(ros_home),ROS_LOG_DIR=str(ros_log));log=(self.output/'logs'/'roscore.log');log.parent.mkdir(parents=True,exist_ok=True);self.core_log=log.open('a')
        self.core=subprocess.Popen(['roscore','-p',str(port)],env=self.env,stdout=self.core_log,stderr=subprocess.STDOUT,start_new_session=True)
        self._wait_master()
    def close(self):
        if self.core and self.core.poll() is None:
            self.core.send_signal(signal.SIGINT)
            try:self.core.wait(timeout=5)
            except subprocess.TimeoutExpired:self.core.kill()
        if getattr(self,'core_log',None):self.core_log.close();self.core_log=None
        if self.temp:self.temp.cleanup();self.temp=None
    @staticmethod
    def _port():
        return _master_ports(1)[0]
    def _wait_master(self):
        end=time.monotonic()+10
        while time.monotonic()<end:
            if self.core.poll() is not None:raise RuntimeError('roscore exited')
            if subprocess.run(['rosparam','list'],env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:return
            time.sleep(.05)
        raise RuntimeError('ROS master unavailable')
    def _call(self,args,log):
        x=subprocess.run(args,cwd=ROOT,env=self.env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
        with log.open('a') as f:f.write('$ {}\n{}\n'.format(' '.join(args),x.stdout))
        if x.returncode:raise RuntimeError('ros command failed: '+args[0])
        return x.stdout
    def __call__(self,episode):
        if not self.core:raise RuntimeError('RosExecutor not started')
        profile=next(x for x in self.protocol['matrix']['profiles'] if x['id']==episode['profile_id']);layout=self.layouts[episode['layout_id']]; base=self.output/'logs'/(episode['episode_id']+'.attempt_{:02d}'.format(int(episode.get('_attempt',1))));base.parent.mkdir(parents=True,exist_ok=True);log=base.with_suffix('.log');tmp=Path(self.temp.name); layout_file=tmp/(episode['episode_id']+'.yaml');trace_file=tmp/(episode['episode_id']+'.trace.json')
        config={'layout':layout,'robot_footprint':self.protocol['robot']['footprint'],'dt':self.protocol['timing']['execution_dt'],'duration':self.protocol['timing']['logical_duration']};layout_file.write_text(yaml.safe_dump(config,sort_keys=False))
        execution={'execution':{'backend':profile['backend'],'dt':self.protocol['timing']['execution_dt'],'provenance':'IDEAL E0' if profile['backend']=='e0' else self.protocol['provenance']}}
        if profile['backend']=='e1':execution['execution']['profile']={k:profile[k] for k in ('delay','tau_x','tau_y','tau_w')}
        execution_file=tmp/(episode['episode_id']+'.execution.yaml');execution_file.write_text(yaml.safe_dump(execution,sort_keys=False))
        subprocess.run(['rosparam','delete','/scale_planner_bridge'],env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self._call(['rosparam','set','/use_sim_time','true'],log); self._call(['rosparam','load',str(ROOT/'navigation/scale_planner_bridge/config/common.yaml'),'/scale_planner_bridge/local_costmap'],log);self._call(['rosparam','load',str(ROOT/'navigation/scale_planner_bridge/config/{}.yaml'.format(episode['planner'])),'/scale_planner_bridge'],log)
        override = episode.get('_override_yaml')
        if override:
            override_path = Path(override)
            if not override_path.is_absolute():
                override_path = ROOT / override_path
            if not override_path.is_file():
                raise InfrastructureFailure('override yaml missing: {}'.format(override_path))
            self._call(['rosparam','load',str(override_path),'/scale_planner_bridge'],log)
        self._call(['rosparam','load',str(ROOT/'navigation/scale_planner_bridge/config/matrix_common.yaml'),'/scale_planner_bridge'],log);self._call(['rosparam','load',str(execution_file),'/scale_planner_bridge'],log);self._call(['rosparam','set','/scale_planner_bridge/smoke_duration',str(self.protocol['timing']['logical_duration'])],log)
        bridge_log=log.open('a');bridge=subprocess.Popen(['rosrun','scale_planner_bridge','planner_bridge_node'],cwd=ROOT,env=self.env,stdout=bridge_log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            end=time.monotonic()+10
            while time.monotonic()<end:
                if bridge.poll() is not None:raise RuntimeError('unexpected bridge exit')
                services=subprocess.run(['rosservice','list'],env=self.env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.splitlines()
                if '/initialize' in services and '/step' in services:break
                time.sleep(.05)
            else:raise RuntimeError('bridge service unavailable')
            smoke=subprocess.run([str(ROOT/'.venv/bin/python'),'navigation/scale_planner_bridge/scripts/planner_execution_smoke.py','--config',str(layout_file),'--trace-output',str(trace_file),'--allow-algorithm-outcome'],cwd=ROOT,env=self.env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=self.protocol['timing']['wall_timeout'])
            with log.open('a') as f:f.write(smoke.stdout)
            try:last=json.loads(smoke.stdout.splitlines()[-1])
            except (IndexError,json.JSONDecodeError):raise InfrastructureFailure('smoke output is malformed')
            if smoke.returncode==2 and last.get('fatal_kind')=='contract':raise ContractFailure(last.get('error','smoke contract failure'))
            if smoke.returncode:raise InfrastructureFailure('smoke process failed')
            if bridge.poll() is not None:raise InfrastructureFailure('unexpected bridge exit')
            summary=last;trace=json.loads(trace_file.read_text());return summary,trace
        finally:
            if bridge.poll() is None:bridge.send_signal(signal.SIGINT); 
            try:bridge.wait(timeout=5)
            except subprocess.TimeoutExpired:bridge.kill();bridge.wait(timeout=2)
            bridge_log.close()
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                services=subprocess.run(['rosservice','list'],env=self.env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.splitlines()
                if '/initialize' not in services and '/step' not in services:break
                time.sleep(.02)
            for artifact in (layout_file,execution_file,trace_file):
                try:artifact.unlink()
                except FileNotFoundError:pass

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('generate','preflight','run'));p.add_argument('--output',default=str(OUTPUT));p.add_argument('--workers',type=int,default=1,help='process workers for run');a=p.parse_args()
    if a.command!='run' and a.workers!=1:p.error('--workers applies only to run')
    r=generate() if a.command=='generate' else {'preflight':preflight,'run':run}[a.command](output=Path(a.output),**({'workers':a.workers} if a.command=='run' else {}));print(json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
