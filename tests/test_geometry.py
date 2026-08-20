import pytest
import yaml
from simulation.execution import Pose2D
from simulation.geometry import circle, collision, minimum_clearance, rectangle, transform_footprint
from simulation.maps import load_layout


def test_separated_shapes_do_not_collide():
    assert not collision(rectangle(0, 0, 1, 1), [circle(3, 0, .5)])


def test_touching_is_collision():
    assert collision(rectangle(0, 0, 2, 2), [rectangle(1.5, 0, 1, 1)])


def test_overlap_is_collision():
    assert collision(rectangle(0, 0, 2, 2), [circle(0, 0, .1)])


def test_rotated_footprint_transform():
    shape = transform_footprint(rectangle(0, 0, 2, 1), Pose2D(yaw=1.57079632679))
    assert shape.bounds[3] - shape.bounds[1] == pytest.approx(2)


def test_minimum_clearance():
    assert minimum_clearance(rectangle(0, 0, 1, 1), [circle(3, 0, .5)]) == pytest.approx(2)


def test_layout_yaml_parsing(tmp_path):
    path = tmp_path / "layout.yaml"
    path.write_text(yaml.safe_dump({"layout": {"layout_id": "test", "arena": {"width": 2, "height": 2},
        "start": {"x": 0, "y": 0}, "goal": {"x": 1, "y": 1, "yaw": .2},
        "obstacles": [{"type": "circle", "x": .5, "y": .5, "radius": .1}]}}))
    layout = load_layout(path)
    assert layout["layout_id"] == "test" and layout["goal"].yaw == .2 and len(layout["obstacles"]) == 1
