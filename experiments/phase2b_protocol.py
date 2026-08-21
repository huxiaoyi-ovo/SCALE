"""Deterministic calibration-only geometry and schedule helpers (no planners)."""
from __future__ import annotations
import copy, csv, math, random
from pathlib import Path
import yaml
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, box

from experiments import phase2_protocol as phase2

ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_PATH = ROOT / "configs/phase2b/calibration.yaml"
LAYOUTS_PATH = ROOT / "configs/phase2b/calibration_layouts.yaml"
SCHEDULE_PATH = ROOT / "configs/phase2b/calibration_schedule.csv"
PHASE2_LAYOUTS_PATH = ROOT / "configs/phase2/layouts.yaml"

canonical_hash = phase2.canonical_hash
load_yaml = phase2.load_yaml


def _resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def validate_calibration(calibration):
    cfg = calibration or load_yaml(CALIBRATION_PATH)
    if cfg.get("provenance") != "CALIBRATION ONLY - NEVER SCIENTIFIC DATA":
        raise ValueError("calibration provenance mismatch")
    p2 = phase2.validate_protocol(load_yaml(_resolve(cfg["phase2_reference"])))
    timing = cfg.get("timing", {})
    if (timing.get("planner_period"), timing.get("execution_dt"), timing.get("logical_duration"),
            timing.get("wall_timeout"), timing.get("external_xy_tolerance"), timing.get("external_yaw_tolerance")) != (
            p2["timing"]["planner_period"], p2["timing"]["execution_dt"], p2["timing"]["logical_duration"],
            p2["timing"]["wall_timeout"], p2["timing"]["external_xy_tolerance"], p2["timing"]["external_yaw_tolerance"]):
        raise ValueError("calibration timing contract differs from Phase 2")
    if cfg.get("robot", {}).get("footprint") != p2["robot"]["footprint"]:
        raise ValueError("calibration robot footprint differs from Phase 2")
    if cfg.get("external_termination", {}).get("source") != cfg["phase2_reference"]:
        raise ValueError("calibration external termination source mismatch")
    if cfg.get("collision", {}).get("truth") != "independent_footprint_collision":
        raise ValueError("calibration collision truth contract mismatch")
    g = cfg.get("layout_generation", {})
    if g.get("seed") != 20260823 or g.get("count") != 10:
        raise ValueError("calibration layout protocol mismatch")
    s = cfg.get("schedule", {})
    if s.get("seed") != 20260824 or s.get("episode_count") != 30:
        raise ValueError("calibration schedule mismatch")
    if s.get("condition_order") != ["dwa_current", "dwa_forward0", "teb_current"]:
        raise ValueError("calibration condition order mismatch")
    conditions = cfg.get("conditions", [])
    if [x.get("id") for x in conditions] != s.get("condition_order"):
        raise ValueError("calibration condition definitions mismatch")
    if [(x.get("profile_id"), x.get("planner"), x.get("override")) for x in conditions] != [
        ("e0", "dwa", None),
        ("e0", "dwa", "configs/phase2b/dwa_forward_point_zero.yaml"),
        ("e0", "teb", None),
    ]:
        raise ValueError("calibration planner/override contract mismatch")
    retry = cfg.get("failure_policy", {})
    if retry.get("infrastructure_retries") != 2 or retry.get("max_attempts_total") != 3:
        raise ValueError("calibration retry policy mismatch")
    if not retry.get("algorithm_outcomes_never_retry") or not retry.get("contract_failures_stop_study"):
        raise ValueError("calibration failure policy mismatch")
    gate = cfg.get("gate", {})
    if gate.get("valid_episodes_per_condition") != 10:
        raise ValueError("calibration gate count mismatch")
    if gate.get("pass_success_bounds") != {"dwa_forward0": [2, 8], "teb_current": [2, 9]}:
        raise ValueError("calibration gate bounds mismatch")
    if gate.get("dwa_current") != "descriptive_only":
        raise ValueError("calibration gate descriptive-only contract mismatch")
    return cfg


def _phase2(calibration):
    return phase2.validate_protocol(load_yaml(_resolve(validate_calibration(calibration)["phase2_reference"])))


def layout_fingerprint(layout):
    return canonical_hash(layout["obstacles"])


def frozen_layout_fingerprints(path=PHASE2_LAYOUTS_PATH):
    return {layout_fingerprint(x) for x in load_yaml(path)["layouts"]}


