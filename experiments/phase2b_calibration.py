#!/usr/bin/env python3
"""Deterministic calibration-only runner and gate for the Phase 2B baseline-viability check."""
from __future__ import annotations
import argparse, csv, gzip, json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import phase2_runner
from experiments.phase2_protocol import canonical_hash, load_yaml
from experiments.phase2_runner import (
    ContractFailure,
    RosExecutor,
    _atomic,
    _episode_record,
    _rows,
    _trace,
    classify_failure,
)
from experiments.phase2b_protocol import (
    CALIBRATION_PATH,
    LAYOUTS_PATH,
    SCHEDULE_PATH,
    load_layouts,
    load_schedule,
    validate_calibration,
    validate_layouts,
    validate_schedule,
)

CONTRACT_FIELDS = ("time_contract", "feedback_contract", "command_hold_contract", "collision_truth_contract")


def _resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def _output_path(calibration, output):
    if output is not None:
        return Path(output)
    return ROOT / calibration["outputs"]["root"]


def _atomic_append(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _rows(path)
    rows.append(row)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(row))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _attempt_count(output, episode_id):
    return sum(row["episode_id"] == episode_id for row in _rows(Path(output) / "attempts.csv"))


def _assert_resume_safe(output, terminal_rows, pending_rows):
    output = Path(output)
    for row in terminal_rows:
        trace_path = output / "traces" / (row["episode_id"] + ".json.gz")
        try:
            with gzip.open(trace_path, "rt") as stream:
                json.load(stream)
        except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
            raise RuntimeError("terminal trace missing or invalid: " + row["episode_id"]) from error
    pending_ids = {row["episode_id"] for row in pending_rows}
    for attempt in _rows(output / "attempts.csv"):
        if attempt["episode_id"] in pending_ids and attempt.get("status") != "infrastructure":
            raise RuntimeError("terminal attempt lacks complete artifacts: " + attempt["episode_id"])


def normalized_path_progress(trace, layout):
    """Nearest-point final-position arc-length projection / stored path length, clipped [0,1]."""
    states = trace.get("execution_states", [])
    if not states:
        return 0.0
    final = (float(states[-1]["x"]), float(states[-1]["y"]))
    points = [(float(point["x"]), float(point["y"])) for point in layout["global_path"]]
    if len(points) < 2:
        return 0.0
    segment_lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    total = float(layout.get("geometry_diagnostics", {}).get("path_length", 0.0) or 0.0)
    if total <= 0.0:
        total = sum(segment_lengths)
    if total <= 0.0:
        return 0.0
    best_arc = 0.0
    best_distance = float("inf")
    arc_before = 0.0
    for (ax, ay), (bx, by), segment_length in zip(points, points[1:], segment_lengths):
        dx, dy = bx - ax, by - ay
        if segment_length > 0.0:
            ratio = min(1.0, max(0.0, ((final[0] - ax) * dx + (final[1] - ay) * dy) / (segment_length * segment_length)))
        else:
            ratio = 0.0
        projection = (ax + ratio * dx, ay + ratio * dy)
        distance = math.hypot(final[0] - projection[0], final[1] - projection[1])
        arc = arc_before + ratio * segment_length
        if distance < best_distance:
            best_distance = distance
            best_arc = arc
        arc_before += segment_length
    return min(1.0, max(0.0, best_arc / total))


def static_hash(calibration_path=CALIBRATION_PATH, layouts_path=LAYOUTS_PATH, schedule_path=SCHEDULE_PATH):
    cfg = validate_calibration(load_yaml(calibration_path))
    layouts = load_layouts(layouts_path)
    validate_layouts(layouts, cfg)
    rows = load_schedule(schedule_path)
    validate_schedule(rows, cfg, layouts)
    return canonical_hash({"calibration": cfg, "layouts": layouts, "schedule": rows})


