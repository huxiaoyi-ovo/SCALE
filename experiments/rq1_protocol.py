"""Frozen RQ1 geometry and schedule, derived only from the Phase-2 rules."""
from __future__ import annotations

import csv
import random
from pathlib import Path

from experiments import phase2_protocol as phase2

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "configs/rq1/protocol.yaml"

PROFILE_IDS = (
    "e0", "delay_050", "delay_100", "delay_200", "tau_x_100",
    "tau_x_300", "tau_y_150", "tau_y_300", "tau_y_500", "tau_w_100",
    "tau_w_300",
)


def canonical_hash(value):
    return phase2.canonical_hash(value)


def load_yaml(path):
    return phase2.load_yaml(path)


def profiles(protocol):
    return protocol["matrix"]["profiles"]


def validate_protocol(protocol):
    """Fail closed unless RQ1 changes only approved study metadata."""
    baseline = phase2.load_yaml(phase2.PROTOCOL_PATH)
    phase2.validate_protocol(baseline)
    if protocol["provenance"] != baseline["provenance"]:
        raise ValueError("provenance differs from Phase 2")
    if protocol["matrix"]["planners"] != ["tr", "teb"]:
        raise ValueError("RQ1 planners must be [tr, teb]")
    if tuple(item["id"] for item in profiles(protocol)) != PROFILE_IDS:
        raise ValueError("profile order differs from Phase 2")
    if profiles(protocol) != profiles(baseline):
        raise ValueError("profiles differ from Phase 2")
    if protocol["timing"] != baseline["timing"] or protocol["robot"] != baseline["robot"]:
        raise ValueError("timing or robot differs from Phase 2")
    geometry = dict(protocol["layout_generation"])
    phase2_geometry = dict(baseline["layout_generation"])
    if geometry.pop("seed") != 20260826 or phase2_geometry.pop("seed") != 20260820:
        raise ValueError("unexpected layout seed")
    if geometry != phase2_geometry:
        raise ValueError("geometry rules differ from Phase 2")
    if protocol["randomization"] != {"schedule_seed": 20260827, "schedule_rule": "deterministic_full_matrix_shuffle"}:
        raise ValueError("unexpected schedule seed/rule")
    if protocol["failure_policy"] != baseline["failure_policy"]:
        raise ValueError("failure policy differs from Phase 2")
    analysis = protocol["analysis"]
    if analysis["bootstrap"] != {"method": "paired_layout_percentile", "confidence_level": 0.95, "resamples": 5000, "seed": 20260828}:
        raise ValueError("unexpected RQ1 bootstrap contract")
    if analysis["partitions"] != ["discovery", "holdout"] or analysis["significance_tests"] is not False:
        raise ValueError("invalid RQ1 analysis partition contract")
    return protocol


def validate_layouts(layouts, protocol):
    phase2.validate_layouts(layouts, protocol)
    if layouts.get("layout_seed") != protocol["layout_generation"]["seed"]:
        raise ValueError("layout seed mismatch")
    ids = [item["layout_id"] for item in layouts["layouts"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate layout id")
    return True


def generate_layouts(protocol=None):
    protocol = validate_protocol(protocol or load_yaml(PROTOCOL_PATH))
    generation = protocol["layout_generation"]
    rng = random.Random(generation["seed"])
    layouts, candidate_index = [], 0
    while len(layouts) < 40:
        candidate_index += 1
        obstacles = phase2._candidate(rng, protocol)
        if not obstacles:
            continue
        path = phase2._path(obstacles, protocol)
        if not path:
            continue
        length = sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(path, path[1:]))
        lo, hi = generation["accepted_path_length_range"]
        if not lo <= length <= hi:
            continue
        partition = "discovery" if len(layouts) < 20 else "holdout"
        layouts.append({
            "layout_id": "{}_{:02d}".format(partition, len(layouts) % 20 + 1),
            "partition": partition,
            "candidate_index": candidate_index,
            "candidate_seed": generation["seed"],
            "arena": generation["arena"], "start": generation["start"], "goal": generation["goal"],
            "obstacles": obstacles,
            "global_path": phase2._poses(path, generation["start"], generation["goal"]),
            "geometry_diagnostics": {"obstacle_count": 6, "grid_resolution": generation["path_grid_resolution"],
                                     "inflation_radius": generation["footprint_circumscribed_radius"] + generation["path_safety_margin"],
                                     "path_length": round(length, 6)},
        })
    result = {"schema_version": 1, "layout_seed": generation["seed"], "generation": generation, "layouts": layouts}
    validate_layouts(result, protocol)
    return result


def make_schedule(protocol, layouts):
    rows = [{
        "episode_id": "{}__{}__{}__{}".format(layout["partition"], layout["layout_id"], planner, profile["id"]),
        "partition": layout["partition"], "layout_id": layout["layout_id"],
        "planner": planner, "profile_id": profile["id"],
    } for layout in layouts["layouts"] for planner in protocol["matrix"]["planners"] for profile in profiles(protocol)]
    random.Random(protocol["randomization"]["schedule_seed"]).shuffle(rows)
    for index, row in enumerate(rows, 1):
        row["schedule_index"] = index
    return rows


def write_schedule(path, rows):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("schedule_index", "episode_id", "partition", "layout_id", "planner", "profile_id"))
        writer.writeheader()
        writer.writerows(rows)
