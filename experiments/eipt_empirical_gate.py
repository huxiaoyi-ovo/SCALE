#!/usr/bin/env python3
"""Frozen one-day EIPT empirical discrimination gate.

This module selects snapshots from immutable traces and evaluates black-box planner
margins.  It never runs new navigation episodes or changes planner parameters.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import multiprocessing as mp
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict, deque
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulation.execution import Command, FirstOrderExecution, Pose2D, State, _integrate
from simulation.geometry import footprint, minimum_clearance, transform_footprint
from simulation.maps import load_layout


PROTOCOL_PATH = ROOT / "configs/eipt/protocol.yaml"
OUTPUT = ROOT / "data/eipt_empirical_gate"
CONTRACT_FIELDS = ("time_contract", "feedback_contract", "command_hold_contract", "collision_truth_contract")
COMPONENTS = ("vx", "vy", "wz")
THETA = ("delay", "tau_x", "tau_y", "tau_w")


def _read_csv(path):
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def _load_trace(path):
    with gzip.open(path, "rt") as handle:
        return json.load(handle)


def _bool(value):
    if value not in ("true", "false"):
        raise RuntimeError("invalid boolean: {!r}".format(value))
    return value == "true"


def _stable_key(seed, *parts):
    value = "{}|{}".format(seed, "|".join(str(part) for part in parts))
    return hashlib.sha256(value.encode()).hexdigest()


def _command_vector(command, limits):
    return tuple(float(command[name]) / float(limits[name]) for name in COMPONENTS)


def _l2(values):
    return math.sqrt(sum(value * value for value in values))


def material_transition(reference, candidate, frozen):
    """Return whether two planner responses differ materially under the frozen rule."""
    if reference is None or candidate is None:
        return reference is not candidate
    limits = frozen["command_limits"]
    left, right = _command_vector(reference, limits), _command_vector(candidate, limits)
    if _l2(tuple(a - b for a, b in zip(left, right))) >= frozen["normalized_command_l2_change_min"] - 1e-12:
        return True
    threshold = frozen["reversal_component_magnitude_min"]
    if any(a * b < 0 and min(abs(a), abs(b)) >= threshold for a, b in zip(left, right)):
        return True

    def dominant(values):
        ordered = sorted(((abs(value), index) for index, value in enumerate(values)), reverse=True)
        if ordered[0][0] < frozen["dominant_component_magnitude_min"]:
            return None
        if ordered[1][0] > 0 and ordered[0][0] / ordered[1][0] < frozen["dominant_component_ratio_min"]:
            return None
        return ordered[0][1]

    left_mode, right_mode = dominant(left), dominant(right)
    if left_mode is not None and right_mode is not None and left_mode != right_mode:
        return True
    if _l2(left) >= frozen["collapse_reference_l2_min"] and _l2(right) <= frozen["collapse_candidate_l2_max"]:
        return True
    return False


def sequence_transition(reference, candidate, frozen):
    if len(reference) != len(candidate):
        raise ValueError("planner-response sequences must share a horizon")
    return any(material_transition(left, right, frozen) for left, right in zip(reference, candidate))


def _profile_map(source_name):
    path = ROOT / ("configs/rq1/protocol.yaml" if source_name == "rq1" else "configs/phase2/protocol.yaml")
    protocol = yaml.safe_load(path.read_text())
    result = {}
    for profile in protocol["matrix"]["profiles"]:
        result[profile["id"]] = {name: float(profile.get(name, 0.0)) for name in THETA}
    return result


def _path_progress(state, layout):
    points = [(float(item["x"]), float(item["y"])) for item in layout["global_path"]]
    lengths, total = [0.0], 0.0
    for left, right in zip(points, points[1:]):
        total += math.hypot(right[0] - left[0], right[1] - left[1])
        lengths.append(total)
    best_distance, best_arc = float("inf"), 0.0
    px, py = float(state["x"]), float(state["y"])
    for index, (left, right) in enumerate(zip(points, points[1:])):
        dx, dy = right[0] - left[0], right[1] - left[1]
        denominator = dx * dx + dy * dy
        ratio = 0.0 if denominator == 0 else max(0.0, min(1.0, ((px - left[0]) * dx + (py - left[1]) * dy) / denominator))
        x, y = left[0] + ratio * dx, left[1] + ratio * dy
        distance = math.hypot(px - x, py - y)
        if distance < best_distance:
            best_distance, best_arc = distance, lengths[index] + ratio * math.sqrt(denominator)
    return best_arc / total if total else 0.0


def _meaningful_signs(values, magnitude):
    return [(time_value, 1 if value > 0 else -1) for time_value, value in values if abs(value) >= magnitude]


def _trace_events(trace, layout, protocol):
    calls = trace["planner_calls"]
    limits = protocol["planner_response_transition"]["command_limits"]
    bad = protocol["bad_event"]
    progress = [_path_progress(call["executed"], layout) for call in calls]
    events = []
    terminal = trace["termination"]
    terminal_time = float(trace["execution_states"][-1]["time"])
    if terminal.get("collision"):
        events.append((terminal_time, "collision"))
    if int(terminal.get("planner_failures", 0)) > 0:
        events.append((terminal_time, "planner_failure"))

    collapse = bad["command_collapse"]
    run = 0
    collapse_active = False
    for index, call in enumerate(calls):
        norm = _l2(_command_vector(call["command"], limits))
        run = run + 1 if norm <= collapse["normalized_command_l2_max"] else 0
        condition = run >= int(collapse["sustained_cycles"]) and progress[index] < collapse["max_path_progress"]
        if condition and not collapse_active:
            events.append((float(call["simulation_time"]), "command_collapse"))
        collapse_active = condition

    stall = bad["progress_stall"]
    stall_active = False
    planner_period = float(trace["planner_period"])
    stall_steps = int(round(float(stall["lookback"]) / planner_period))
    for index, call in enumerate(calls):
        now = float(call["simulation_time"])
        previous = index - stall_steps
        condition = previous >= 0 and progress[index] < stall["max_path_progress"] and progress[index] - progress[previous] <= stall["normalized_progress_gain_max"]
        if condition and not stall_active:
            events.append((now, "progress_stall"))
        stall_active = condition

    oscillation = bad["oscillatory_reversal"]
    oscillation_active = {name: False for name in oscillation["components"]}
    oscillation_steps = int(round(float(oscillation["lookback"]) / planner_period))
    for index, call in enumerate(calls):
        first = max(0, index - oscillation_steps)
        for name in oscillation["components"]:
            values = [(float(item["simulation_time"]), float(item["command"][name]) / limits[name])
                      for item in calls[first:index + 1]]
            signs = _meaningful_signs(values, oscillation["normalized_component_magnitude_min"])
            changes = sum(left[1] != right[1] for left, right in zip(signs, signs[1:]))
            condition = changes >= int(oscillation["sign_changes_min"])
            if condition and not oscillation_active[name]:
                events.append((float(call["simulation_time"]), "oscillatory_reversal_{}".format(name)))
            oscillation_active[name] = condition
    return sorted(set(events)), progress


def _future_labels(events, time_value, window):
    mechanisms = sorted({mechanism for event_time, mechanism in events if time_value < event_time <= time_value + window + 1e-9})
    return mechanisms


def _snapshot_record(source, episode, trace_path, trace, layout, theta, call_index, events, progress):
    call = trace["planner_calls"][call_index]
    mechanisms = _future_labels(events, float(call["simulation_time"]), 2.0)
    previous = trace["planner_calls"][max(0, call_index - 1)]["command"]
    return {
        "source": source,
        "episode_id": episode["episode_id"],
        "partition": episode["partition"],
        "layout_id": episode["layout_id"],
        "layout_cluster": "{}:{}".format(source, episode["layout_id"]),
        "planner": episode["planner"],
        "profile_id": episode["profile_id"],
        "trace_path": str(trace_path.relative_to(ROOT)),
        "call_index": call_index,
        "snapshot_time": float(call["simulation_time"]),
        "normalized_path_progress": progress[call_index],
        "y_bad": bool(mechanisms),
        "mechanisms": mechanisms,
        "executed": call["executed"],
        "recorded_command": call["command"],
        "previous_command": previous,
        "theta": theta,
    }


def _source_records(name, settings, protocol):
    episodes_path = ROOT / settings["episodes"]
    traces_path = ROOT / settings["traces"]
    layouts = yaml.safe_load((ROOT / settings["layouts"]).read_text())
    layout_by_id = {item["layout_id"]: item for item in layouts["layouts"]}
    profiles = _profile_map(name)
    rows = _read_csv(episodes_path)
    if {row["lock_hash"] for row in rows} != {settings["expected_lock_hash"]}:
        raise RuntimeError("{} lock mismatch".format(name))
    allowed = set(settings["planners"])
    selected = [row for row in rows if row["planner"] in allowed]
    expected = 880 if name == "rq1" else 440
    if len(selected) != expected:
        raise RuntimeError("{} expected {} relevant episodes, found {}".format(name, expected, len(selected)))
    result = []
    for row in selected:
        if not _bool(row["valid"]) or not all(_bool(row[field]) for field in CONTRACT_FIELDS):
            raise RuntimeError("invalid source episode: {}".format(row["episode_id"]))
        trace_path = traces_path / (row["episode_id"] + ".json.gz")
        if not trace_path.is_file():
            raise RuntimeError("missing trace: {}".format(trace_path))
        result.append((name, row, trace_path, layout_by_id[row["layout_id"]], profiles[row["profile_id"]]))
    return result, layout_by_id


def _candidate_snapshots(protocol):
    bad_candidates, nominal_candidates = [], []
    layouts_by_source = {}
    sample = protocol["sampling"]
    warmup = int(sample["planner_warmup_cycles"])
    for source, settings in protocol["sources"].items():
        episodes, layouts_by_source[source] = _source_records(source, settings, protocol)
        for source_name, episode, trace_path, layout, theta in episodes:
            trace = _load_trace(trace_path)
            if not trace.get("planner_calls"):
                continue
            events, progress = _trace_events(trace, layout, protocol)
            calls = trace["planner_calls"]
            per_episode_bad = []
            for event_time, mechanism in events:
                target = event_time - sample["target_event_lead"]
                eligible = [(abs(float(call["simulation_time"]) - target), index) for index, call in enumerate(calls)
                            if index >= warmup and sample["event_lead_min"] - 1e-9 <= event_time - float(call["simulation_time"]) <= sample["event_lead_max"] + 1e-9]
                if not eligible:
                    continue
                index = min(eligible)[1]
                record = _snapshot_record(source_name, episode, trace_path, trace, layout, theta, index, events, progress)
                if record["y_bad"]:
                    record["center_event"] = mechanism
                    per_episode_bad.append(record)
            if per_episode_bad:
                per_episode_bad.sort(key=lambda row: (row["snapshot_time"], row["center_event"] != "collision", row["center_event"]))
                bad_candidates.append(per_episode_bad[0])

            if _bool(episode["success"]):
                stride = max(1, int(round(0.5 / float(trace["planner_period"]))))
                for index in range(warmup, len(calls), stride):
                    record = _snapshot_record(source_name, episode, trace_path, trace, layout, theta, index, events, progress)
                    if not record["y_bad"] and record["normalized_path_progress"] < 0.95:
                        nominal_candidates.append(record)
    return bad_candidates, nominal_candidates, layouts_by_source


def _choose(protocol, bad_candidates, nominal_candidates):
    sample = protocol["sampling"]
    seed = sample["seed"]
    selected = []
    for planner in sample["planners"]:
        for partition in sample["partitions"]:
            bad_pool = [row for row in bad_candidates if row["planner"] == planner and row["partition"] == partition]
            nominal_pool = [row for row in nominal_candidates if row["planner"] == planner and row["partition"] == partition]
            nominal_layouts = {row["layout_cluster"] for row in nominal_pool}
            layout_counts = Counter()

            def add_bad(rows, count):
                ordered = sorted(rows, key=lambda item: (item["layout_cluster"] in nominal_layouts,
                    _stable_key(seed, "bad", item["episode_id"])))
                for prior_layout_limit in (0, sample["max_snapshots_per_layout"] - 1):
                    for row in ordered:
                        if any(item["episode_id"] == row["episode_id"] for item in chosen_bad):
                            continue
                        if layout_counts[row["layout_cluster"]] > prior_layout_limit:
                            continue
                        chosen_bad.append(row); layout_counts[row["layout_cluster"]] += 1
                        if len(chosen_bad) >= count:
                            return

            chosen_bad = []
            if planner == "dwa":
                forced = [row for row in bad_pool if row["profile_id"] == "e0" and row["normalized_path_progress"] < 0.20]
                add_bad(forced, sample["dwa_coverage"]["min_e0_near_start_bad_per_partition"])
                if len(chosen_bad) < sample["dwa_coverage"]["min_e0_near_start_bad_per_partition"]:
                    raise RuntimeError("insufficient DWA E0 near-start bad snapshots in {}".format(partition))
            add_bad(bad_pool, sample["bad_per_planner_partition"])
            if len(chosen_bad) != sample["bad_per_planner_partition"]:
                raise RuntimeError("insufficient bad snapshots for {}/{}: {}".format(planner, partition, len(chosen_bad)))

            selected_by_episode = defaultdict(list)
            for row in chosen_bad:
                selected_by_episode[row["episode_id"]].append(row)
            chosen_nominal = []

            def nominal_distance(row):
                return min(abs(row["snapshot_time"] - bad["snapshot_time"]) / sample["nominal_match"]["elapsed_time_scale"] +
                           abs(row["normalized_path_progress"] - bad["normalized_path_progress"]) / sample["nominal_match"]["path_progress_scale"]
                           for bad in chosen_bad)

            def add_nominal(rows, target):
                ordered = sorted(rows, key=lambda row: (nominal_distance(row), _stable_key(seed, "nominal", row["episode_id"], row["call_index"])))
                for row in ordered:
                    prior = selected_by_episode[row["episode_id"]]
                    if len(prior) >= sample["max_snapshots_per_episode"] or layout_counts[row["layout_cluster"]] >= sample["max_snapshots_per_layout"]:
                        continue
                    if any(abs(row["snapshot_time"] - item["snapshot_time"]) < sample["same_episode_minimum_time_separation"] - 1e-9 or
                           abs(row["normalized_path_progress"] - item["normalized_path_progress"]) < sample["same_episode_minimum_progress_separation"] - 1e-9
                           for item in prior):
                        continue
                    chosen_nominal.append(row); selected_by_episode[row["episode_id"]].append(row); layout_counts[row["layout_cluster"]] += 1
                    if len(chosen_nominal) >= target:
                        break

            if planner == "dwa":
                failed_e0_layouts = {row["layout_id"] for row in bad_pool if row["profile_id"] == "e0"}
                rescued = [row for row in nominal_pool if row["profile_id"].startswith("tau_y_") and row["layout_id"] in failed_e0_layouts]
                add_nominal(rescued, sample["dwa_coverage"]["min_tau_y_rescue_nominal_per_partition"])
                if len(chosen_nominal) < sample["dwa_coverage"]["min_tau_y_rescue_nominal_per_partition"]:
                    raise RuntimeError("insufficient DWA tau_y rescue controls in {}".format(partition))
                easy = [row for row in nominal_pool if row["profile_id"] == "e0"]
                add_nominal(easy, min(sample["nominal_per_planner_partition"], len(chosen_nominal) + sample["dwa_coverage"]["include_all_available_e0_success_controls_up_to"]))
            add_nominal(nominal_pool, sample["nominal_per_planner_partition"])
            if len(chosen_nominal) != sample["nominal_per_planner_partition"]:
                raise RuntimeError("insufficient nominal snapshots for {}/{}: {}".format(planner, partition, len(chosen_nominal)))
            selected.extend(chosen_bad + chosen_nominal)
    if len(selected) != 144 or len({(row["episode_id"], row["call_index"]) for row in selected}) != 144:
        raise RuntimeError("snapshot selection did not produce 144 unique rows")
    for index, row in enumerate(sorted(selected, key=lambda item: (item["partition"], item["planner"], not item["y_bad"], item["layout_cluster"], item["episode_id"])), 1):
        row["snapshot_id"] = "eipt_{:03d}".format(index)
    return sorted(selected, key=lambda row: row["snapshot_id"])


def prepare(output=OUTPUT):
    protocol = yaml.safe_load(PROTOCOL_PATH.read_text())
    bad, nominal, _ = _candidate_snapshots(protocol)
    selected = _choose(protocol, bad, nominal)
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    path = output / "snapshot_schedule.json"
    payload = {"protocol_sha256": hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest(), "snapshots": selected}
    if path.exists() and json.loads(path.read_text()) != payload:
        raise RuntimeError("frozen snapshot schedule drift")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    counts = Counter((row["planner"], row["partition"], row["y_bad"]) for row in selected)
    return {"snapshots": len(selected), "counts": {"|".join(map(str, key)): value for key, value in sorted(counts.items())}}


def _directions(dimensions, mode):
    result = []
    for index in range(dimensions):
        for sign_value in (-1.0, 1.0):
            direction = [0.0] * dimensions; direction[index] = sign_value; result.append(tuple(direction))
    if mode == "axes_plus_cube_corners":
        scale = math.sqrt(dimensions)
        for mask in range(2 ** dimensions):
            result.append(tuple((1.0 if mask & (1 << index) else -1.0) / scale for index in range(dimensions)))
    elif mode == "signed_axes_plus_all_positive_and_all_negative":
        scale = math.sqrt(dimensions)
        result.extend([tuple([1.0 / scale] * dimensions), tuple([-1.0 / scale] * dimensions)])
    else:
        raise ValueError("unknown direction mode")
    return result


def directional_margin(origin, bounds, directions, evaluate, settings):
    """Fixed coarse directional search followed by first-bracket bisection."""
    best = None
    query_count = 0
    for direction in directions:
        previous_radius = 0.0
        previous_candidate = tuple(origin)
        radius = settings["coarse_radius_step"]
        while radius <= settings["max_radius"] + 1e-12:
            candidate = tuple(max(bounds[index][0], min(bounds[index][1], origin[index] + radius * direction[index])) for index in range(len(origin)))
            if candidate == previous_candidate:
                radius += settings["coarse_radius_step"]
                continue
            query_count += 1
            if evaluate(candidate):
                low, high = previous_radius, radius
                while high - low > settings["bisection_radius_resolution"] + 1e-12:
                    middle = (low + high) / 2.0
                    probe = tuple(max(bounds[index][0], min(bounds[index][1], origin[index] + middle * direction[index])) for index in range(len(origin)))
                    query_count += 1
                    if evaluate(probe): high = middle
                    else: low = middle
                final = tuple(max(bounds[index][0], min(bounds[index][1], origin[index] + high * direction[index])) for index in range(len(origin)))
                distance = _l2(tuple(value - base for value, base in zip(final, origin)))
                best = distance if best is None else min(best, distance)
                break
            previous_radius, previous_candidate = radius, candidate
            radius += settings["coarse_radius_step"]
    return (settings["no_transition_value"] if best is None else best), best is None, query_count


def restore_execution(snapshot, theta, trace):
    """Restore actual pose/velocity while rebuilding delay queue from command history."""
    state = snapshot["executed"]
    execution = FirstOrderExecution(**theta, initial_pose=Pose2D(state["x"], state["y"], state["yaw"]))
    execution.state = State(state["x"], state["y"], state["yaw"], state["vx"], state["vy"], state["wz"], 0.0)
    history_window = 0.25
    snapshot_time = snapshot["snapshot_time"]
    history = [call for call in trace["planner_calls"][:snapshot["call_index"]]
               if float(call["simulation_time"]) >= snapshot_time - history_window - 1e-9]
    active = Command()
    pending = []
    for call in history:
        command = Command(**{name: float(call["command"][name]) for name in COMPONENTS})
        activation = float(call["simulation_time"]) - snapshot_time + float(theta["delay"])
        if activation <= 1e-12: active = command
        else: pending.append((activation, command))
    execution.active_command = active
    execution._pending = deque(sorted(pending, key=lambda item: item[0]))
    return execution


class RosQuerySession:
    def __init__(self, planner, port, output):
        self.planner, self.port, self.output = planner, port, Path(output)
        self.temp = None; self.core = None; self.bridge = None

    def start(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scale_eipt_")
        root = Path(self.temp.name); (root / "ros_home").mkdir(); (root / "ros_log").mkdir()
        os.environ.update(ROS_MASTER_URI="http://127.0.0.1:{}".format(self.port), ROS_IP="127.0.0.1",
                          ROS_HOME=str(root / "ros_home"), ROS_LOG_DIR=str(root / "ros_log"))
        log_path = self.output / "logs" / ("worker_{}_{}.log".format(self.planner, self.port)); log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = log_path.open("a")
        self.core = subprocess.Popen(["roscore", "-p", str(self.port)], stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if subprocess.run(["rosparam", "list"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0: break
            time.sleep(.05)
        else: raise RuntimeError("ROS master unavailable")
        commands = [
            ["rosparam", "set", "/use_sim_time", "true"],
            ["rosparam", "load", str(ROOT / "navigation/scale_planner_bridge/config/common.yaml"), "/scale_planner_bridge/local_costmap"],
            ["rosparam", "load", str(ROOT / "navigation/scale_planner_bridge/config/{}.yaml".format(self.planner)), "/scale_planner_bridge"],
            ["rosparam", "load", str(ROOT / "navigation/scale_planner_bridge/config/matrix_common.yaml"), "/scale_planner_bridge"],
            ["rosparam", "set", "/scale_planner_bridge/allow_reinitialize", "true"],
        ]
        for command in commands:
            if subprocess.run(command, stdout=self.log, stderr=subprocess.STDOUT).returncode:
                raise RuntimeError("rosparam setup failed")
        self.bridge = subprocess.Popen(["rosrun", "scale_planner_bridge", "planner_bridge_node"], cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        sys.path.append("/usr/lib/python3/dist-packages")
        import rospy
        rospy.init_node("eipt_query_{}_{}".format(self.planner, self.port), anonymous=True, disable_signals=True)
        rospy.wait_for_service("/initialize", timeout=10); rospy.wait_for_service("/step", timeout=10)
        from scale_planner_bridge.srv import Initialize, Step
        self.initialize = rospy.ServiceProxy("/initialize", Initialize)
        self.step = rospy.ServiceProxy("/step", Step)

    def close(self):
        for process in (self.bridge, self.core):
            if process and process.poll() is None:
                process.send_signal(signal.SIGINT)
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
        if getattr(self, "log", None): self.log.close()
        if self.temp: self.temp.cleanup()

    def _initialize(self, layout):
        from navigation.scale_planner_bridge.scripts.planner_execution_smoke import map_from_layout, fixed_plan
        from scale_planner_bridge.srv import InitializeRequest
        reply = self.initialize(InitializeRequest(map=map_from_layout(layout),
            plan=fixed_plan(layout["start"], layout["goal"], layout.get("global_path")), planner_period=0.05))
        if not reply.ok: raise RuntimeError("planner initialize failed: " + reply.error)

    def _step(self, step_index, state):
        from scale_planner_bridge.srv import StepRequest
        reply = self.step(StepRequest(simulation_time=step_index * 0.05, x=state["x"], y=state["y"], yaw=state["yaw"],
                                      vx=state["vx"], vy=state["vy"], wz=state["wz"]))
        if not reply.ok: return None
        return {"vx": reply.command.linear.x, "vy": reply.command.linear.y, "wz": reply.command.angular.z}

    def query(self, snapshot, trace, layout, velocity=None):
        self._initialize(layout)
        start = max(0, snapshot["call_index"] - 5)
        step_index = 0
        for call in trace["planner_calls"][start:snapshot["call_index"]]:
            self._step(step_index, call["executed"]); step_index += 1
        state = dict(snapshot["executed"])
        if velocity is not None:
            state.update(dict(zip(COMPONENTS, velocity)))
        return self._step(step_index, state)

    def rollout(self, snapshot, trace, layout, theta, horizon=10):
        self._initialize(layout)
        start = max(0, snapshot["call_index"] - 5)
        step_index = 0
        for call in trace["planner_calls"][start:snapshot["call_index"]]:
            self._step(step_index, call["executed"]); step_index += 1
        execution = restore_execution(snapshot, theta, trace)
        commands = []
        for _ in range(horizon):
            state = {name: getattr(execution.state, name) for name in ("x", "y", "yaw", "vx", "vy", "wz")}
            command = self._step(step_index, state); commands.append(command); step_index += 1
            if command is None:
                commands.extend([None] * (horizon - len(commands))); break
            execution.set_command(Command(**command))
            for _ in range(5): execution.advance(0.01)
        return commands


def _ordinary_metrics(snapshot, trace, layout, protocol):
    limits = protocol["planner_response_transition"]["command_limits"]
    command = _command_vector(snapshot["recorded_command"], limits)
    executed = tuple(float(snapshot["executed"][name]) / limits[name] for name in COMPONENTS)
    previous = _command_vector(snapshot["previous_command"], limits)
    ev = _l2(tuple(left - right for left, right in zip(command, executed)))
    du = _l2(tuple(left - right for left, right in zip(command, previous)))
    state = snapshot["executed"]
    ideal_pose = _integrate(Pose2D(state["x"], state["y"], state["yaw"]), Command(**snapshot["recorded_command"]), 0.05)
    next_index = min(snapshot["call_index"] + 1, len(trace["planner_calls"]) - 1)
    actual = trace["planner_calls"][next_index]["executed"]
    ex = _l2(((ideal_pose.x - actual["x"]) / 0.025, (ideal_pose.y - actual["y"]) / 0.025,
              math.atan2(math.sin(ideal_pose.yaw - actual["yaw"]), math.cos(ideal_pose.yaw - actual["yaw"])) / 0.04))
    robot = footprint(yaml.safe_load((ROOT / "configs/rq1/protocol.yaml").read_text())["robot"]["footprint"])
    parsed = load_layout(layout)
    shape = transform_footprint(robot, Pose2D(state["x"], state["y"], state["yaw"]))
    clearance = minimum_clearance(shape, parsed["obstacles"])
    return {"e_v": ev, "e_x": ex, "c_min": clearance, "u_magnitude": _l2(command), "delta_u_magnitude": du}


def evaluate_snapshot(session, snapshot, layout, protocol):
    trace = _load_trace(ROOT / snapshot["trace_path"])
    frozen = protocol["planner_response_transition"]
    recorded = snapshot["recorded_command"]
    baseline = session.query(snapshot, trace, layout)
    replay_mismatch = material_transition(recorded, baseline, frozen)
    ordinary = _ordinary_metrics(snapshot, trace, layout, protocol)

    m_settings = protocol["ordinary_margin"]
    scales = tuple(float(m_settings["scales"][name]) for name in COMPONENTS)
    origin = tuple(float(snapshot["executed"][name]) / scale for name, scale in zip(COMPONENTS, scales))
    bounds = tuple((float(m_settings["bounds"][name][0]) / scale, float(m_settings["bounds"][name][1]) / scale)
                   for name, scale in zip(COMPONENTS, scales))
    directions = _directions(3, m_settings["directions"])
    def state_transition(candidate):
        velocity = tuple(candidate[index] * scales[index] for index in range(3))
        return material_transition(baseline, session.query(snapshot, trace, layout, velocity), frozen)
    m_p, m_p_censored, m_p_queries = directional_margin(origin, bounds, directions, state_transition, m_settings)

    f_settings = protocol["execution_margin"]
    theta_scales = tuple(float(f_settings["scales"][name]) for name in THETA)
    theta_origin = tuple(float(snapshot["theta"][name]) / scale for name, scale in zip(THETA, theta_scales))
    theta_bounds = tuple((float(f_settings["normalized_bounds"][0]), float(f_settings["normalized_bounds"][1])) for _ in THETA)
    nominal_sequence = session.rollout(snapshot, trace, layout, snapshot["theta"], f_settings["horizon_planner_cycles"])
    def execution_transition(candidate):
        theta = {name: candidate[index] * theta_scales[index] for index, name in enumerate(THETA)}
        sequence = session.rollout(snapshot, trace, layout, theta, f_settings["horizon_planner_cycles"])
        return sequence_transition(nominal_sequence, sequence, frozen)
    m_pf, m_pf_censored, m_pf_queries = directional_margin(theta_origin, theta_bounds,
        _directions(4, f_settings["directions"]), execution_transition, f_settings)
    return dict(ordinary, baseline_query_command=baseline, baseline_query_mismatch=replay_mismatch,
                m_p=m_p, m_p_censored=m_p_censored, m_pf=m_pf, m_pf_censored=m_pf_censored,
                m_p_queries=m_p_queries, m_pf_queries=m_pf_queries,
                nominal_rollout_failure=any(command is None for command in nominal_sequence))


def _worker(planner, snapshots, layouts, protocol, output, port, queue):
    session = RosQuerySession(planner, port, output)
    try:
        session.start()
        for snapshot in snapshots:
            path = Path(output) / "query_results" / (snapshot["snapshot_id"] + ".json")
            if path.exists():
                queue.put((snapshot["snapshot_id"], "resumed", None)); continue
            try:
                result = evaluate_snapshot(session, snapshot, layouts[snapshot["source"]][snapshot["layout_id"]], protocol)
                temporary = path.with_suffix(".tmp"); temporary.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(json.dumps(result, sort_keys=True) + "\n"); temporary.replace(path)
                queue.put((snapshot["snapshot_id"], "ok", None))
            except Exception as error:
                queue.put((snapshot["snapshot_id"], "error", repr(error))); return
    finally:
        session.close()


def _ports(count):
    import socket
    ports, sockets = [], []
    try:
        for _ in range(count):
            sock = socket.socket(); sock.bind(("127.0.0.1", 0)); ports.append(sock.getsockname()[1]); sockets.append(sock)
    finally:
        for sock in sockets: sock.close()
    return ports


def run(output=OUTPUT, workers=12, limit=None, snapshot_ids=None, partition=None):
    output = Path(output)
    schedule = json.loads((output / "snapshot_schedule.json").read_text())
    if schedule["protocol_sha256"] != hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest():
        raise RuntimeError("snapshot schedule protocol drift")
    snapshots = schedule["snapshots"]
    if partition:
        if partition not in ("discovery", "holdout"):
            raise ValueError("partition must be discovery or holdout")
        snapshots = [row for row in snapshots if row["partition"] == partition]
    if snapshot_ids:
        requested_ids = set(snapshot_ids)
        snapshots = [row for row in snapshots if row["snapshot_id"] in requested_ids]
        if {row["snapshot_id"] for row in snapshots} != requested_ids:
            raise RuntimeError("unknown snapshot id requested")
    if limit:
        snapshots = snapshots[:limit]
    protocol = yaml.safe_load(PROTOCOL_PATH.read_text())
    layouts = {source: {item["layout_id"]: item for item in yaml.safe_load((ROOT / settings["layouts"]).read_text())["layouts"]}
               for source, settings in protocol["sources"].items()}
    assignments = []
    per_planner = max(1, workers // 3)
    for planner in protocol["sampling"]["planners"]:
        rows = [row for row in snapshots if row["planner"] == planner]
        for index in range(min(per_planner, len(rows))):
            chunk = rows[index::per_planner]
            if chunk: assignments.append((planner, chunk))
    ports = _ports(len(assignments)); queue = mp.Queue(); processes = []
    for (planner, rows), port in zip(assignments, ports):
        process = mp.Process(target=_worker, args=(planner, rows, layouts, protocol, output, port, queue)); process.start(); processes.append(process)
    completed, errors = 0, []
    expected = len(snapshots)
    while completed < expected and any(process.is_alive() for process in processes):
        try:
            snapshot_id, status, error = queue.get(timeout=1); completed += 1
            if status == "error": errors.append((snapshot_id, error))
            if completed % 10 == 0: print("completed {}/{}".format(completed, expected), flush=True)
        except Exception:
            pass
        if errors: break
    if errors:
        for process in processes:
            if process.is_alive(): process.terminate()
    for process in processes: process.join(timeout=10)
    if errors: raise RuntimeError("query worker failure: {}".format(errors[0]))
    missing = [row["snapshot_id"] for row in snapshots if not (output / "query_results" / (row["snapshot_id"] + ".json")).is_file()]
    if missing:
        raise RuntimeError("query workers ended without results: {}".format(missing[:5]))
    result_files = list((output / "query_results").glob("eipt_*.json"))
    return {"requested": expected, "available_results": len(result_files), "workers": len(assignments)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--snapshot-id", action="append")
    parser.add_argument("--partition", choices=("discovery", "holdout"))
    args = parser.parse_args(argv)
    result = prepare(Path(args.output)) if args.command == "prepare" else run(
        Path(args.output), args.workers, args.limit, args.snapshot_id, args.partition)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
