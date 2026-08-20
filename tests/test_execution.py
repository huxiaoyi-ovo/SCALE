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


def test_command_is_held_across_execution_substeps():
    model = IdealExecution()
    model.set_command(Command(vx=1, vy=.2, wz=.1))
    for _ in range(5):
        model.advance(.01)
    assert (model.state.time, model.state.vx, model.state.vy, model.state.wz) == pytest.approx(
        (.05, 1, .2, .1))


def test_e1_delay_uses_logical_time_inside_substep():
    model = FirstOrderExecution(delay=.025, tau_x=0)
    model.set_command(Command(vx=1))
    assert model.advance(.02).x == 0
    state = model.advance(.01)
    assert (state.time, state.x, state.vx) == pytest.approx((.03, .005, 1))


def test_e1_limiting_case_converges_to_e0_with_multi_rate_commands():
    ideal = IdealExecution()
    limiting = FirstOrderExecution(tau_x=1e-6, tau_y=1e-6, tau_w=1e-6)
    commands = (Command(vx=.4), Command(vy=.2, wz=.1), Command(vx=.1, vy=-.1, wz=-.2))
    maximum_pose_error = 0.0
    maximum_velocity_error = 0.0
    for command in commands:
        ideal.set_command(command)
        limiting.set_command(command)
        for _ in range(5):
            ideal_state = ideal.advance(.01)
            limiting_state = limiting.advance(.01)
            maximum_pose_error = max(maximum_pose_error,
                                     abs(limiting_state.x - ideal_state.x),
                                     abs(limiting_state.y - ideal_state.y),
                                     abs(limiting_state.yaw - ideal_state.yaw))
            maximum_velocity_error = max(maximum_velocity_error,
                                         abs(limiting_state.vx - ideal_state.vx),
                                         abs(limiting_state.vy - ideal_state.vy),
                                         abs(limiting_state.wz - ideal_state.wz))
            assert limiting_state.time == pytest.approx(ideal_state.time, abs=1e-12)
    assert maximum_pose_error < 1e-6
    assert maximum_velocity_error < 1e-12


def test_execution_rejects_non_finite_time_parameters():
    with pytest.raises(ValueError):
        IdealExecution().advance(float("nan"))
    with pytest.raises(ValueError):
        FirstOrderExecution(delay=float("inf"))


def test_empirical_not_implemented():
    with pytest.raises(NotImplementedError):
        EmpiricalExecution().step(Command(), .1)
