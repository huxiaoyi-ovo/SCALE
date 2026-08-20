import json
from pathlib import Path
import yaml
from experiments.runner import run
from simulation.execution import IdealExecution
from simulation.geometry import footprint
from simulation.maps import load_layout
from simulation.simulator import Simulator


def _layout():
    return load_layout({"layout_id": "unit", "arena": {"width": 4, "height": 4},
                        "start": {"x": 0, "y": 0, "yaw": 0}, "goal": {"x": 1, "y": 0, "yaw": 0}, "obstacles": []})


def test_simulator_is_deterministic_and_records_t0():
    sequence = [{"type": "forward", "speed": 1, "duration": .2}]
    layout, shape = _layout(), footprint({"type": "rectangle", "width": .1, "length": .1})
    one = Simulator(layout, IdealExecution(), shape, .1, .2).run(sequence)
    two = Simulator(layout, IdealExecution(), shape, .1, .2).run(sequence)
    assert one == two and one[0]["time"] == 0 and one[-1]["x"] == 0.2


def test_runner_artifacts_metadata_and_metrics(tmp_path):
    profiles = tmp_path / "profiles.yaml"
    profiles.write_text(yaml.safe_dump({"profiles": {"ideal": {"delay": 0, "tau_x": 0, "tau_y": 0, "tau_w": 0},
        "mild_lag": {"delay": .1, "tau_x": .1, "tau_y": .1, "tau_w": .1}}}))
    config = {"execution_profile": "mild_lag", "execution_profiles": str(profiles), "layout": {"layout_id": "unit",
        "arena": {"width": 2, "height": 2}, "start": {"x": 0, "y": 0}, "goal": {"x": .2, "y": 0}, "obstacles": []},
        "dt": .1, "duration": .2, "robot_footprint": {"type": "rectangle", "width": .1, "length": .1},
        "seed": 7, "output_directory": str(tmp_path / "data"), "scripted_commands": [{"type": "forward", "speed": 1, "duration": .2}]}
    paths = run(config)
    repeated_paths = run(config)
    required_metadata = {"run_id", "execution_model", "execution_profile", "layout", "seed", "git_commit", "timestamp", "valid"}
    metric_names = {"duration", "path_length", "minimum_clearance", "collision", "final_position_error", "final_yaw_error"}
    for path in paths:
        assert {"config.yaml", "metadata.json", "trajectory.csv", "metrics.json", "trajectory.png"} <= {p.name for p in Path(path).iterdir()}
        assert set(json.loads((Path(path) / "metadata.json").read_text())) == required_metadata
        assert set(json.loads((Path(path) / "metrics.json").read_text())) == metric_names
        resolved = yaml.safe_load((Path(path) / "config.yaml").read_text())
        assert "execution_profile_parameters" in resolved
    for first, repeated in zip(paths, repeated_paths):
        assert (Path(first) / "trajectory.csv").read_text() == (Path(repeated) / "trajectory.csv").read_text()
