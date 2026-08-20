import math
import pytest
from simulation.execution import Command, EmpiricalExecution, FirstOrderExecution, IdealExecution, Pose2D


def test_e0_forward():
    assert IdealExecution().step(Command(vx=2), .5).x == pytest.approx(1)


def test_e0_lateral():
    assert IdealExecution().step(Command(vy=2), .5).y == pytest.approx(1)


def test_e0_rotation():
    assert IdealExecution().step(Command(wz=math.pi), .5).yaw == pytest.approx(math.pi / 2)


def test_e0_combined_exact_se2():
    state = IdealExecution().step(Command(vx=1, wz=math.pi / 2), 1)
    assert (state.x, state.y) == pytest.approx((2 / math.pi, 2 / math.pi))


def test_e1_steady_response():
    assert FirstOrderExecution(tau_x=0).step(Command(vx=1), .1).vx == pytest.approx(1)


def test_e1_lag():
    state = FirstOrderExecution(tau_x=.1).step(Command(vx=1), .1)
    assert 0 < state.vx < 1


def test_e1_delay_holds_active_command():
    model = FirstOrderExecution(delay=.2, tau_x=0)
    assert model.step(Command(vx=1), .1).vx == 0
    assert model.step(Command(vx=1), .1).vx == 0
    assert model.step(Command(vx=1), .1).vx == 1
    assert model.step(Command(), .1).vx == 1


def test_empirical_not_implemented():
    with pytest.raises(NotImplementedError):
        EmpiricalExecution().step(Command(), .1)
