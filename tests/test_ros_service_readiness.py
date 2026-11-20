import subprocess

import pytest

from navigation.scale_planner_bridge.scripts import determinism_regression


def test_wait_for_services_bounds_a_hanging_command(monkeypatch):
    def hang(command, *, timeout, **kwargs):
        assert 0.0 < timeout <= 1.0
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(determinism_regression.subprocess, "run", hang)

    with pytest.raises(RuntimeError, match="planner bridge services did not start"):
        determinism_regression.wait_for_services({}, timeout=1.0)


def test_wait_for_services_uses_the_remaining_budget(monkeypatch):
    clock = [0.0]
    timeouts = []

    def run(command, *, timeout, **kwargs):
        timeouts.append(timeout)
        clock[0] += 0.25
        services = "/initialize\n/step\n" if len(timeouts) == 2 else "/initialize\n"
        return subprocess.CompletedProcess(command, returncode=0, stdout=services)

    def sleep(duration):
        clock[0] += duration

    monkeypatch.setattr(determinism_regression.subprocess, "run", run)
    monkeypatch.setattr(determinism_regression.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(determinism_regression.time, "sleep", sleep)

    determinism_regression.wait_for_services({}, timeout=1.0)

    assert timeouts == pytest.approx([1.0, 0.7])
