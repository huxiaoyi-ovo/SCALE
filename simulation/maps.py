"""Prompt-format layout loading and preview."""
from pathlib import Path
import yaml
from .execution import Pose2D
from .geometry import circle, rectangle


def _pose(spec):
    return Pose2D(spec["x"], spec["y"], spec.get("yaw", 0.0))


def _obstacle(spec):
    if spec["type"] == "rectangle":
        return rectangle(spec["x"], spec["y"], spec["width"], spec["length"], spec.get("yaw", 0.0))
    if spec["type"] == "circle":
        return circle(spec["x"], spec["y"], spec["radius"])
    raise ValueError("unsupported obstacle type: {}".format(spec["type"]))


def load_layout(source):
    if isinstance(source, (str, Path)):
        with Path(source).open() as stream:
            source = yaml.safe_load(stream)
    layout = source.get("layout", source)
    return {"layout_id": layout["layout_id"], "arena": dict(layout["arena"]), "start": _pose(layout["start"]),
            "goal": _pose(layout["goal"]), "obstacles": [_obstacle(item) for item in layout.get("obstacles", [])]}


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
