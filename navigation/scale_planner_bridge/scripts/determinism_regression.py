#!/usr/bin/env python3
"""Restart the DWA bridge repeatedly and compare complete deterministic traces."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[3]
SMOKE = ROOT / "navigation" / "scale_planner_bridge" / "scripts" / "dwa_e0_smoke.py"
PYTHON = ROOT / ".venv" / "bin" / "python"


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_port(port, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("ROS master did not start")


def wait_for_services(environment, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(["rosservice", "list"], env=environment, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        services = set(result.stdout.splitlines())
        if {"/initialize", "/step"} <= services:
            return
        time.sleep(0.05)
    raise RuntimeError("planner bridge services did not start")


def stop(process):
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)


def log_tail(path, lines=40):
    if not path.exists():
        return ""
    return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])


def compare(reference, candidate, tolerance, path="trace"):
    if isinstance(reference, bool) or isinstance(candidate, bool):
        if reference is not candidate:
            raise AssertionError("{} differs: {} != {}".format(path, reference, candidate))
        return 0.0
    if isinstance(reference, (int, float)) and isinstance(candidate, (int, float)):
        difference = abs(float(reference) - float(candidate))
        if difference > tolerance:
            raise AssertionError("{} differs by {}".format(path, difference))
        return difference
    if isinstance(reference, dict) and isinstance(candidate, dict):
        if reference.keys() != candidate.keys():
            raise AssertionError("{} keys differ".format(path))
        return max((compare(reference[key], candidate[key], tolerance, path + "." + key)
                    for key in reference), default=0.0)
    if isinstance(reference, list) and isinstance(candidate, list):
        if len(reference) != len(candidate):
            raise AssertionError("{} lengths differ".format(path))
        return max((compare(left, right, tolerance, "{}[{}]".format(path, index))
                    for index, (left, right) in enumerate(zip(reference, candidate))), default=0.0)
    if reference != candidate:
        raise AssertionError("{} differs: {} != {}".format(path, reference, candidate))
    return 0.0


def run_once(index, directory, environment):
    trace_path = directory / "run_{:02d}.json".format(index)
    launch_log = directory / "launch_{:02d}.log".format(index)
    with launch_log.open("w") as log:
        launch = subprocess.Popen(["roslaunch", "scale_planner_bridge", "dwa_e0_bridge.launch"],
                                  env=environment, stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True)
        try:
            wait_for_services(environment)
            result = subprocess.run([str(PYTHON), str(SMOKE), "--trace-output", str(trace_path)],
                                    cwd=str(ROOT), env=environment, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30.0)
            if result.returncode != 0:
                raise RuntimeError("smoke run {} failed:\n{}\n{}".format(
                    index, result.stdout, log_tail(launch_log)))
            summary = json.loads(result.stdout.strip().splitlines()[-1])
            if not summary["time_contract"] or not summary["feedback_contract"]:
                raise RuntimeError("run {} did not verify timing and feedback".format(index))
        finally:
            stop(launch)
    return json.loads(trace_path.read_text()), summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--tolerance", type=float, default=1e-9)
    args = parser.parse_args()
    if args.runs < 2 or args.tolerance < 0:
        raise ValueError("runs must be at least two and tolerance must be non-negative")
    if not PYTHON.exists():
        raise RuntimeError("project .venv is required")

    port = free_port()
    environment = os.environ.copy()
    environment.update({"ROS_MASTER_URI": "http://127.0.0.1:{}".format(port),
                        "ROS_IP": "127.0.0.1"})
    with tempfile.TemporaryDirectory(prefix="scale_determinism_") as temporary:
        directory = Path(temporary)
        core_log = directory / "roscore.log"
        with core_log.open("w") as log:
            core = subprocess.Popen(["roscore", "-p", str(port)], env=environment,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                wait_for_port(port)
                reference, first_summary = run_once(1, directory, environment)
                maximum_difference = 0.0
                for index in range(2, args.runs + 1):
                    candidate, _ = run_once(index, directory, environment)
                    maximum_difference = max(maximum_difference,
                                             compare(reference, candidate, args.tolerance))
            finally:
                stop(core)

    result = {"success": True, "runs": args.runs, "tolerance": args.tolerance,
              "max_abs_difference": maximum_difference,
              "planner_calls": first_summary["planner_calls"],
              "execution_steps": first_summary["execution_steps"],
              "termination": first_summary["reason"]}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
