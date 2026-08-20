"""Deterministic planar E0, E1, and reserved E2 execution interfaces."""
from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Command:
    vx: float = 0.0
    vy: float = 0.0
    wz: float = 0.0


@dataclass(frozen=True)
class Pose2D:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0


@dataclass(frozen=True)
class State:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    wz: float = 0.0
    time: float = 0.0


def _integrate(pose, command, dt):
    angle = command.wz * dt
    if abs(command.wz) < 1e-12:
        local_x, local_y = command.vx * dt, command.vy * dt
    else:
        local_x = (command.vx * math.sin(angle) + command.vy * (math.cos(angle) - 1)) / command.wz
        local_y = (command.vx * (1 - math.cos(angle)) + command.vy * math.sin(angle)) / command.wz
    c, s = math.cos(pose.yaw), math.sin(pose.yaw)
    return Pose2D(pose.x + c * local_x - s * local_y, pose.y + s * local_x + c * local_y, pose.yaw + angle)


def _check_dt(dt):
    if dt <= 0:
        raise ValueError("dt must be positive")


class IdealExecution:
    """E0: exact integration of a constant body-frame holonomic command."""
    def __init__(self, initial_pose=Pose2D()):
        self.state = State(initial_pose.x, initial_pose.y, initial_pose.yaw)

    def step(self, command, dt):
        _check_dt(dt)
        pose = _integrate(self.state, command, dt)
        self.state = State(pose.x, pose.y, pose.yaw, command.vx, command.vy, command.wz, self.state.time + dt)
        return self.state


class FirstOrderExecution:
    """E1: synthetic delayed commands with independent first-order body-speed lags."""
    def __init__(self, delay=0.0, tau_x=0.0, tau_y=0.0, tau_w=0.0, initial_pose=Pose2D()):
        if min(delay, tau_x, tau_y, tau_w) < 0:
            raise ValueError("delay and time constants must be non-negative")
        self.delay, self.taus = delay, Command(tau_x, tau_y, tau_w)
        self.state = State(initial_pose.x, initial_pose.y, initial_pose.yaw)
        self.active_command = Command()
        self._pending = deque()

    @classmethod
    def from_profile(cls, profile, initial_pose=Pose2D()):
        return cls(delay=profile["delay"], tau_x=profile["tau_x"], tau_y=profile["tau_y"],
                   tau_w=profile["tau_w"], initial_pose=initial_pose)

    @staticmethod
    def _lag(value, target, tau, dt):
        return target if tau == 0 else target + (value - target) * math.exp(-dt / tau)

    def step(self, command, dt):
        _check_dt(dt)
        self._pending.append((self.state.time + self.delay, command))
        while self._pending and self._pending[0][0] <= self.state.time + 1e-12:
            _, self.active_command = self._pending.popleft()
        actual = Command(self._lag(self.state.vx, self.active_command.vx, self.taus.vx, dt),
                         self._lag(self.state.vy, self.active_command.vy, self.taus.vy, dt),
                         self._lag(self.state.wz, self.active_command.wz, self.taus.wz, dt))
        pose = _integrate(self.state, actual, dt)
        self.state = State(pose.x, pose.y, pose.yaw, actual.vx, actual.vy, actual.wz, self.state.time + dt)
        return self.state


class EmpiricalExecution:
    """E2 is reserved for measured execution data, not Phase-0 simulation."""
    def step(self, command, dt):
        raise NotImplementedError("Empirical execution is outside Phase 0")
