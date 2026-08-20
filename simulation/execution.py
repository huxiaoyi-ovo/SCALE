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
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be finite and positive")


class IdealExecution:
    """E0: exact integration of a constant body-frame holonomic command."""
    def __init__(self, initial_pose=Pose2D()):
        self.state = State(initial_pose.x, initial_pose.y, initial_pose.yaw)
        self.active_command = Command()

    def set_command(self, command):
        self.active_command = command

    def advance(self, dt):
        _check_dt(dt)
        pose = _integrate(self.state, self.active_command, dt)
        command = self.active_command
        self.state = State(pose.x, pose.y, pose.yaw, command.vx, command.vy,
                           command.wz, self.state.time + dt)
        return self.state

    def step(self, command, dt):
        self.set_command(command)
        return self.advance(dt)


class FirstOrderExecution:
    """E1: synthetic delayed commands with independent first-order body-speed lags."""
    def __init__(self, delay=0.0, tau_x=0.0, tau_y=0.0, tau_w=0.0, initial_pose=Pose2D()):
        parameters = (delay, tau_x, tau_y, tau_w)
        if not all(math.isfinite(value) and value >= 0 for value in parameters):
            raise ValueError("delay and time constants must be finite and non-negative")
        self.delay, self.taus = delay, Command(tau_x, tau_y, tau_w)
        self.state = State(initial_pose.x, initial_pose.y, initial_pose.yaw)
        self.active_command = Command()
        self._pending = deque()

    @classmethod
    def from_profile(cls, profile, initial_pose=Pose2D()):
        return cls(delay=profile["delay"], tau_x=profile["tau_x"], tau_y=profile["tau_y"],
                   tau_w=profile["tau_w"], initial_pose=initial_pose)

    @staticmethod
    def _lag_response(value, target, tau, dt):
        if tau == 0:
            return target, target
        decay = math.exp(-dt / tau)
        end = target + (value - target) * decay
        average = target + (value - target) * (tau / dt) * (1 - decay)
        return end, average

    def set_command(self, command):
        self._pending.append((self.state.time + self.delay, command))

    def _activate_due_commands(self):
        while self._pending and self._pending[0][0] <= self.state.time + 1e-12:
            _, self.active_command = self._pending.popleft()

    def _advance_segment(self, dt):
        x_end, x_average = self._lag_response(
            self.state.vx, self.active_command.vx, self.taus.vx, dt)
        y_end, y_average = self._lag_response(
            self.state.vy, self.active_command.vy, self.taus.vy, dt)
        w_end, w_average = self._lag_response(
            self.state.wz, self.active_command.wz, self.taus.wz, dt)
        pose = _integrate(self.state, Command(x_average, y_average, w_average), dt)
        self.state = State(pose.x, pose.y, pose.yaw, x_end, y_end, w_end,
                           self.state.time + dt)

    def advance(self, dt):
        _check_dt(dt)
        end_time = self.state.time + dt
        self._activate_due_commands()
        while self._pending and self._pending[0][0] < end_time - 1e-12:
            event_time = self._pending[0][0]
            if event_time > self.state.time + 1e-12:
                self._advance_segment(event_time - self.state.time)
            self._activate_due_commands()
        if end_time > self.state.time + 1e-12:
            self._advance_segment(end_time - self.state.time)
        return self.state

    def step(self, command, dt):
        self.set_command(command)
        return self.advance(dt)


class EmpiricalExecution:
    """E2 is reserved for measured execution data, not Phase-0 simulation."""
    def step(self, command, dt):
        raise NotImplementedError("Empirical execution is outside Phase 0")
