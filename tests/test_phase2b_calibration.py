import csv
import gzip
import json
from pathlib import Path

import pytest
import yaml

from experiments import phase2b_protocol as protocol
from experiments.phase2b_calibration import gate, run, static_hash
from experiments.phase2_runner import classify_failure


ROOT = Path(__file__).resolve().parents[1]


def _summary(success=True):
    return {
        "success": success,
        "reason": "external_tolerance" if success else "logical_timeout",
        "collision": False,
        "planner_failures": 0,
        "planner_calls": 1,
        "execution_steps": 1,
        "final_xy_error": 0.0,
        "final_yaw_error": 0.0,
        "time_contract": True,
        "feedback_contract": True,
        "command_hold_contract": True,
        "compute_seconds": {"mean": 0.0, "max": 0.0},
    }


def _trace_state():
    return {"execution_states": [{"x": 0.6, "y": 2.0, "yaw": 0.0, "time": 0.0}]}


def test_layouts_and_schedule_are_deterministic_new_and_non_overlapping():
    first = protocol.generate_layouts()
    second = protocol.generate_layouts()
    assert first == second
    assert len(first["layouts"]) == 10
    assert [item["layout_id"] for item in first["layouts"]] == [
        "calibration_{:02d}".format(i) for i in range(1, 11)
    ]
    frozen = yaml.safe_load((ROOT / "configs/phase2/layouts.yaml").read_text())
    assert not ({protocol.layout_fingerprint(item) for item in first["layouts"]}
                & {protocol.layout_fingerprint(item) for item in frozen["layouts"]})
    cfg = protocol.load_yaml(protocol.CALIBRATION_PATH)
    schedule = protocol.make_schedule(cfg, first)
    assert len(schedule) == len({row["episode_id"] for row in schedule}) == 30
    for condition in cfg["conditions"]:
        assert sum(row["condition"] == condition["id"] for row in schedule) == 10


def test_override_yaml_contains_only_forward_point_distance():
    override = yaml.safe_load((ROOT / "configs/phase2b/dwa_forward_point_zero.yaml").read_text())
    assert list(override) == ["planner"]
    assert list(override["planner"]) == ["forward_point_distance"]
    assert override["planner"]["forward_point_distance"] == 0.0


