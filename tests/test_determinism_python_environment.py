import json
from pathlib import Path
import subprocess
import sys

from navigation.scale_planner_bridge.scripts import determinism_regression


def test_determinism_child_uses_the_running_interpreter(tmp_path, monkeypatch):
    summary = {
        "time_contract": True,
        "feedback_contract": True,
        "command_hold_contract": True,
        "execution_backend": "e0",
    }
    monkeypatch.setattr(determinism_regression.subprocess, "Popen", lambda *args, **kwargs: object())
    monkeypatch.setattr(determinism_regression, "wait_for_services", lambda *args: None)
    monkeypatch.setattr(determinism_regression, "stop", lambda *args: None)

    def run(command, **kwargs):
        assert command[0] == sys.executable
        Path(command[-1]).write_text("{}")
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(summary))

    monkeypatch.setattr(determinism_regression.subprocess, "run", run)

    _, result = determinism_regression.run_once(1, tmp_path, {}, "dwa", "e0")
    assert result == summary