def _validate_terminal_rows(rows, expected_rows, calibration_hash, require_complete=False):
    expected_ids = {row["episode_id"] for row in expected_rows}
    if len({row["episode_id"] for row in rows}) != len(rows):
        raise RuntimeError("duplicate terminal episodes")
    if not {row["episode_id"] for row in rows}.issubset(expected_ids):
        raise RuntimeError("terminal episode set differs from calibration schedule")
    if require_complete and (len(rows) != len(expected_ids) or {row["episode_id"] for row in rows} != expected_ids):
        raise RuntimeError("incomplete terminal episodes")
    if any(key.startswith("_") for row in rows for key in row):
        raise RuntimeError("private scheduling field found in terminal episodes CSV")
    expected_by_id = {row["episode_id"]: row for row in expected_rows}
    for row in rows:
        if row.get("valid") != "true" or row.get("calibration_hash") != calibration_hash:
            raise RuntimeError("terminal episode validity or calibration hash mismatch")
        expected = expected_by_id[row["episode_id"]]
        for field in ("layout_id", "condition", "planner", "profile_id"):
            if row.get(field) != expected[field]:
                raise RuntimeError("terminal episode schedule mismatch: " + field)
        if str(row.get("schedule_index", "")) != str(expected["schedule_index"]):
            raise RuntimeError("terminal episode schedule index mismatch")
        if any(row.get(field) != "true" for field in CONTRACT_FIELDS):
            raise RuntimeError("terminal episode violates a calibration contract")
        if row.get("normalized_path_progress") is None:
            raise RuntimeError("terminal episode lacks normalized path progress")


def run(calibration_path=CALIBRATION_PATH, layouts_path=LAYOUTS_PATH, schedule_path=SCHEDULE_PATH,
        output=None, executor=None):
    cfg = validate_calibration(load_yaml(calibration_path))
    layouts = load_layouts(layouts_path)
    validate_layouts(layouts, cfg)
    rows = load_schedule(schedule_path)
    validate_schedule(rows, cfg, layouts)
    out = _output_path(cfg, output)
    calibration_hash = static_hash(calibration_path, layouts_path, schedule_path)
    terminal = _rows(out / "episodes.csv")
    _validate_terminal_rows(terminal, rows, calibration_hash, require_complete=False)
    done = {row["episode_id"] for row in terminal}
    todo = [row for row in rows if row["episode_id"] not in done]
    _assert_resume_safe(out, terminal, todo)
    protocol = load_yaml(_resolve(cfg["phase2_reference"]))
    layout_by_id = {item["layout_id"]: item for item in layouts["layouts"]}
    owned = executor is None
    executor = executor or RosExecutor(protocol, layouts, out)
    if owned:
        executor.start()
    try:
        for episode in todo:
            while True:
                attempt = _attempt_count(out, episode["episode_id"]) + 1
                call_episode = dict(episode, _attempt=attempt)
                try:
                    summary, trace = executor(call_episode)
                except ContractFailure as error:
                    _atomic_append(out / "attempts.csv", {"timestamp": phase2_runner._now(), "episode_id": episode["episode_id"],
                                                          "attempt": attempt, "status": "contract", "detail": str(error)})
                    raise RuntimeError("contract failure: " + episode["episode_id"])
                except Exception as error:
                    _atomic_append(out / "attempts.csv", {"timestamp": phase2_runner._now(), "episode_id": episode["episode_id"],
                                                          "attempt": attempt, "status": "infrastructure", "detail": str(error)})
                    if attempt >= 3:
                        raise RuntimeError("infrastructure retry exhaustion: " + episode["episode_id"])
                    continue
                kind = classify_failure(summary)
                if kind == "contract":
                    _atomic_append(out / "attempts.csv", {"timestamp": phase2_runner._now(), "episode_id": episode["episode_id"],
                                                          "attempt": attempt, "status": "contract", "detail": summary.get("reason", "")})
                    raise RuntimeError("contract failure: " + episode["episode_id"])
                try:
                    record = _episode_record(episode, summary, trace, calibration_hash, layout_by_id[episode["layout_id"]],
                                             protocol["robot"]["footprint"])
                    record["normalized_path_progress"] = round(normalized_path_progress(trace, layout_by_id[episode["layout_id"]]), 6)
                    record["calibration_hash"] = calibration_hash
                    record.pop("lock_hash", None)
                except ContractFailure as error:
                    _atomic_append(out / "attempts.csv", {"timestamp": phase2_runner._now(), "episode_id": episode["episode_id"],
                                                          "attempt": attempt, "status": "contract", "detail": str(error)})
                    raise RuntimeError("contract failure: " + episode["episode_id"])
                except Exception as error:
                    _atomic_append(out / "attempts.csv", {"timestamp": phase2_runner._now(), "episode_id": episode["episode_id"],
                                                          "attempt": attempt, "status": "infrastructure", "detail": str(error)})
                    if attempt >= 3:
                        raise RuntimeError("infrastructure retry exhaustion: " + episode["episode_id"])
                    continue
                _atomic_append(out / "attempts.csv", {"timestamp": phase2_runner._now(), "episode_id": episode["episode_id"],
                                                      "attempt": attempt, "status": kind, "detail": summary.get("reason", "")})
                _trace(out, episode["episode_id"], trace)
                _atomic_append(out / "episodes.csv", record)
                break
        completed = len(done) + len(todo)
        _atomic(out / "calibration.json", json.dumps({"success": True, "calibration_hash": calibration_hash, "completed": completed}, sort_keys=True) + "\n")
        return {"completed": completed, "calibration_hash": calibration_hash}
    finally:
        if owned:
            executor.close()


