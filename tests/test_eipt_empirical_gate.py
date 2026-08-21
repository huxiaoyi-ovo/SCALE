from pathlib import Path

import pytest
import yaml

from experiments.eipt_empirical_gate import (directional_margin, material_transition,
                                              restore_execution)
from simulation.execution import Command


ROOT = Path(__file__).resolve().parents[1]


def _command(vx=0.0, vy=0.0, wz=0.0):
    return {"vx": vx, "vy": vy, "wz": wz}


def test_material_transition_frozen_thresholds():
    frozen = yaml.safe_load((ROOT / "configs/eipt/protocol.yaml").read_text())["planner_response_transition"]

    assert not material_transition(_command(vx=0.10, vy=0.02), _command(vx=0.105, vy=0.018), frozen)
    assert not material_transition(_command(), _command(vx=0.34 * frozen["command_limits"]["vx"]), frozen)
    assert material_transition(_command(), _command(vx=0.35 * frozen["command_limits"]["vx"]), frozen)
    assert material_transition(_command(vy=0.20), _command(vy=-0.20), frozen)
    assert material_transition(_command(vx=0.20), _command(), frozen)


def test_directional_margin_resolves_boundary_or_censors():
    settings = {"coarse_radius_step": 0.25, "max_radius": 1.0,
                "bisection_radius_resolution": 0.03125, "no_transition_value": 2.0}
    margin, censored, queries = directional_margin(
        (0.0,), ((-1.0, 1.0),), ((1.0,),), lambda value: value[0] >= 0.60, settings)
    assert not censored
    assert margin == pytest.approx(0.60, abs=settings["bisection_radius_resolution"])
    assert queries > 0

    margin, censored, queries = directional_margin(
        (0.0,), ((-1.0, 1.0),), ((1.0,),), lambda _value: False, settings)
    assert (margin, censored) == (2.0, True)
    assert queries > 0


def test_restore_execution_rebuilds_delay_queue_from_history():
    snapshot = {
        "call_index": 3,
        "snapshot_time": 1.0,
        "executed": {"x": 1.2, "y": -0.4, "yaw": 0.3, "vx": 0.11, "vy": -0.07, "wz": 0.05},
    }
    trace = {"planner_calls": [
        {"simulation_time": 0.70, "command": _command(vx=9.0)},
        {"simulation_time": 0.80, "command": _command(vx=0.20, vy=0.10)},
        {"simulation_time": 0.90, "command": _command(vx=-0.10, wz=0.30)},
    ]}
    execution = restore_execution(snapshot, {"delay": 0.15, "tau_x": 0.1, "tau_y": 0.2, "tau_w": 0.3}, trace)

    assert execution.active_command == Command(vx=0.20, vy=0.10)
    assert list(execution._pending) == [(pytest.approx(0.05), Command(vx=-0.10, wz=0.30))]
    assert (execution.state.x, execution.state.y, execution.state.yaw,
            execution.state.vx, execution.state.vy, execution.state.wz) == pytest.approx(
                (1.2, -0.4, 0.3, 0.11, -0.07, 0.05))
