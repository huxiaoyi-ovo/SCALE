"""Shapely geometry for layouts, robot footprints, and clearance."""
import math

from shapely.affinity import rotate, translate
from shapely.geometry import Point, Polygon


def rectangle(x, y, width, length, yaw=0.0):
    if not all(math.isfinite(value) and value > 0 for value in (width, length)):
        raise ValueError("rectangle width and length must be finite and positive")
    if not all(math.isfinite(value) for value in (x, y, yaw)):
        raise ValueError("rectangle position and yaw must be finite")
    shape = Polygon([(-width / 2, -length / 2), (width / 2, -length / 2),
                     (width / 2, length / 2), (-width / 2, length / 2)])
    return translate(rotate(shape, yaw, origin=(0, 0), use_radians=True), xoff=x, yoff=y)


def circle(x, y, radius, resolution=32):
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("circle radius must be finite and positive")
    if not all(math.isfinite(value) for value in (x, y)):
        raise ValueError("circle position must be finite")
    return Point(x, y).buffer(radius, resolution=resolution)


def footprint(spec):
    kind = spec["type"]
    if kind == "rectangle":
        return rectangle(0, 0, spec["width"], spec["length"], spec.get("yaw", 0.0))
    if kind == "polygon":
        points = [tuple(point) for point in spec["points"]]
        if not all(math.isfinite(coordinate) for point in points for coordinate in point):
            raise ValueError("footprint polygon coordinates must be finite")
        shape = Polygon(points)
        if not shape.is_valid or shape.area <= 0:
            raise ValueError("footprint polygon must be valid and have positive area")
        return shape
    raise ValueError("unsupported footprint type: {}".format(kind))


def transform_footprint(shape, pose):
    return translate(rotate(shape, pose.yaw, origin=(0, 0), use_radians=True), xoff=pose.x, yoff=pose.y)


def collision(shape, obstacles):
    return any(shape.intersects(obstacle) for obstacle in obstacles)


def minimum_clearance(shape, obstacles):
    return min((shape.distance(obstacle) for obstacle in obstacles), default=float("inf"))
