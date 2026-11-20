import pytest

from simulation.execution import IdealExecution
from simulation.geometry import rectangle
from simulation.simulator import Simulator


@pytest.mark.parametrize("dt", [0.0, -1.0, float("nan"), float("inf")])
def test_simulator_rejects_invalid_timestep(dt):
    with pytest.raises(ValueError, match="dt must be finite and positive"):
        Simulator(None, None, None, dt=dt, duration=0.2)


@pytest.mark.parametrize("duration", [-1.0, float("nan"), float("inf")])
def test_simulator_rejects_invalid_run_duration(duration):
    with pytest.raises(ValueError, match="duration must be finite and non-negative"):
        Simulator(None, None, None, dt=0.1, duration=duration)


@pytest.mark.parametrize("duration", [-1.0, float("nan"), float("inf")])
def test_simulator_rejects_invalid_segment_duration(duration):
    execution = IdealExecution()
    simulator = Simulator(
        {"obstacles": []}, execution, rectangle(0, 0, 0.1, 0.1), dt=0.1, duration=0.2,
    )

    with pytest.raises(ValueError, match="segment duration must be finite and non-negative"):
        simulator.run([{"type": "forward", "speed": 1.0, "duration": duration}])

    assert execution.state.time == 0.0
