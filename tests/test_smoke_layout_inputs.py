import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yaml


def _import_smoke(monkeypatch):
    ros_modules = {
        "rospy": SimpleNamespace(),
        "geometry_msgs.msg": SimpleNamespace(PoseStamped=object, Quaternion=object),
        "nav_msgs.msg": SimpleNamespace(OccupancyGrid=object, MapMetaData=object, Path=object),
        "scale_planner_bridge.srv": SimpleNamespace(
            Initialize=object, InitializeRequest=dict, Step=object, StepRequest=object,
        ),
    }
    for name, module in ros_modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    script = (Path(__file__).resolve().parents[1] / "navigation/scale_planner_bridge/scripts"
              / "planner_execution_smoke.py")
    spec = importlib.util.spec_from_file_location("smoke_layout_fixture", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("file_backed", [False, True])
def test_smoke_initializes_ros_with_resolved_layout(file_backed, tmp_path, monkeypatch):
    smoke = _import_smoke(monkeypatch)
    layout = {
        "layout_id": "unit",
        "arena": {"width": 2, "height": 1},
        "start": {"x": 0, "y": 0},
        "goal": {"x": 1, "y": 0},
        "obstacles": [],
    }
    source = {"layout": layout}
    if file_backed:
        path = tmp_path / "layout.yaml"
        path.write_text(yaml.safe_dump(source))
        source = str(path)
    config = {"layout": source, "dt": 0.01, "duration": 0.2}
    smoke.map_from_layout = lambda raw: raw["arena"]
    smoke.fixed_plan = lambda start, goal: (start, goal)
    smoke.rospy.get_param = lambda name, default=0.05: default
    smoke.rospy.wait_for_service = lambda *args, **kwargs: None

    def initialize(request):
        assert request["map"] == layout["arena"]
        assert request["plan"] == (layout["start"], layout["goal"])
        return SimpleNamespace(ok=False, error="fixture stops after initialization")

    smoke.rospy.ServiceProxy = lambda *args: initialize
    with pytest.raises(RuntimeError, match="fixture stops after initialization"):
        smoke.run(config)
