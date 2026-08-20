"""Deterministic global-dt execution of scripted command segments."""
from .execution import Command, Pose2D
from .geometry import collision, minimum_clearance, transform_footprint


def _command(segment):
    kind = segment["type"]
    if kind == "forward": return Command(vx=segment["speed"])
    if kind == "lateral": return Command(vy=segment["speed"])
    if kind == "rotate": return Command(wz=segment["speed"])
    if kind == "combined": return Command(segment["vx"], segment["vy"], segment["wz"])
    raise ValueError("unsupported command type: {}".format(kind))


class Simulator:
    def __init__(self, layout, execution, robot_footprint, dt, duration):
        if dt <= 0 or duration < 0:
            raise ValueError("dt must be positive and duration non-negative")
        self.layout, self.execution, self.footprint = layout, execution, robot_footprint
        self.dt, self.duration = dt, duration

    def _row(self, state, command):
        shape = transform_footprint(self.footprint, Pose2D(state.x, state.y, state.yaw))
        return {"time": state.time, "x": state.x, "y": state.y, "yaw": state.yaw,
                "command_vx": command.vx, "command_vy": command.vy, "command_wz": command.wz,
                "vx": state.vx, "vy": state.vy, "wz": state.wz,
                "collision": collision(shape, self.layout["obstacles"]),
                "clearance": minimum_clearance(shape, self.layout["obstacles"])}

    def run(self, scripted_sequence):
        rows, elapsed, command = [self._row(self.execution.state, Command())], 0.0, Command()
        for segment in scripted_sequence:
            command, segment_elapsed = _command(segment), 0.0
            while segment_elapsed < segment["duration"] - 1e-12 and elapsed < self.duration - 1e-12:
                step = min(self.dt, segment["duration"] - segment_elapsed, self.duration - elapsed)
                rows.append(self._row(self.execution.step(command, step), command))
                segment_elapsed += step; elapsed += step
        command = Command()
        while elapsed < self.duration - 1e-12:
            step = min(self.dt, self.duration - elapsed)
            rows.append(self._row(self.execution.step(command, step), command))
            elapsed += step
        return rows
