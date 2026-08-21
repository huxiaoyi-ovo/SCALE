import csv
from pathlib import Path

import yaml

from analysis.phase2_report import analyze, paired_bootstrap
from experiments import phase2_protocol
import json
import experiments.phase2_runner as runner
from experiments.phase2_runner import (RosExecutor, classify_failure, generate,
                                       static_preflight)


ROOT = Path(__file__).resolve().parents[1]


def test_layout_generation_is_fixed_and_balanced():
    first, second = phase2_protocol.generate_layouts(), phase2_protocol.generate_layouts()
    assert first == second
    assert len(first["layouts"]) == 40
    assert sum(item["partition"] == "discovery" for item in first["layouts"]) == 20
    assert all(len(item["obstacles"]) == 6 and item["global_path"] for item in first["layouts"])
    frozen = yaml.safe_load((ROOT / "configs/phase2/layouts.yaml").read_text())
    assert frozen == first


def test_schedule_is_exact_full_matrix(tmp_path):
    protocol = yaml.safe_load((ROOT / "configs/phase2/protocol.yaml").read_text())
    layouts = phase2_protocol.generate_layouts()
    schedule = phase2_protocol.make_schedule(protocol, layouts)
    assert len(schedule) == len({row["episode_id"] for row in schedule}) == 880
    assert {row["planner"] for row in schedule} == {"dwa", "teb"}
    assert {row["profile_id"] for row in schedule} == {item["id"] for item in protocol["matrix"]["profiles"]}


def test_one_factor_schema_and_terminal_retry_classification():
    protocol = yaml.safe_load((ROOT / "configs/phase2/protocol.yaml").read_text())
    phase2_protocol.validate_protocol(protocol)
    assert classify_failure({"time_contract": True, "feedback_contract": True, "command_hold_contract": True,
                             "collision": True, "planner_failures": 0, "reason": "footprint_collision"}) == "algorithm"
    assert classify_failure(error="service unavailable") == "infrastructure"
    assert classify_failure({"time_contract": False}) == "contract"


def test_bootstrap_is_reproducible_and_paired():
    values = [-1.0, 0.0, 2.0, 3.0]
    assert paired_bootstrap(values, seed=7, resamples=100) == paired_bootstrap(values, seed=7, resamples=100)
    assert paired_bootstrap(values, seed=7, resamples=100)[0] == 1.0


def test_generate_and_static_preflight(tmp_path):
    layouts, schedule, output = tmp_path / "layouts.yaml", tmp_path / "schedule.csv", tmp_path / "out"
    result = generate(ROOT / "configs/phase2/protocol.yaml", layouts, schedule)
    assert result["episodes"] == 880
    check = static_preflight(ROOT / "configs/phase2/protocol.yaml", layouts, schedule)
    assert check["static"] and check["matrix_episodes"] == 880


def test_report_refuses_incomplete_input(tmp_path):
    core = {"code_hashes": {}, "preflight": {"contracts": {"timing": True, "feedback": True, "command_hold": True, "collision": True, "determinism": True}}}
    (tmp_path / "lock.json").write_text(json.dumps({"success": True, "lock_core": core, "lock_hash": phase2_protocol.canonical_hash(core)}))
    (tmp_path / "episodes.csv").write_text("episode_id,lock_hash,valid\none,locked,true\n")
    try:
        analyze(tmp_path)
    except RuntimeError as error:
        assert "880" in str(error)
    else:
        raise AssertionError("incomplete report input was accepted")


def test_ros_executor_command_plan_is_protocol_bound(tmp_path):
    protocol = yaml.safe_load((ROOT / "configs/phase2/protocol.yaml").read_text())
    layouts = phase2_protocol.generate_layouts(protocol)
    executor = RosExecutor(protocol, layouts, tmp_path)
    assert executor.core is None
    assert executor.layouts["discovery_01"]["global_path"][0]["x"] == 0.6


def test_ros_executor_close_without_start_is_safe(tmp_path):
    protocol = yaml.safe_load((ROOT / "configs/phase2/protocol.yaml").read_text())
    executor = RosExecutor(protocol, phase2_protocol.generate_layouts(protocol), tmp_path)
    executor.close()


def _summary(reason="external_tolerance", **extra):
    value = {"success": reason == "external_tolerance", "reason": reason, "collision": False,
             "planner_failures": 0, "planner_calls": 1, "execution_steps": 1,
             "final_xy_error": 0.0, "final_yaw_error": 0.0,
             "time_contract": True, "feedback_contract": True, "command_hold_contract": True,
             "compute_seconds": {"mean": 0.0, "max": 0.0}}
    value.update(extra); return value


def _run_fixture(monkeypatch, tmp_path, executor):
    episode = {"episode_id": "one", "partition": "discovery", "layout_id": "discovery_01", "planner": "dwa", "profile_id": "e0"}
    static = {"protocol_hash": "p", "layouts_hash": "l", "schedule_hash": "s"}
    core = {"protocol_hash": "p", "layouts_hash": "l", "schedule_hash": "s"}
    lock = {"success": True, "lock_core": core, "lock_hash": runner.canonical_hash(core)}
    (tmp_path / "lock.json").write_text(json.dumps(lock))
    monkeypatch.setattr(runner, "static_preflight", lambda *a, **k: static)
    original_rows = runner._rows
    monkeypatch.setattr(runner, "_rows", lambda path: [episode] if str(path).endswith("schedule.csv") else original_rows(path))
    return runner.run(output=tmp_path, executor=executor)