def _write_terminal(output, successes_by_condition, calibration_hash=None,
                    missing=0, duplicate=False, bad_contract=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    calibration_hash = calibration_hash or static_hash()
    rows = protocol.load_schedule()
    if missing:
        rows = rows[:-missing]
    if duplicate:
        rows = rows + [dict(rows[0])]
    grouped = {}
    for row in rows:
        grouped.setdefault(row["condition"], []).append(row)
    episode_rows = []
    for condition, condition_rows in grouped.items():
        successes = successes_by_condition.get(condition, 0)
        for index, row in enumerate(condition_rows):
            item = dict(row)
            item.pop("_override_yaml", None)
            item.update(
                valid="true",
                calibration_hash=calibration_hash,
                success="true" if index < successes else "false",
                time_contract="true",
                feedback_contract="true",
                command_hold_contract="true",
                collision_truth_contract="true",
                normalized_path_progress="0.5",
            )
            if bad_contract and row["episode_id"] == bad_contract:
                item["time_contract"] = "false"
            episode_rows.append(item)
    fields = ("episode_id", "layout_id", "condition", "planner", "profile_id",
              "schedule_index", "valid", "calibration_hash", "success",
              "time_contract", "feedback_contract", "command_hold_contract",
              "collision_truth_contract", "normalized_path_progress")
    with (output / "episodes.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(episode_rows)
    (output / "traces").mkdir(parents=True, exist_ok=True)
    for row in episode_rows:
        with gzip.open(output / "traces" / (row["episode_id"] + ".json.gz"), "wt") as trace:
            json.dump({"execution_states": []}, trace)


def test_gate_pass_and_fail_boundaries(tmp_path):
    pass_output = tmp_path / "pass"
    _write_terminal(pass_output, {"dwa_forward0": 2, "teb_current": 9})
    passed = gate(output=pass_output)
    assert passed["pass"] and passed["status"] == "pass"
    assert passed["counts"]["dwa_forward0"]["success"] == 2
    assert passed["counts"]["teb_current"]["success"] == 9

    pass_upper = tmp_path / "pass_upper"
    _write_terminal(pass_upper, {"dwa_forward0": 8, "teb_current": 2})
    assert gate(output=pass_upper)["pass"] is True

    fail_low = tmp_path / "fail_low"
    _write_terminal(fail_low, {"dwa_forward0": 1, "teb_current": 9})
    assert gate(output=fail_low)["pass"] is False

    fail_high = tmp_path / "fail_high"
    _write_terminal(fail_high, {"dwa_forward0": 8, "teb_current": 10})
    assert gate(output=fail_high)["pass"] is False


def test_gate_refuses_incomplete_duplicate_and_contract_invalid_data(tmp_path):
    incomplete = tmp_path / "incomplete"
    _write_terminal(incomplete, {}, missing=1)
    with pytest.raises(RuntimeError, match="incomplete"):
        gate(output=incomplete)

    duplicate = tmp_path / "duplicate"
    _write_terminal(duplicate, {}, duplicate=True)
    with pytest.raises(RuntimeError, match="duplicate"):
        gate(output=duplicate)

    invalid = tmp_path / "invalid"
    _write_terminal(invalid, {}, bad_contract="calibration_01__dwa_current")
    with pytest.raises(RuntimeError, match="contract"):
        gate(output=invalid)


def test_retry_classification_reuses_proven_phase2_rule():
    assert classify_failure({"time_contract": True, "feedback_contract": True,
                             "command_hold_contract": True, "collision": True,
                             "planner_failures": 0, "reason": "logical_timeout"}) == "algorithm"
    assert classify_failure(error="transport") == "infrastructure"
    assert classify_failure({"time_contract": False}) == "contract"


def test_run_infrastructure_retry_limit(tmp_path):
    calls = []

    def executor(_):
        calls.append(1)
        raise RuntimeError("transport")

    with pytest.raises(RuntimeError, match="retry exhaustion"):
        run(output=tmp_path / "infra", executor=executor)
    assert len(calls) == 3
    attempts = list(csv.DictReader((tmp_path / "infra" / "attempts.csv").open(newline="")))
    assert len(attempts) == 3
    assert all(row["status"] == "infrastructure" for row in attempts)


def test_run_is_resumable_without_replaying_terminal_outcomes(tmp_path):
    calls = []

    def executor(_):
        calls.append(1)
        return _summary(), _trace_state()

    output = tmp_path / "resume"
    assert run(output=output, executor=executor)["completed"] == 30
    assert len(calls) == 30
    calls.clear()
    assert run(output=output, executor=executor)["completed"] == 30
    assert len(calls) == 0


def test_resume_refuses_incomplete_terminal_artifacts(tmp_path):
    output = tmp_path / "incomplete_artifacts"
    _write_terminal(output, {})
    next((output / "traces").glob("*.json.gz")).unlink()

    with pytest.raises(RuntimeError, match="trace missing or invalid"):
        run(output=output, executor=lambda _: (_summary(), _trace_state()))


def test_resume_never_replays_orphan_algorithm_attempt(tmp_path):
    output = tmp_path / "orphan_algorithm"
    output.mkdir(parents=True)
    first = protocol.load_schedule()[0]
    with (output / "attempts.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("timestamp", "episode_id", "attempt", "status", "detail"))
        writer.writeheader()
        writer.writerow({"timestamp": "t", "episode_id": first["episode_id"], "attempt": 1,
                         "status": "algorithm", "detail": "logical_timeout"})

    with pytest.raises(RuntimeError, match="terminal attempt lacks complete artifacts"):
        run(output=output, executor=lambda _: (_summary(), _trace_state()))
