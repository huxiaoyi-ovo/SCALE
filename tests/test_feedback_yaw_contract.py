import importlib.util
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


def _install_ros_stubs():
    rospy = ModuleType("rospy")
    geometry_msgs = ModuleType("geometry_msgs")
    geometry_msgs_msg = ModuleType("geometry_msgs.msg")
    nav_msgs = ModuleType("nav_msgs")
    nav_msgs_msg = ModuleType("nav_msgs.msg")
    services = ModuleType("scale_planner_bridge.srv")
    services.Initialize = services.InitializeRequest = services.Step = services.StepRequest = object
    geometry_msgs_msg.PoseStamped = geometry_msgs_msg.Quaternion = object
    nav_msgs_msg.OccupancyGrid = nav_msgs_msg.MapMetaData = nav_msgs_msg.Path = object
    sys.modules.update({
        "rospy": rospy,
        "geometry_msgs": geometry_msgs,
        "geometry_msgs.msg": geometry_msgs_msg,
        "nav_msgs": nav_msgs,
        "nav_msgs.msg": nav_msgs_msg,
        "scale_planner_bridge": ModuleType("scale_planner_bridge"),
        "scale_planner_bridge.srv": services,
    })


_install_ros_stubs()
_MODULE_PATH = Path(__file__).parents[1] / "navigation/scale_planner_bridge/scripts/planner_execution_smoke.py"
_SPEC = importlib.util.spec_from_file_location("planner_execution_smoke", _MODULE_PATH)
smoke = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(smoke)


def _reply(yaw, *, x=1.0):
    return SimpleNamespace(
        logical_time=3.0,
        feedback=SimpleNamespace(
            header=SimpleNamespace(stamp=SimpleNamespace(to_sec=lambda: 13.0)),
            pose=SimpleNamespace(pose=SimpleNamespace(
                position=SimpleNamespace(x=x, y=2.0),
                orientation=SimpleNamespace(z=math.sin(yaw / 2.0), w=math.cos(yaw / 2.0)),
            )),
            twist=SimpleNamespace(twist=SimpleNamespace(
                linear=SimpleNamespace(x=0.1, y=0.2), angular=SimpleNamespace(z=0.3),
            )),
        ),
    )


def _state(yaw=0.0):
    return SimpleNamespace(time=3.0, x=1.0, y=2.0, yaw=yaw, vx=0.1, vy=0.2, wz=0.3)


@pytest.mark.parametrize("actual, expected", [
    (0.0, 2.0 * math.pi),
    (0.0, -2.0 * math.pi),
    (6.276502071760585, -6.2898685425985885),
])
def test_feedback_yaw_accepts_equivalent_wrapped_representations(actual, expected):
    smoke.verify_feedback(_reply(actual), _state(expected), 10.0)


def test_feedback_yaw_rejects_genuine_error_larger_than_tolerance():
    with pytest.raises(smoke.ContractViolation, match="feedback_yaw mismatch"):
        smoke.verify_feedback(_reply(2.0 * smoke.TOLERANCE), _state(), 10.0)


def test_feedback_nonangular_fields_remain_linear():
    with pytest.raises(smoke.ContractViolation, match="feedback_x mismatch"):
        smoke.verify_feedback(_reply(0.0, x=1.0 + 2.0 * smoke.TOLERANCE), _state(), 10.0)
