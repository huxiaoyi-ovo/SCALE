#!/usr/bin/env python3
"""Fixed-map DWA x E0 smoke test; SCALE owns integration and termination."""
import json
import math
from pathlib import Path

import rospy
import yaml
from geometry_msgs.msg import PoseStamped, Quaternion
from nav_msgs.msg import OccupancyGrid, MapMetaData, Path as RosPath

from scale_planner_bridge.srv import Initialize, InitializeRequest, Step, StepRequest


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


def footprint_collision(grid, state, footprint):
    """Conservative occupancy check for the configured rectangular footprint."""
    c, s = math.cos(state[2]), math.sin(state[2])
    padding = grid.info.resolution / math.sqrt(2.0)
    half_x = footprint["width"] / 2.0 + padding
    half_y = footprint["length"] / 2.0 + padding
    for index, value in enumerate(grid.data):
        if value < 50:
            continue
        ix, iy = index % grid.info.width, index // grid.info.width
        x = grid.info.origin.position.x + (ix + 0.5) * grid.info.resolution
        y = grid.info.origin.position.y + (iy + 0.5) * grid.info.resolution
        dx, dy = x - state[0], y - state[1]
        if abs(c * dx + s * dy) <= half_x and abs(-s * dx + c * dy) <= half_y:
            return True
    return False


def fixed_plan(start, goal):
    plan = RosPath(); plan.header.frame_id = "map"
    for ratio in (0.0, 0.25, 0.5, 0.75, 1.0):
        pose = PoseStamped(); pose.header.frame_id = "map"
        pose.pose.position.x = start["x"] + ratio * (goal["x"] - start["x"])
        pose.pose.position.y = start["y"] + ratio * (goal["y"] - start["y"])
        pose.pose.orientation = quat(start.get("yaw", 0.0) + ratio * (goal.get("yaw", 0.0) - start.get("yaw", 0.0)))
        plan.poses.append(pose)
    return plan


def integrate(state, command, dt):
    angle = command.angular.z * dt
    if abs(command.angular.z) < 1e-12:
        lx, ly = command.linear.x * dt, command.linear.y * dt
    else:
        lx = (command.linear.x * math.sin(angle) + command.linear.y * (math.cos(angle) - 1.0)) / command.angular.z
        ly = (command.linear.x * (1.0 - math.cos(angle)) + command.linear.y * math.sin(angle)) / command.angular.z
    c, s = math.cos(state[2]), math.sin(state[2])
    return [state[0] + c * lx - s * ly, state[1] + s * lx + c * ly, state[2] + angle,
            command.linear.x, command.linear.y, command.angular.z]


def main():
    root = Path(__file__).resolve().parents[3]
    with (root / "configs" / "pilot.yaml").open() as stream:
        config = yaml.safe_load(stream)
    layout, dt = config["layout"], config["dt"]
    rospy.init_node("dwa_e0_smoke", anonymous=True)
    duration = rospy.get_param("/scale_planner_bridge/smoke_duration", config["duration"])
    xy_tolerance = rospy.get_param("/scale_planner_bridge/external_xy_tolerance", 0.08)
    yaw_tolerance = rospy.get_param("/scale_planner_bridge/external_yaw_tolerance", 0.10)
    rospy.wait_for_service("/initialize", timeout=10.0); rospy.wait_for_service("/step", timeout=10.0)
    initialize, step = rospy.ServiceProxy("/initialize", Initialize), rospy.ServiceProxy("/step", Step)
    grid = map_from_layout(layout)
    request = InitializeRequest(map=grid, plan=fixed_plan(layout["start"], layout["goal"]))
    initial = initialize(request)
    if not initial.ok:
        raise RuntimeError(initial.error)
    state = [layout["start"]["x"], layout["start"]["y"], layout["start"].get("yaw", 0.0), 0.0, 0.0, 0.0]
    failures, compute, reason, collision = 0, [], "duration", False
    max_steps = int(math.ceil(duration / dt))
    for index in range(max_steps):
        reply = step(StepRequest(x=state[0], y=state[1], yaw=state[2], vx=state[3], vy=state[4], wz=state[5]))
        compute.append(reply.compute_seconds)
        if not reply.ok:
            failures += 1; reason = reply.error; break
        state = integrate(state, reply.command, dt)
        if footprint_collision(grid, state, config["robot_footprint"]):
            collision, reason = True, "footprint_collision"; break
        xy_error = math.hypot(state[0] - layout["goal"]["x"], state[1] - layout["goal"]["y"])
        yaw_error = abs(math.atan2(math.sin(state[2] - layout["goal"].get("yaw", 0.0)), math.cos(state[2] - layout["goal"].get("yaw", 0.0))))
        if xy_error <= xy_tolerance and yaw_error <= yaw_tolerance:
            reason = "external_tolerance"; break
    xy_error = math.hypot(state[0] - layout["goal"]["x"], state[1] - layout["goal"]["y"])
    yaw_error = abs(math.atan2(math.sin(state[2] - layout["goal"].get("yaw", 0.0)), math.cos(state[2] - layout["goal"].get("yaw", 0.0))))
    summary = {"success": reason == "external_tolerance", "reason": reason, "steps": len(compute),
               "final_xy_error": xy_error, "final_yaw_error": yaw_error, "collision": collision,
               "planner_failures": failures, "compute_seconds": {"count": len(compute),
               "mean": sum(compute) / len(compute) if compute else 0.0, "max": max(compute) if compute else 0.0}}
    print(json.dumps(summary, sort_keys=True))
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
