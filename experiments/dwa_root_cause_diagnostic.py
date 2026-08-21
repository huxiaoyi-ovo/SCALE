#!/usr/bin/env python3
"""Locked six-episode DWA root-cause diagnostic; old Phase-2 inputs are read-only."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import phase2_runner as phase2
from experiments.phase2_protocol import canonical_hash, load_yaml, validate_protocol, validate_layouts


PROTOCOL = ROOT / "configs/phase2/protocol.yaml"
SOURCE_LAYOUTS = ROOT / "configs/phase2/layouts.yaml"
DWA_CONFIG = ROOT / "navigation/scale_planner_bridge/config/dwa.yaml"
OVERRIDE = ROOT / "configs/diagnostics/dwa_no_dynamic_window.yaml"
OUTPUT = ROOT / "data/dwa_root_cause_diagnostic"
SELECTED = ("discovery_01", "discovery_02", "discovery_03")
KINK = {"x": 0.65, "y": 1.95}


def _derived_layouts(source):
    """Return original-path A and index-1-removed B copies for three frozen layouts."""
    by_id = {item["layout_id"]: item for item in source.get("layouts", [])}
    if tuple(layout_id for layout_id in SELECTED if layout_id in by_id) != SELECTED:
        raise RuntimeError("frozen diagnostic layouts are missing")
    result = []
    for source_id in SELECTED:
        original = copy.deepcopy(by_id[source_id])
        path = original["global_path"]
        if len(path) < 3 or {key: path[1].get(key) for key in KINK} != KINK:
            raise RuntimeError("unexpected frozen start-path kink: " + source_id)

        variant_a = copy.deepcopy(original)
        variant_a["layout_id"] = source_id + "__original_path"
        result.append(variant_a)

        variant_b = copy.deepcopy(original)
        variant_b["layout_id"] = source_id + "__start_kink_removed"
        del variant_b["global_path"][1]
        if len(variant_b["global_path"]) != len(path) - 1:
            raise RuntimeError("smoothed path length invariant failed: " + source_id)
        if variant_b["global_path"] != path[:1] + path[2:]:
            raise RuntimeError("smoothed path did not remove only index 1: " + source_id)
        comparable_original = copy.deepcopy(original)
        comparable_original["layout_id"] = variant_b["layout_id"]
        if any(variant_b[key] != comparable_original[key] for key in variant_b if key != "global_path"):
            raise RuntimeError("smoothed layout changed a non-path field: " + source_id)
        result.append(variant_b)
    return {"layouts": result}


def _validate(protocol, source, derived):
    protocol = validate_protocol(protocol)
    if load_yaml(OVERRIDE) != {"planner": {"use_dwa": False}}:
        raise RuntimeError("Variant A override must contain only planner.use_dwa=false")
    # Verify the three direct replacements retain the original protocol's
    # continuous-path geometry constraints without editing the frozen source.
    geometry_probe = copy.deepcopy(source)
    probe_by_id = {item["layout_id"]: item for item in geometry_probe["layouts"]}
    for item in derived["layouts"]:
        if item["layout_id"].endswith("__start_kink_removed"):
            source_id = item["layout_id"][: -len("__start_kink_removed")]
            probe_by_id[source_id]["global_path"] = copy.deepcopy(item["global_path"])
    validate_layouts(geometry_probe, protocol)
    e0 = [profile for profile in protocol["matrix"]["profiles"] if profile["id"] == "e0"]
    if len(e0) != 1 or e0[0].get("backend") != "e0":
        raise RuntimeError("frozen E0 profile mismatch")


def _schedule(derived):
    rows = []
    for index, source_id in enumerate(SELECTED, 1):
        rows.append({
            "schedule_index": 2 * index - 1,
            "episode_id": source_id + "__dwa__no_dynamic_window__e0",
            "partition": "diagnostic",
            "layout_id": source_id + "__original_path",
            "source_layout_id": source_id,
            "variant": "A_no_dynamic_window",
            "planner": "dwa",
            "profile_id": "e0",
            "_override_yaml": str(OVERRIDE.relative_to(ROOT)),
        })
        rows.append({
            "schedule_index": 2 * index,
            "episode_id": source_id + "__dwa__start_kink_removed__e0",
            "partition": "diagnostic",
            "layout_id": source_id + "__start_kink_removed",
            "source_layout_id": source_id,
            "variant": "B_start_kink_removed",
            "planner": "dwa",
            "profile_id": "e0",
        })
    if len(rows) != 6 or {row["episode_id"] for row in rows}.__len__() != 6:
        raise RuntimeError("diagnostic schedule must contain exactly six unique episodes")
    if {row["layout_id"] for row in rows} != {item["layout_id"] for item in derived["layouts"]}:
        raise RuntimeError("diagnostic schedule/layout mismatch")
    return rows


def _lock(protocol, source, derived, schedule):
    paths = (
        Path(__file__).resolve(),
        ROOT / "experiments/phase2_runner.py",
        ROOT / "experiments/phase2_protocol.py",
        DWA_CONFIG,
        OVERRIDE,
        ROOT / "navigation/scale_planner_bridge/config/common.yaml",
        ROOT / "navigation/scale_planner_bridge/config/matrix_common.yaml",
        ROOT / "navigation/scale_planner_bridge/scripts/planner_execution_smoke.py",
        ROOT / "navigation/scale_planner_bridge/src/planner_bridge_node.cpp",
    )
    core = {
        "study": "dwa_root_cause_diagnostic",
        "selected_source_layout_ids": list(SELECTED),
        "protocol_hash": canonical_hash(protocol),
        "source_layouts_hash": canonical_hash(source),
        "derived_layouts_hash": canonical_hash(derived),
        "schedule_hash": canonical_hash(schedule),
        "git_head": phase2._git_head(),
        "code_hashes": {str(path.relative_to(ROOT)): phase2._hashfile(path) for path in paths},
    }
    return {"success": True, "lock_core": core, "lock_hash": canonical_hash(core)}


def _load_or_create_lock(output, lock):
    path = Path(output) / "diagnostic_lock.json"
    if path.exists():
        if json.loads(path.read_text()) != lock:
            raise RuntimeError("immutable diagnostic lock drift")
    else:
        phase2._atomic(path, json.dumps(lock, indent=2, sort_keys=True) + "\n")


def _existing_rows(output, lock_hash, schedule):
    rows = phase2._rows(Path(output) / "episodes.csv")
    expected = {row["episode_id"]: row for row in schedule}
    if len(rows) != len({row.get("episode_id") for row in rows}):
        raise RuntimeError("duplicate terminal diagnostic episodes")
    for row in rows:
        episode = expected.get(row.get("episode_id"))
        if episode is None or row.get("valid") != "true" or row.get("lock_hash") != lock_hash:
            raise RuntimeError("terminal diagnostic lock or schedule mismatch")
        for field in ("layout_id", "source_layout_id", "variant", "planner", "profile_id"):
            if row.get(field) != episode[field]:
                raise RuntimeError("terminal diagnostic field mismatch: " + field)
    return {row["episode_id"]: row for row in rows}


def inputs():
    protocol = load_yaml(PROTOCOL)
    source = load_yaml(SOURCE_LAYOUTS)
    derived = _derived_layouts(source)
    _validate(protocol, source, derived)
    return protocol, source, derived, _schedule(derived)


def validate():
    protocol, source, derived, schedule = inputs()
    return {
        "valid": True,
        "episodes": len(schedule),
        "selected_source_layout_ids": list(SELECTED),
        "source_layouts_hash": canonical_hash(source),
        "derived_layouts_hash": canonical_hash(derived),
        "schedule_hash": canonical_hash(schedule),
        "variant_a": "planner.use_dwa=false only",
        "variant_b": "delete global_path index 1 only",
    }


def run(output=OUTPUT, workers=12):
    if workers < 1:
        raise ValueError("workers must be at least one")
    protocol, source, derived, schedule = inputs()
    out = Path(output)
    lock = _lock(protocol, source, derived, schedule)
    _load_or_create_lock(out, lock)
    existing_by_id = _existing_rows(out, lock["lock_hash"], schedule)
    done = phase2._valid_done(out, lock["lock_hash"])
    if not done.issubset({row["episode_id"] for row in schedule}):
        raise RuntimeError("completed episode outside diagnostic schedule")
    todo = [row for row in schedule if row["episode_id"] not in done]
    layout_by_id = {item["layout_id"]: item for item in derived["layouts"]}
    if workers == 1:
        phase2._run_serial(todo, protocol, derived, out, lock["lock_hash"], layout_by_id, existing_by_id)
    else:
        phase2._run_parallel(todo, protocol, derived, out, lock["lock_hash"], layout_by_id, existing_by_id, workers)
    return {"completed": len(phase2._valid_done(out, lock["lock_hash"])), "episodes": len(schedule),
            "lock_hash": lock["lock_hash"], "workers": min(workers, len(schedule))}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "run"))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args(argv)
    if args.command == "validate":
        result = validate()
    else:
        result = run(output=Path(args.output), workers=args.workers)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
