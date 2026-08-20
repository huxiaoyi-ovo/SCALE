#!/usr/bin/env python3
"""Logically timed DWA x E0 smoke using SCALE's canonical geometry."""
import argparse
import json
import math
from pathlib import Path
import sys

SYSTEM_DIST_PACKAGES = "/usr/lib/python3/dist-packages"
if SYSTEM_DIST_PACKAGES not in sys.path:
    sys.path.append(SYSTEM_DIST_PACKAGES)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import rospy
import yaml
from geometry_msgs.msg import PoseStamped, Quaternion
from nav_msgs.msg import OccupancyGrid, MapMetaData, Path as RosPath

from scale_planner_bridge.srv import Initialize, InitializeRequest, Step, StepRequest
from simulation.execution import Command, IdealExecution, Pose2D
from simulation.geometry import collision, footprint, transform_footprint
from simulation.maps import load_layout


TOLERANCE = 1e-9


def quat(yaw):
    return Quaternion(z=math.sin(yaw / 2.0), w=math.cos(yaw / 2.0))


def occupied(item, x, y):
    if item["type"] == "circle":
        return (x - item["x"]) ** 2 + (y - item["y"]) ** 2 <= item["radius"] ** 2
    dx, dy = x - item["x"], y - item["y"]
    c, s = math.cos(item.get("yaw", 0.0)), math.sin(item.get("yaw", 0.0))
    local_x, local_y = c * dx + s * dy, -s * dx + c * dy
    return abs(local_x) <= item["width"] / 2.0 and abs(local_y) <= item["length"] / 2.0


def map_from_layout(layout, resolution=0.05):
    arena = layout["arena"]
    grid = OccupancyGrid()
    grid.header.frame_id = "map"
    grid.info = MapMetaData(resolution=resolution, width=int(math.ceil(arena["width"] / resolution)),
                            height=int(math.ceil(arena["height"] / resolution)))
    grid.info.origin.orientation.w = 1.0
    grid.data = [0] * (grid.info.width * grid.info.height)
    for iy in range(grid.info.height):
        for ix in range(grid.info.width):
            x, y = (ix + 0.5) * resolution, (iy + 0.5) * resolution
            if any(occupied(obstacle, x, y) for obstacle in layout.get("obstacles", [])):
                grid.data[iy * grid.info.width + ix] = 100
    return grid


def fixed_plan(start, goal):
    plan = RosPath(); plan.header.frame_id = "map"
    for ratio in (0.0, 0.25, 0.5, 0.75, 1.0):
        pose = PoseStamped(); pose.header.frame_id = "map"
        pose.pose.position.x = start["x"] + ratio * (goal["x"] - start["x"])
        pose.pose.position.y = start["y"] + ratio * (goal["y"] - start["y"])
        pose.pose.orientation = quat(start.get("yaw", 0.0) + ratio * (goal.get("yaw", 0.0) - start.get("yaw", 0.0)))
        plan.poses.append(pose)
    return plan


def state_record(state):
    return {"time": state.time, "x": state.x, "y": state.y, "yaw": state.yaw,
            "vx": state.vx, "vy": state.vy, "wz": state.wz}


def feedback_record(message):
    orientation = message.pose.pose.orientation
    yaw = 2.0 * math.atan2(orientation.z, orientation.w)
    return {"stamp": message.header.stamp.to_sec(), "x": message.pose.pose.position.x,
            "y": message.pose.pose.position.y, "yaw": yaw,
            "vx": message.twist.twist.linear.x, "vy": message.twist.twist.linear.y,
            "wz": message.twist.twist.angular.z}


def assert_close(label, actual, expected):
    if abs(actual - expected) > TOLERANCE:
        raise RuntimeError("{} mismatch: {} != {}".format(label, actual, expected))


def verify_feedback(reply, state, clock_epoch):
    feedback = feedback_record(reply.feedback)
    expected = state_record(state)
    assert_close("logical_time", reply.logical_time, state.time)
    assert_close("odom_stamp", feedback["stamp"], clock_epoch + state.time)
    for field in ("x", "y", "yaw", "vx", "vy", "wz"):
        assert_close("feedback_{}".format(field), feedback[field], expected[field])
    return feedback


def resolve_config(source):
    path = Path(source)
    return path if path.is_absolute() else ROOT / path


