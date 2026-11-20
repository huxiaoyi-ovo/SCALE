import math

import pytest

from simulation.maps import load_layout


@pytest.fixture
def layout():
    return {
        "layout_id": "fixture",
        "arena": {"width": 2, "height": 1},
        "start": {"x": 0.0, "y": 0.0},
        "goal": {"x": 1.0, "y": 0.0},
    }


@pytest.mark.parametrize("axis, value", [("width", -1), ("height", 0), ("width", math.inf), ("height", math.nan)])
def test_layout_rejects_invalid_arena_dimensions(layout, axis, value):
    layout["arena"][axis] = value

    with pytest.raises(ValueError, match="arena width and height"):
        load_layout(layout)


@pytest.mark.parametrize("label, field, value", [
    ("start", "x", math.nan), ("goal", "yaw", math.inf), ("goal", "y", -math.inf),
])
def test_layout_rejects_nonfinite_pose_values(layout, label, field, value):
    layout[label][field] = value

    with pytest.raises(ValueError, match="layout {} pose coordinates and yaw".format(label)):
        load_layout(layout)
