import math

import pytest

from simulation.geometry import circle, footprint, rectangle


@pytest.mark.parametrize("width, length", [(-1, 1), (1, 0), (math.inf, 1), (1, math.nan)])
def test_rectangles_require_positive_finite_dimensions(width, length):
    with pytest.raises(ValueError, match="rectangle width and length"):
        rectangle(0, 0, width, length)


@pytest.mark.parametrize("radius", [-1, 0, math.inf, math.nan])
def test_circles_require_positive_finite_radius(radius):
    with pytest.raises(ValueError, match="circle radius"):
        circle(0, 0, radius)


@pytest.mark.parametrize("points", [
    [],
    [(0, 0), (1, 1), (2, 2)],
    [(0, 0), (2, 2), (1, 0), (0, 1)],
])
def test_polygons_reject_empty_degenerate_and_self_intersecting_footprints(points):
    with pytest.raises(ValueError, match="footprint polygon must be valid"):
        footprint({"type": "polygon", "points": points})


def test_polygon_accepts_a_valid_footprint():
    points = iter([(0, 0), (1, 0), (0, 1)])
    shape = footprint({"type": "polygon", "points": points})
    assert shape.area == 0.5
