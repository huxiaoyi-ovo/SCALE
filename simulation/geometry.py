"""Shapely geometry for layouts, robot footprints, and clearance."""
from shapely.affinity import rotate, translate
from shapely.geometry import Point, Polygon


def rectangle(x, y, width, length, yaw=0.0):
    shape = Polygon([(-width / 2, -length / 2), (width / 2, -length / 2),
                     (width / 2, length / 2), (-width / 2, length / 2)])
    return translate(rotate(shape, yaw, origin=(0, 0), use_radians=True), xoff=x, yoff=y)


def circle(x, y, radius, resolution=32):
    return Point(x, y).buffer(radius, resolution=resolution)


def footprint(spec):
    kind = spec["type"]
    if kind == "rectangle":
        return rectangle(0, 0, spec["width"], spec["length"], spec.get("yaw", 0.0))
    if kind == "polygon":
        return Polygon(spec["points"])
    raise ValueError("unsupported footprint type: {}".format(kind))


def transform_footprint(shape, pose):
    return translate(rotate(shape, pose.yaw, origin=(0, 0), use_radians=True), xoff=pose.x, yoff=pose.y)


def collision(shape, obstacles):
    return any(shape.intersects(obstacle) for obstacle in obstacles)


def minimum_clearance(shape, obstacles):
    return min((shape.distance(obstacle) for obstacle in obstacles), default=float("inf"))
