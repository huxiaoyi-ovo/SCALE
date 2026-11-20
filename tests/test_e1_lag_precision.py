import pytest

from simulation.execution import Command, FirstOrderExecution


def test_slow_finite_lag_remains_slow_when_exponential_rounds_to_one():
    execution = FirstOrderExecution(tau_x=1e18)
    state = execution.step(Command(vx=1.0), dt=0.1)

    assert state.vx == pytest.approx(1e-19, rel=1e-12, abs=0.0)
    assert state.x == pytest.approx(5e-21, rel=1e-12, abs=0.0)
