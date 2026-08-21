#!/usr/bin/env python3
"""Locked, resumable execution runner for the frozen synthetic RQ1 matrix."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import phase2_runner as base
from experiments.rq1_protocol import (canonical_hash, generate_layouts, load_yaml,
                                      make_schedule, validate_layouts, validate_protocol,
                                      write_schedule)

_BASE_EPISODE_RECORD = base._episode_record

PROTOCOL = ROOT / "configs/rq1/protocol.yaml"
LAYOUTS = ROOT / "configs/rq1/layouts.yaml"
SCHEDULE = ROOT / "configs/rq1/schedule.csv"
OUTPUT = ROOT / "data/rq1_synthetic"
CONTRACT = base.CONTRACT
PHASE1C_BASE = base.PHASE1C_BASE


def _rows(path):
    return base._rows(path)


def _atomic(path, text):
    return base._atomic(path, text)


def _csv_rows(rows):
    return [{key: str(value) for key, value in row.items()} for row in rows]


def _progress(states, raw_layout):
    """Final executed position projected onto the frozen path arc length."""
    points = [(float(p["x"]), float(p["y"])) for p in raw_layout["global_path"]]
    total = sum(math.hypot(bx - ax, by - ay) for (ax, ay), (bx, by) in zip(points, points[1:]))
    if total <= 0:
        raise base.ContractFailure("global path has zero length")
    x, y = float(states[-1]["x"]), float(states[-1]["y"])
    arc = 0.0
    best_distance, best_progress = float("inf"), 0.0
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length <= 0:
            continue
        fraction = min(1.0, max(0.0, ((x - ax) * dx + (y - ay) * dy) / (length * length)))
        px, py = ax + fraction * dx, ay + fraction * dy
        distance = math.hypot(x - px, y - py)
        if distance < best_distance:
            best_distance, best_progress = distance, arc + fraction * length
        arc += length
    return min(1.0, max(0.0, best_progress / total))


def _episode_record(episode, summary, trace, lock_hash, raw_layout, robot_spec):
    record = _BASE_EPISODE_RECORD(episode, summary, trace, lock_hash, raw_layout, robot_spec)
    record["normalized_path_progress"] = _progress(trace["execution_states"], raw_layout)
    return record


def _tr_config_check():
    dwa = load_yaml(ROOT / "navigation/scale_planner_bridge/config/dwa.yaml")
    tr = load_yaml(ROOT / "navigation/scale_planner_bridge/config/tr.yaml")
    candidate = {key: value for key, value in tr.items()}
    planner = dict(candidate["planner"])
    if planner.pop("use_dwa", None) is not False:
        raise RuntimeError("TR must set planner.use_dwa=false")
    candidate["planner"] = planner
    if candidate != dwa:
        raise RuntimeError("tr.yaml differs from dwa.yaml beyond planner.use_dwa=false")


def generate(protocol_path=PROTOCOL, layouts_path=LAYOUTS, schedule_path=SCHEDULE):
    protocol = validate_protocol(load_yaml(protocol_path))
    layouts = generate_layouts(protocol)
    schedule = make_schedule(protocol, layouts)
    layouts_path, schedule_path = Path(layouts_path), Path(schedule_path)
    if layouts_path.exists():
        if canonical_hash(load_yaml(layouts_path)) != canonical_hash(layouts):
            raise RuntimeError("refusing to replace frozen generated input: {}".format(layouts_path))
    else:
        _atomic(layouts_path, yaml.safe_dump(layouts, sort_keys=False))
    expected_schedule = _csv_rows(schedule)
    if schedule_path.exists():
        if canonical_hash(_rows(schedule_path)) != canonical_hash(expected_schedule):
            raise RuntimeError("refusing to replace frozen generated input: {}".format(schedule_path))
    else:
        write_schedule(schedule_path, schedule)
    return {"layouts": 40, "episodes": 880, "layouts_hash": canonical_hash(layouts), "schedule_hash": canonical_hash(_csv_rows(schedule))}


def static_preflight(protocol_path=PROTOCOL, layouts_path=LAYOUTS, schedule_path=SCHEDULE):
    protocol = validate_protocol(load_yaml(protocol_path))
    layouts = load_yaml(layouts_path)
    validate_layouts(layouts, protocol)
    rows = _rows(schedule_path)
    expected = make_schedule(protocol, layouts)
    if len(rows) != 880 or len({row["episode_id"] for row in rows}) != 880 or rows != _csv_rows(expected):
        raise RuntimeError("frozen schedule mismatch")
    if {row["planner"] for row in rows} != {"tr", "teb"}:
        raise RuntimeError("unexpected planner matrix")
    if {row["profile_id"] for row in rows} != {profile["id"] for profile in protocol["matrix"]["profiles"]}:
        raise RuntimeError("unexpected profile matrix")
    if sum(row["partition"] == "discovery" for row in rows) != 440 or sum(row["partition"] == "holdout" for row in rows) != 440:
        raise RuntimeError("partition count mismatch")
    timing = protocol["timing"]
    if not math.isclose(round(timing["planner_period"] / timing["execution_dt"]) * timing["execution_dt"], timing["planner_period"]):
        raise RuntimeError("planner/execution timing not divisible")
    _tr_config_check()
    if subprocess.run(["git", "merge-base", "--is-ancestor", PHASE1C_BASE, "HEAD"], cwd=ROOT).returncode:
        raise RuntimeError("Phase 1C base is not an ancestor of HEAD")
    return {"static": True, "protocol_hash": canonical_hash(protocol), "layouts_hash": canonical_hash(layouts),
            "schedule_hash": canonical_hash(rows), "matrix_episodes": 880, "tr_config_equivalence": True}


def _lock_paths():
    return [
        ROOT / "experiments/rq1_runner.py", ROOT / "experiments/rq1_protocol.py", ROOT / "analysis/rq1_report.py",
        ROOT / "experiments/phase2_runner.py", ROOT / "experiments/phase2_protocol.py",
        ROOT / "navigation/scale_planner_bridge/scripts/planner_execution_smoke.py",
        ROOT / "navigation/scale_planner_bridge/scripts/determinism_regression.py",
        ROOT / "navigation/scale_planner_bridge/src/planner_bridge_node.cpp",
        ROOT / "navigation/scale_planner_bridge/launch/planner_execution.launch",
        ROOT / "navigation/scale_planner_bridge/config/tr.yaml", ROOT / "navigation/scale_planner_bridge/config/teb.yaml",
        ROOT / "navigation/scale_planner_bridge/config/common.yaml", ROOT / "navigation/scale_planner_bridge/config/matrix_common.yaml",
        ROOT / "navigation/scale_planner_bridge/config/execution_e0.yaml", ROOT / "navigation/scale_planner_bridge/config/execution_e1.yaml",
        ROOT / "simulation/execution.py", ROOT / "simulation/geometry.py", ROOT / "simulation/maps.py",
    ]


def lock_core(static, evidence):
    return {"protocol_hash": static["protocol_hash"], "layouts_hash": static["layouts_hash"], "schedule_hash": static["schedule_hash"],
            "git_head": base._git_head(), "phase1c_base": PHASE1C_BASE,
            "code_hashes": {str(path.relative_to(ROOT)): base._hashfile(path) for path in _lock_paths()},
            "dependencies": base._dependency_versions(), "preflight": evidence}


def preflight(protocol_path=PROTOCOL, layouts_path=LAYOUTS, schedule_path=SCHEDULE, output=OUTPUT):
    """Engineering preflight; run before, and only before, a new RQ1 lock."""
    static = static_preflight(protocol_path, layouts_path, schedule_path)
    evidence = {"static": static}
    protocol = load_yaml(protocol_path)
    pilot = dict(load_yaml(ROOT / "configs/pilot.yaml")["layout"], layout_id="engineering_fixture")
    probe = base.RosExecutor(protocol, {"layouts": [pilot]}, Path(output) / "engineering_probe")
    try:
        probe.start()
        summary, trace = probe({"episode_id": "engineering_fixture__tr__e0", "partition": "engineering", "layout_id": "engineering_fixture", "planner": "tr", "profile_id": "e0", "_attempt": 1})
    finally:
        probe.close()
    if not all(summary.get(name) is True for name in CONTRACT) or not trace.get("execution_states"):
        raise RuntimeError("TR executor probe contract failure")
    evidence["batch_executor_probe"] = {"summary": summary, "trace_states": len(trace["execution_states"])}
    determinism = []
    for planner in ("tr", "teb"):
        for execution in ("e0", "e1"):
            command = [".venv/bin/python", "navigation/scale_planner_bridge/scripts/determinism_regression.py", "--planner", planner, "--execution", execution, "--runs", "2", "--tolerance", "1e-9"]
            result = base._run_checked(command, 120)
            if result["returncode"]:
                raise RuntimeError("determinism preflight failure")
            payload = json.loads(result["stdout"].splitlines()[-1])
            if payload["max_abs_difference"] > 1e-9:
                raise RuntimeError("determinism contract failure")
            determinism.append({"planner": planner, "execution": execution, "result": payload, "command": result})
    evidence["determinism"] = determinism
    evidence["contracts"] = {"timing": True, "feedback": True, "command_hold": True, "determinism": True}
    core = lock_core(static, evidence)
    lock = {"success": True, "lock_core": core, "lock_hash": canonical_hash(core), "created_at": base._now()}
    output = Path(output)
    _atomic(output / "preflight.json", json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    _atomic(output / "lock.json", json.dumps(lock, indent=2, sort_keys=True) + "\n")
    return lock


def run(protocol_path=PROTOCOL, layouts_path=LAYOUTS, schedule_path=SCHEDULE, output=OUTPUT, executor=None, workers=12):
    if workers < 1 or (executor is not None and workers != 1):
        raise ValueError("workers must be positive; an injected executor requires workers=1")
    output = Path(output)
    lock = json.loads((output / "lock.json").read_text())
    static = static_preflight(protocol_path, layouts_path, schedule_path)
    if canonical_hash(lock["lock_core"]) != lock["lock_hash"] or any(lock["lock_core"][key] != static[key] for key in ("protocol_hash", "layouts_hash", "schedule_hash")):
        raise RuntimeError("immutable lock drift")
    if any(base._hashfile(ROOT / path) != digest for path, digest in lock["lock_core"]["code_hashes"].items()):
        raise RuntimeError("source hash drift")
    episodes = _rows(output / "episodes.csv")
    if len(episodes) != len({row["episode_id"] for row in episodes}) or any(row.get("valid") != "true" or row.get("lock_hash") != lock["lock_hash"] for row in episodes):
        raise RuntimeError("terminal episode lock/validity mismatch")
    if any("normalized_path_progress" not in row for row in episodes):
        raise RuntimeError("terminal episode lacks normalized_path_progress")
    existing = {row["episode_id"]: row for row in episodes}
    todo = [row for row in _rows(schedule_path) if row["episode_id"] not in base._valid_done(output, lock["lock_hash"])]
    protocol, layouts = load_yaml(protocol_path), load_yaml(layouts_path)
    layout_by_id = {layout["layout_id"]: layout for layout in layouts["layouts"]}
    original = base._episode_record
    base._episode_record = _episode_record
    try:
        if workers == 1:
            base._run_serial(todo, protocol, layouts, output, lock["lock_hash"], layout_by_id, existing, executor)
        else:
            base._run_parallel(todo, protocol, layouts, output, lock["lock_hash"], layout_by_id, existing, workers)
    finally:
        base._episode_record = original
    return {"completed": len(base._valid_done(output, lock["lock_hash"])), "lock_hash": lock["lock_hash"], "workers": workers}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "validate", "preflight", "run"))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    if args.command != "run" and args.workers != 12:
        parser.error("--workers applies only to run")
    if args.command == "generate":
        result = generate()
    elif args.command == "validate":
        result = static_preflight()
    elif args.command == "preflight":
        result = preflight(output=Path(args.output))
    else:
        result = run(output=Path(args.output), workers=args.workers)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
