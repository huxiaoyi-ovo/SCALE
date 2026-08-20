"""The six and only six Phase-0 metrics."""
import math

METRIC_NAMES = ("duration", "path_length", "minimum_clearance", "collision",
                "final_position_error", "final_yaw_error")


def compute(rows, goal):
    final = rows[-1]
    path_length = sum(math.hypot(b["x"] - a["x"], b["y"] - a["y"]) for a, b in zip(rows, rows[1:]))
    yaw_error = (final["yaw"] - goal.yaw + math.pi) % (2 * math.pi) - math.pi
    return {"duration": final["time"], "path_length": path_length,
            "minimum_clearance": min(row["clearance"] for row in rows),
            "collision": any(row["collision"] for row in rows),
            "final_position_error": math.hypot(final["x"] - goal.x, final["y"] - goal.y),
            "final_yaw_error": abs(yaw_error)}