def generate_layouts(calibration=None, phase2_layouts_path=PHASE2_LAYOUTS_PATH):
    cfg = validate_calibration(calibration)
    p2 = _phase2(cfg)
    seed = cfg["layout_generation"]["seed"]
    count = cfg["layout_generation"]["count"]
    g = p2["layout_generation"]
    a, s, z = g["arena"], g["start"], g["goal"]
    rng = random.Random(seed)
    frozen = frozen_layout_fingerprints(phase2_layouts_path)
    out = []
    idx = 0
    while len(out) < count:
        idx += 1
        obs = phase2._candidate(rng, p2)
        if not obs:
            continue
        path = phase2._path(obs, p2)
        if not path:
            continue
        length = sum(math.hypot(b[0] - c[0], b[1] - c[1]) for c, b in zip(path, path[1:]))
        lo, hi = g["accepted_path_length_range"]
        if not lo <= length <= hi:
            continue
        if layout_fingerprint({"obstacles": obs}) in frozen:
            continue
        out.append({
            "layout_id": "calibration_{:02d}".format(len(out) + 1),
            "partition": "calibration",
            "candidate_index": idx,
            "candidate_seed": seed,
            "arena": a,
            "start": s,
            "goal": z,
            "obstacles": obs,
            "global_path": phase2._poses(path, s, z),
            "geometry_diagnostics": {
                "obstacle_count": len(obs),
                "grid_resolution": g["path_grid_resolution"],
                "inflation_radius": g["footprint_circumscribed_radius"] + g["path_safety_margin"],
                "path_length": round(length, 6),
            },
        })
    result = {
        "schema_version": 1,
        "layout_seed": seed,
        "generation": copy.deepcopy(g),
        "layouts": out,
    }
    result["generation"]["seed"] = seed
    result["generation"]["count"] = count
    result["generation"]["acceptance_rule"] = cfg["layout_generation"]["acceptance_rule"]
    result["generation"].pop("discovery_count", None)
    result["generation"].pop("holdout_count", None)
    validate_layouts(result, cfg)
    return result


def validate_layouts(layouts, calibration=None):
    cfg = validate_calibration(calibration)
    p2 = _phase2(cfg)
    g, a, s, z, _, inflate = phase2._params(p2)
    items = layouts.get("layouts", [])
    count = cfg["layout_generation"]["count"]
    if len(items) != count:
        raise ValueError("calibration layout count mismatch")
    if [x.get("layout_id") for x in items] != ["calibration_{:02d}".format(i) for i in range(1, count + 1)]:
        raise ValueError("calibration layout id mismatch")
    if any(x.get("partition") != "calibration" for x in items):
        raise ValueError("calibration layout partition mismatch")
    if len({layout_fingerprint(x) for x in items}) != count:
        raise ValueError("duplicate calibration layout fingerprint")
    overlap = frozen_layout_fingerprints() & {layout_fingerprint(x) for x in items}
    if overlap:
        raise ValueError("calibration layout overlaps frozen Phase 2 layout")
    footprint = p2["robot"]["footprint"]
    inset = box(inflate, inflate, a["width"] - inflate, a["height"] - inflate)

    def body_at(pose):
        body = box(-footprint["width"] / 2.0, -footprint["length"] / 2.0,
                   footprint["width"] / 2.0, footprint["length"] / 2.0)
        return translate(rotate(body, pose.get("yaw", 0.0), origin=(0, 0), use_radians=True),
                         xoff=pose["x"], yoff=pose["y"])

    for item in items:
        obs = [phase2._shape(x) for x in item["obstacles"]]
        if len(obs) != g["obstacle_count"] or item["start"] != s or item["goal"] != z:
            raise ValueError("calibration layout mismatch")
        for shape in obs:
            if shape.distance(phase2._pt(s)) < g["start_goal_exclusion"] or shape.distance(phase2._pt(z)) < g["start_goal_exclusion"]:
                raise ValueError("calibration endpoint exclusion")
            bounds = shape.bounds
            if (bounds[0] < g["boundary_margin"] or bounds[1] < g["boundary_margin"]
                    or bounds[2] > a["width"] - g["boundary_margin"] or bounds[3] > a["height"] - g["boundary_margin"]):
                raise ValueError("calibration obstacle boundary")
        if any(x.distance(y) < g["obstacle_separation"] for i, x in enumerate(obs) for y in obs[i + 1:]):
            raise ValueError("calibration obstacle separation")
        path = item["global_path"]
        pts = [(x["x"], x["y"]) for x in path]
        if len(pts) < 2 or pts[0] != (s["x"], s["y"]) or pts[-1] != (z["x"], z["y"]) or not all(math.isfinite(x["yaw"]) for x in path):
            raise ValueError("calibration path endpoint/yaw")
        if any(not inset.covers(LineString([p, q])) or any(LineString([p, q]).intersects(obstacle.buffer(inflate)) for obstacle in obs)
               for p, q in zip(pts, pts[1:])):
            raise ValueError("calibration continuous path clearance")
        endpoint_footprints = [body_at(e) for e in (s, z)]
        if any(body.intersects(obstacle) for body in endpoint_footprints for obstacle in obs):
            raise ValueError("calibration physical endpoint collision")
        length = sum(math.hypot(b[0] - c[0], b[1] - c[1]) for c, b in zip(pts, pts[1:]))
        lo, hi = g["accepted_path_length_range"]
        if not lo <= length <= hi:
            raise ValueError("calibration path length")
    return True