def run(config, trace_output=None):
    raw_layout = config["layout"]
    layout = load_layout(raw_layout)
    execution_dt = float(config["dt"])
    planner_period = float(rospy.get_param("/scale_planner_bridge/planner_period"))
    duration = float(rospy.get_param("/scale_planner_bridge/smoke_duration", config["duration"]))
    xy_tolerance = float(rospy.get_param("/scale_planner_bridge/external_xy_tolerance", 0.08))
    yaw_tolerance = float(rospy.get_param("/scale_planner_bridge/external_yaw_tolerance", 0.10))
    substeps = int(round(planner_period / execution_dt))
    if substeps < 1 or abs(substeps * execution_dt - planner_period) > TOLERANCE:
        raise ValueError("planner_period must be an integer multiple of execution_dt")

    rospy.wait_for_service("/initialize", timeout=10.0)
    rospy.wait_for_service("/step", timeout=10.0)
    initialize = rospy.ServiceProxy("/initialize", Initialize)
    step = rospy.ServiceProxy("/step", Step)
    initial = initialize(InitializeRequest(map=map_from_layout(raw_layout),
                                           plan=fixed_plan(raw_layout["start"], raw_layout["goal"]),
                                           planner_period=planner_period))
    if not initial.ok:
        raise RuntimeError(initial.error)

    execution = IdealExecution(layout["start"])
    robot_shape = footprint(config["robot_footprint"])
    trace = {"planner_period": planner_period, "execution_dt": execution_dt,
             "planner_calls": [], "execution_states": [state_record(execution.state)]}
    compute_times = []
    planner_failures = 0
    reason = "duration"
    collided = False
    planner_index = 0

    while execution.state.time < duration - TOLERANCE:
        state = execution.state
        assert_close("planner_schedule", state.time, planner_index * planner_period)
        reply = step(StepRequest(simulation_time=state.time, x=state.x, y=state.y, yaw=state.yaw,
                                 vx=state.vx, vy=state.vy, wz=state.wz))
        compute_times.append(reply.compute_seconds)
        if not reply.ok:
            planner_failures += 1
            reason = reply.error
            break
        feedback = verify_feedback(reply, state, initial.clock_epoch)
        command = Command(reply.command.linear.x, reply.command.linear.y, reply.command.angular.z)
        trace["planner_calls"].append({"simulation_time": state.time, "executed": state_record(state),
                                       "feedback": feedback,
                                       "command": {"vx": command.vx, "vy": command.vy, "wz": command.wz}})

        for _ in range(substeps):
            new_state = execution.step(command, execution_dt)
            trace["execution_states"].append(state_record(new_state))
            shape = transform_footprint(robot_shape, Pose2D(new_state.x, new_state.y, new_state.yaw))
            if collision(shape, layout["obstacles"]):
                collided, reason = True, "footprint_collision"
                break
            xy_error = math.hypot(new_state.x - layout["goal"].x, new_state.y - layout["goal"].y)
            yaw_error = abs(math.atan2(math.sin(new_state.yaw - layout["goal"].yaw),
                                       math.cos(new_state.yaw - layout["goal"].yaw)))
            if xy_error <= xy_tolerance and yaw_error <= yaw_tolerance:
                reason = "external_tolerance"
                break
        planner_index += 1
        if reason != "duration":
            break

    final = execution.state
    xy_error = math.hypot(final.x - layout["goal"].x, final.y - layout["goal"].y)
    yaw_error = abs(math.atan2(math.sin(final.yaw - layout["goal"].yaw),
                               math.cos(final.yaw - layout["goal"].yaw)))
    success = reason == "external_tolerance"
    summary = {"success": success, "reason": reason, "planner_calls": len(trace["planner_calls"]),
               "execution_steps": len(trace["execution_states"]) - 1,
               "final_xy_error": xy_error, "final_yaw_error": yaw_error, "collision": collided,
               "planner_failures": planner_failures, "time_contract": True, "feedback_contract": True,
               "compute_seconds": {"count": len(compute_times),
               "mean": sum(compute_times) / len(compute_times) if compute_times else 0.0,
               "max": max(compute_times) if compute_times else 0.0}}
    trace["termination"] = {key: summary[key] for key in
                            ("success", "reason", "planner_calls", "execution_steps",
                             "final_xy_error", "final_yaw_error", "collision", "planner_failures")}
    if trace_output:
        path = Path(trace_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/pilot.yaml")
    parser.add_argument("--trace-output")
    args = parser.parse_args()
    with resolve_config(args.config).open() as stream:
        config = yaml.safe_load(stream)
    rospy.init_node("dwa_e0_smoke", anonymous=True)
    summary = run(config, args.trace_output)
    print(json.dumps(summary, sort_keys=True))
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