def gate(calibration_path=CALIBRATION_PATH, layouts_path=LAYOUTS_PATH, schedule_path=SCHEDULE_PATH,
         output=None):
    cfg = validate_calibration(load_yaml(calibration_path))
    rows = load_schedule(schedule_path)
    validate_schedule(rows, cfg, load_layouts(layouts_path))
    out = _output_path(cfg, output)
    calibration_hash = static_hash(calibration_path, layouts_path, schedule_path)
    terminal = _rows(out / "episodes.csv")
    _validate_terminal_rows(terminal, rows, calibration_hash, require_complete=True)
    for row in terminal:
        trace_path = out / "traces" / (row["episode_id"] + ".json.gz")
        if not trace_path.exists():
            raise RuntimeError("terminal trace missing: " + row["episode_id"])
        try:
            with gzip.open(trace_path, "rt") as stream:
                json.load(stream)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("terminal trace invalid: " + row["episode_id"]) from error
    by_condition = {condition["id"]: condition for condition in cfg["conditions"]}
    counts = {}
    for condition_id, condition in by_condition.items():
        matching = [row for row in terminal if row["condition"] == condition_id]
        if len(matching) != 10:
            raise RuntimeError("condition episode count mismatch: " + condition_id)
        if any(row["planner"] != condition["planner"] for row in matching):
            raise RuntimeError("condition planner mismatch: " + condition_id)
        counts[condition_id] = {"valid": len(matching), "success": sum(row["success"] == "true" for row in matching)}
    bounds = cfg["gate"]["pass_success_bounds"]
    passed = (bounds["dwa_forward0"][0] <= counts["dwa_forward0"]["success"] <= bounds["dwa_forward0"][1]
              and bounds["teb_current"][0] <= counts["teb_current"]["success"] <= bounds["teb_current"][1])
    return {
        "pass": passed,
        "status": "pass" if passed else "stop",
        "counts": counts,
        "episodes": len(terminal),
        "calibration_hash": calibration_hash,
    }


def generate(calibration_path=CALIBRATION_PATH, layouts_path=LAYOUTS_PATH, schedule_path=SCHEDULE_PATH):
    from experiments.phase2b_protocol import generate as protocol_generate
    return protocol_generate(calibration_path, layouts_path, schedule_path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "run", "gate"))
    parser.add_argument("--output", default=None)
    parser.add_argument("--calibration", default=str(CALIBRATION_PATH))
    parser.add_argument("--layouts", default=str(LAYOUTS_PATH))
    parser.add_argument("--schedule", default=str(SCHEDULE_PATH))
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = generate(args.calibration, args.layouts, args.schedule)
        elif args.command == "run":
            result = run(args.calibration, args.layouts, args.schedule, args.output)
        else:
            result = gate(args.calibration, args.layouts, args.schedule, args.output)
    except (RuntimeError, ValueError) as error:
        print(json.dumps({"pass": False, "status": "stop", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
