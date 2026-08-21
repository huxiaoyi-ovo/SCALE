#!/usr/bin/env python3
"""Locked, resumable E0 screen for DWAPlannerROS without Dynamic Window."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import phase2_runner as phase2
from experiments.phase2_protocol import canonical_hash, load_yaml


PLANNER = "dwa"
CONDITION = "dwa_rollout_no_dynamic_window"
PROTOCOL = ROOT / "configs/phase2/protocol.yaml"
LAYOUTS = ROOT / "configs/phase2b/calibration_layouts.yaml"
OVERRIDE = ROOT / "configs/diagnostics/dwa_no_dynamic_window.yaml"
BASE_CONFIG = ROOT / "navigation/scale_planner_bridge/config/dwa.yaml"
SMOKE = ROOT / "navigation/scale_planner_bridge/scripts/planner_execution_smoke.py"
BRIDGE = ROOT / "navigation/scale_planner_bridge/src/planner_bridge_node.cpp"
OUTPUT = ROOT / "data/rollout_candidate_screen/dwa_no_dynamic_window"


def _schedule(layouts):
    calibration = [item for item in layouts.get("layouts", []) if item.get("partition") == "calibration"]
    if len(calibration) != 10 or len({item.get("layout_id") for item in calibration}) != 10:
        raise RuntimeError("calibration layouts must contain exactly 10 unique calibration entries")
    return [
        {
            "schedule_index": index,
            "episode_id": "calibration__{}__{}__e0".format(item["layout_id"], CONDITION),
            "partition": "calibration",
            "layout_id": item["layout_id"],
            "planner": PLANNER,
            "profile_id": "e0",
            "condition": CONDITION,
            "_override_yaml": str(OVERRIDE.relative_to(ROOT)),
        }
        for index, item in enumerate(calibration, 1)
    ]


def _validate(protocol, layouts, schedule):
    expected_override = {"planner": {"use_dwa": False}}
    if load_yaml(OVERRIDE) != expected_override:
        raise RuntimeError("DWA rollout override must be exactly {!r}".format(expected_override))
    profile = next((item for item in protocol.get("matrix", {}).get("profiles", []) if item.get("id") == "e0"), None)
    if profile is None or profile.get("backend") != "e0":
        raise RuntimeError("protocol E0 profile mismatch")
    if len(schedule) != 10 or len({item["episode_id"] for item in schedule}) != 10:
        raise RuntimeError("screen schedule must contain exactly 10 unique episodes")
    if len({item["layout_id"] for item in schedule}) != 10:
        raise RuntimeError("screen schedule must contain exactly 10 unique layouts")
    if any(
        item["planner"] != PLANNER
        or item["profile_id"] != "e0"
        or item["condition"] != CONDITION
        or item.get("_override_yaml") != str(OVERRIDE.relative_to(ROOT))
        for item in schedule
    ):
        raise RuntimeError("screen schedule configuration mismatch")
    layout_ids = {item.get("layout_id") for item in layouts.get("layouts", [])}
    if {item["layout_id"] for item in schedule} != layout_ids:
        raise RuntimeError("screen schedule/layout set mismatch")


def _lock(protocol, layouts, schedule):
    paths = (
        BASE_CONFIG,
        OVERRIDE,
        ROOT / "navigation/scale_planner_bridge/config/common.yaml",
        ROOT / "navigation/scale_planner_bridge/config/matrix_common.yaml",
        ROOT / "experiments/phase2_runner.py",
        SMOKE,
        BRIDGE,
        Path(__file__).resolve(),
    )
    core = {
        "planner": PLANNER,
        "condition": CONDITION,
        "protocol_hash": canonical_hash(protocol),
        "layouts_hash": canonical_hash(layouts),
        "schedule_hash": canonical_hash(schedule),
        "git_head": phase2._git_head(),
        "code_hashes": {str(path.relative_to(ROOT)): phase2._hashfile(path) for path in paths},
    }
    return {"lock_core": core, "lock_hash": canonical_hash(core)}


def _load_or_create_lock(output, lock):
    path = output / "screen_lock.json"
    if path.exists():
        if json.loads(path.read_text()) != lock:
            raise RuntimeError("immutable screen lock drift")
    else:
        phase2._atomic(path, json.dumps(lock, indent=2, sort_keys=True) + "\n")


def _existing_rows(output, lock_hash, schedule):
    rows = phase2._rows(output / "episodes.csv")
    expected_ids = {episode["episode_id"] for episode in schedule}
    if len(rows) != len({row.get("episode_id") for row in rows}):
        raise RuntimeError("duplicate terminal episode rows")
    if any(row.get("episode_id") not in expected_ids for row in rows):
        raise RuntimeError("terminal row is outside the screen schedule")
    if any(row.get("valid") != "true" or row.get("lock_hash") != lock_hash for row in rows):
        raise RuntimeError("terminal episode lock/validity mismatch")
    return {row["episode_id"]: row for row in rows}


def _inputs():
    protocol = load_yaml(PROTOCOL)
    layouts = load_yaml(LAYOUTS)
    schedule = _schedule(layouts)
    _validate(protocol, layouts, schedule)
    return protocol, layouts, schedule


def validate():
    protocol, layouts, schedule = _inputs()
    lock = _lock(protocol, layouts, schedule)
    return {"valid": True, "episodes": len(schedule), "lock_hash": lock["lock_hash"]}


def run(output=OUTPUT, workers=12):
    if workers < 1:
        raise ValueError("workers must be at least one")
    protocol, layouts, schedule = _inputs()
    out = Path(output)
    lock = _lock(protocol, layouts, schedule)
    _load_or_create_lock(out, lock)
    existing_by_id = _existing_rows(out, lock["lock_hash"], schedule)
    done = phase2._valid_done(out, lock["lock_hash"])
    todo = [episode for episode in schedule if episode["episode_id"] not in done]
    layout_by_id = {item["layout_id"]: item for item in layouts["layouts"]}
    if workers == 1:
        phase2._run_serial(todo, protocol, layouts, out, lock["lock_hash"], layout_by_id, existing_by_id)
    else:
        phase2._run_parallel(todo, protocol, layouts, out, lock["lock_hash"], layout_by_id, existing_by_id, workers)
    return {"completed": len(phase2._valid_done(out, lock["lock_hash"])), "lock_hash": lock["lock_hash"],
            "condition": CONDITION, "workers": workers}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "run"))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    if args.command == "validate" and args.workers != 12:
        parser.error("--workers applies only to run")
    result = validate() if args.command == "validate" else run(output=Path(args.output), workers=args.workers)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
