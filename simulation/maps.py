"""Prompt-format layout loading and preview."""
import math
from pathlib import Path
import yaml
from .execution import Pose2D
from .geometry import circle, rectangle


def _pose(spec, label):
    pose = Pose2D(spec["x"], spec["y"], spec.get("yaw", 0.0))
    if not all(math.isfinite(value) for value in (pose.x, pose.y, pose.yaw)):
        raise ValueError("layout {} pose coordinates and yaw must be finite".format(label))
    return pose


def _obstacle(spec):
    if spec["type"] == "rectangle":
        return rectangle(spec["x"], spec["y"], spec["width"], spec["length"], spec.get("yaw", 0.0))
    if spec["type"] == "circle":
        return circle(spec["x"], spec["y"], spec["radius"])
    raise ValueError("unsupported obstacle type: {}".format(spec["type"]))


def load_layout_spec(source):
    if isinstance(source, (str, Path)):
        with Path(source).open() as stream:
            source = yaml.safe_load(stream)
    return source.get("layout", source)


def load_layout(source):
    layout = load_layout_spec(source)
    arena = dict(layout["arena"])
    if not all(math.isfinite(arena[axis]) and arena[axis] > 0 for axis in ("width", "height")):
        raise ValueError("layout arena width and height must be finite and positive")
    return {"layout_id": layout["layout_id"], "arena": arena,
            "start": _pose(layout["start"], "start"), "goal": _pose(layout["goal"], "goal"),
            "obstacles": [_obstacle(item) for item in layout.get("obstacles", [])]}


def preview(ax, layout):
    from matplotlib.patches import Rectangle
    arena = layout["arena"]
    ax.add_patch(Rectangle((0, 0), arena["width"], arena["height"], fill=False))
    for obstacle in layout["obstacles"]:
        x, y = obstacle.exterior.xy
        ax.fill(x, y, color="tab:red", alpha=0.35)
    ax.plot(layout["start"].x, layout["start"].y, "go", label="start")
    ax.plot(layout["goal"].x, layout["goal"].y, "b*", label="goal")
    ax.set_aspect("equal", adjustable="box"); ax.legend()
