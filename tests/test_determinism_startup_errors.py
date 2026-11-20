from pathlib import Path
import sys

import pytest

from navigation.scale_planner_bridge.scripts import determinism_regression


@pytest.fixture
def failed_startup(monkeypatch):
    stopped = []

    def launch(command, *, stdout, **kwargs):
        stdout.write("fixture error from " + command[0] + "\n")
        stdout.flush()
        return command[0]

    def wait(*args):
        raise RuntimeError("startup deadline expired")

    monkeypatch.setattr(determinism_regression.subprocess, "Popen", launch)
    monkeypatch.setattr(determinism_regression, "wait_for_services", wait)
    monkeypatch.setattr(determinism_regression, "wait_for_port", wait)
    monkeypatch.setattr(determinism_regression, "stop", stopped.append)
    return stopped


def test_bridge_startup_error_keeps_launcher_output(tmp_path, failed_startup):
    with pytest.raises(RuntimeError, match="smoke run 3 could not start") as failure:
        determinism_regression.run_once(3, tmp_path, {}, "dwa", "e0")

    assert "fixture error from roslaunch" in str(failure.value)
    assert failed_startup == ["roslaunch"]


def test_master_startup_error_keeps_roscore_output(monkeypatch, failed_startup):
    monkeypatch.setattr(sys, "argv", ["determinism_regression.py"])
    monkeypatch.setattr(determinism_regression, "PYTHON", Path(sys.executable))
    monkeypatch.setattr(determinism_regression, "free_port", lambda: 11311)

    with pytest.raises(RuntimeError, match="fixture error from roscore"):
        determinism_regression.main()

    assert failed_startup == ["roscore"]
