import signal
import subprocess
from types import SimpleNamespace

import pytest

from navigation.scale_planner_bridge.scripts import determinism_regression


@pytest.mark.parametrize("group_already_gone", [False, True])
def test_timed_out_launcher_cleanup_covers_its_process_group(group_already_gone, monkeypatch):
    events = []
    pid = 123

    def wait(timeout):
        events.append(("wait", timeout))
        if timeout == 5.0:
            raise subprocess.TimeoutExpired("roslaunch", timeout)

    def kill_group(group, sig):
        events.append(("group", group, sig))
        if group_already_gone:
            raise ProcessLookupError

    process = SimpleNamespace(
        pid=pid, poll=lambda: None, wait=wait,
        send_signal=lambda sig: events.append(("signal", sig)),
    )
    monkeypatch.setattr(determinism_regression.os, "killpg", kill_group)

    determinism_regression.stop(process)

    assert events == [
        ("signal", signal.SIGINT), ("wait", 5.0), ("group", pid, signal.SIGKILL), ("wait", 2.0),
    ]