def make_schedule(calibration=None, layouts=None):
    cfg = validate_calibration(calibration)
    layouts = layouts or load_yaml(LAYOUTS_PATH)
    validate_layouts(layouts, cfg)
    rows = []
    for layout in layouts["layouts"]:
        for condition in cfg["conditions"]:
            rows.append({
                "episode_id": "{}__{}".format(layout["layout_id"], condition["id"]),
                "layout_id": layout["layout_id"],
                "condition": condition["id"],
                "planner": condition["planner"],
                "profile_id": condition.get("profile_id", "e0"),
                "_override_yaml": condition.get("override") or "",
            })
    random.Random(cfg["schedule"]["seed"]).shuffle(rows)
    for index, row in enumerate(rows, 1):
        row["schedule_index"] = index
    validate_schedule(rows, cfg, layouts)
    return rows


def validate_schedule(rows, calibration=None, layouts=None):
    cfg = validate_calibration(calibration)
    layouts = layouts or load_yaml(LAYOUTS_PATH)
    validate_layouts(layouts, cfg)
    if len(rows) != 30 or len({row["episode_id"] for row in rows}) != 30:
        raise ValueError("calibration schedule count/duplicate mismatch")
    if [row.get("schedule_index") for row in rows] != list(range(1, 31)):
        raise ValueError("calibration schedule index mismatch")
    expected = {
        "{}__{}".format(layout["layout_id"], condition["id"])
        for layout in layouts["layouts"]
        for condition in cfg["conditions"]
    }
    if {row["episode_id"] for row in rows} != expected:
        raise ValueError("calibration schedule cell mismatch")
    by_condition = {x["id"]: x for x in cfg["conditions"]}
    for row in rows:
        condition = by_condition[row["condition"]]
        if row["planner"] != condition["planner"] or row["profile_id"] != condition.get("profile_id", "e0"):
            raise ValueError("calibration schedule condition mismatch")
        if row.get("_override_yaml", "") != (condition.get("override") or ""):
            raise ValueError("calibration schedule override mismatch")
    for condition in cfg["conditions"]:
        if sum(row["condition"] == condition["id"] for row in rows) != 10:
            raise ValueError("calibration schedule condition count mismatch")
    return True


def write_schedule(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("schedule_index", "episode_id", "layout_id", "condition", "planner", "profile_id", "_override_yaml"))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def write_layouts(path, layouts):
    _atomic(path, yaml.safe_dump(layouts, sort_keys=False))


def generate(calibration_path=CALIBRATION_PATH, layouts_path=LAYOUTS_PATH, schedule_path=SCHEDULE_PATH):
    cfg = validate_calibration(load_yaml(calibration_path))
    layouts = generate_layouts(cfg)
    write_layouts(layouts_path, layouts)
    rows = make_schedule(cfg, layouts)
    write_schedule(schedule_path, rows)
    return {
        "layouts": len(layouts["layouts"]),
        "episodes": len(rows),
        "layouts_hash": canonical_hash(layouts),
        "schedule_hash": canonical_hash(rows),
    }


def load_layouts(path=LAYOUTS_PATH):
    return load_yaml(path)


def load_schedule(path=SCHEDULE_PATH):
    import csv
    with Path(path).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        row["schedule_index"] = int(row["schedule_index"])
    return rows
