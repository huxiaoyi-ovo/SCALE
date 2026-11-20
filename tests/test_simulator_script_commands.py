import math

import pytest

from simulation.execution import IdealExecution
from simulation.geometry import rectangle
from simulation.simulator import Simulator


@pytest.mark.parametrize("segment", [
    {"type": "forward", "speed": math.nan},
    {"type": "lateral", "speed": math.inf},
    {"type": "rotate", "speed": -math.inf},
    {"type": "combined", "vx": 0.1, "vy": math.nan, "wz": 0.2},
])
def test_simulator_rejects_nonfinite_commands_before_execution(segment):
    execution = IdealExecution()
    simulator = Simulator(
        {"obstacles": []}, execution, rectangle(0, 0, 0.1, 0.1), dt=0.1, duration=0.2,
    )

    with pytest.raises(ValueError, match="scripted command velocities must be finite"):
        simulator.run([dict(segment, duration=0.1)])

    assert execution.state.time == 0.0