def test_runner_retries_infrastructure_at_most_three(monkeypatch, tmp_path):
    calls = []
    def fail(_): calls.append(1); raise RuntimeError("transport")
    try: _run_fixture(monkeypatch, tmp_path, fail)
    except RuntimeError as error: assert "retry exhaustion" in str(error)
    else: raise AssertionError("retry exhaustion missing")
    assert len(calls) == 3


def test_runner_transient_infra_then_algorithm_once(monkeypatch, tmp_path):
    calls = []
    def mixed(_):
        calls.append(1)
        if len(calls) == 1: raise RuntimeError("transport")
        return _summary("logical_timeout"), {"execution_states": [{"x": .6, "y": 2., "yaw": 0., "time": 1}]}
    assert _run_fixture(monkeypatch, tmp_path, mixed)["completed"] == 1
    assert len(calls) == 2


def test_runner_contract_is_immediate(monkeypatch, tmp_path):
    calls=[]
    def bad(_): calls.append(1); return _summary(time_contract=False), {"execution_states": []}
    try: _run_fixture(monkeypatch, tmp_path, bad)
    except RuntimeError as error: assert "contract failure" in str(error)
    else: raise AssertionError("contract accepted")
    assert len(calls) == 1


def test_runner_resume_requires_readable_matching_trace(monkeypatch, tmp_path):
    calls=[]
    def done(_): calls.append(1); return _summary(), {"execution_states": [{"x": .6, "y": 2., "yaw": 0., "time": 1}]}
    _run_fixture(monkeypatch, tmp_path, done)
    assert _run_fixture(monkeypatch, tmp_path, lambda _: (_ for _ in ()).throw(AssertionError("should skip")))["completed"] == 1
    assert len(calls) == 1


def test_runner_refuses_lock_source_drift(monkeypatch, tmp_path):
    episode = {"episode_id": "one", "partition": "discovery", "layout_id": "x", "planner": "dwa", "profile_id": "e0"}
    core = {"protocol_hash": "old", "layouts_hash": "l", "schedule_hash": "s"}
    (tmp_path / "lock.json").write_text(json.dumps({"success": True, "lock_core": core, "lock_hash": runner.canonical_hash(core)}))
    monkeypatch.setattr(runner, "static_preflight", lambda *a, **k: {"protocol_hash":"new","layouts_hash":"l","schedule_hash":"s"})
    monkeypatch.setattr(runner, "_rows", lambda path: [episode] if str(path).endswith("schedule.csv") else [])
    try: runner.run(output=tmp_path, executor=lambda _: None)
    except RuntimeError as error: assert "drift" in str(error)
    else: raise AssertionError("drift accepted")


def test_report_builds_real_figures_from_complete_locked_fixture(tmp_path):
    protocol = yaml.safe_load((ROOT / "configs/phase2/protocol.yaml").read_text())
    schedule = phase2_protocol.make_schedule(protocol, phase2_protocol.generate_layouts(protocol))
    core = {"protocol_hash": "p", "layouts_hash": "l", "schedule_hash": "s", "git_head": "g", "phase1c_base": "b778f11", "code_hashes": {}, "preflight": {"contracts": {"timing": True, "feedback": True, "command_hold": True, "collision": True, "determinism": True}}}
    fixture_hash = phase2_protocol.canonical_hash(core)
    lock = {"success": True, "lock_hash": fixture_hash, "lock_core": core}; (tmp_path / "lock.json").write_text(json.dumps(lock))
    (tmp_path / "traces").mkdir()
    fields = list(schedule[0]) + ["lock_hash", "valid", "success", "reason", "collision", "planner_failures", "final_time", "path_length", "min_clearance", "final_xy_error", "time_contract", "feedback_contract", "command_hold_contract", "collision_truth_contract"]
    with (tmp_path / "episodes.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for i, row in enumerate(schedule):
            item = dict(row, lock_hash=fixture_hash, valid="true", success="true", reason="external_tolerance", collision="false", planner_failures="0", final_time="5.0", path_length=str(4.8+i%3*.01), min_clearance="0.2", final_xy_error="0.01", time_contract="true", feedback_contract="true", command_hold_contract="true", collision_truth_contract="true")
            writer.writerow(item)
            import gzip
            with gzip.open(tmp_path / "traces" / (row["episode_id"] + ".json.gz"), "wt") as trace: json.dump({"execution_states": []}, trace)
    result = analyze(tmp_path, resamples=10)
    assert result["episodes"] == 880
    analysis = tmp_path / "analysis"
    for name in ("success_rates", "failure_modes", "paired_degradation", "interaction_contrasts", "outcome_heatmap"):
        assert (analysis / (name + ".png")).exists() and (analysis / (name + ".pdf")).exists()
    assert (analysis / "figure_source_episodes.csv").exists() and (analysis / "figure_manifest.json").exists()
    assert "See CSV source data" not in (analysis / "REPORT.md").read_text()
