import pytest

from experiments import runner
from experiments.logger import write_run


def test_failed_plot_leaves_no_valid_run_marker(tmp_path, monkeypatch):
    config = runner._load(runner.PROJECT_ROOT / "configs/pilot.yaml")
    config["execution_profiles"] = str(runner.PROJECT_ROOT / config["execution_profiles"])
    config["output_directory"] = str(tmp_path)

    def fail_plot(*args):
        raise OSError("plot write failed")

    monkeypatch.setattr(runner, "_plot", fail_plot)

    with pytest.raises(OSError, match="plot write failed"):
        runner.run(config)

    reserved = tmp_path / "run_0001"
    assert reserved.is_dir()
    assert not (reserved / "metadata.json").exists()


def test_failed_trajectory_write_leaves_no_valid_run_marker(tmp_path):
    (tmp_path / "trajectory.csv").mkdir()

    with pytest.raises(OSError):
        write_run(tmp_path, {}, {"valid": True}, [{"x": 0.0}], {})

    assert not (tmp_path / "metadata.json").exists()
