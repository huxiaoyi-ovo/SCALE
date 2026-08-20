"""Create one E0 and one E1 Phase-0 run from a pilot configuration."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.metrics import compute
from experiments.logger import write_run
from simulation.execution import FirstOrderExecution, IdealExecution
from simulation.geometry import footprint
from simulation.maps import load_layout, preview
from simulation.simulator import Simulator


def _load(path):
    with open(path) as stream:
        return yaml.safe_load(stream)


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _plot(path, rows, layout):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(); preview(ax, layout)
    ax.plot([row["x"] for row in rows], [row["y"] for row in rows], color="tab:blue")
    ax.set_xlabel("world x (m)"); ax.set_ylabel("world y (m)")
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)


def _run_dir(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    number = 1
    while (output / "run_{:04d}".format(number)).exists(): number += 1
    return output / "run_{:04d}".format(number)


def run(config):
    profiles = _load(config["execution_profiles"])["profiles"]
    layout = load_layout(config["layout"])
    shape = footprint(config["robot_footprint"])
    result = []
    for model_name, profile_name in (("E0", "ideal"), ("E1", config["execution_profile"])):
        profile = {} if model_name == "E0" else profiles[profile_name]
        execution = IdealExecution(layout["start"]) if model_name == "E0" else FirstOrderExecution.from_profile(profile, layout["start"])
        rows = Simulator(layout, execution, shape, config["dt"], config["duration"]).run(config["scripted_commands"])
        path = _run_dir(config["output_directory"])
        metadata = {"run_id": path.name, "execution_model": model_name, "execution_profile": profile_name,
                    "layout": layout["layout_id"], "seed": config["seed"], "git_commit": _git_commit(),
                    "timestamp": datetime.now(timezone.utc).isoformat(), "valid": True}
        resolved_config = dict(config)
        resolved_config.update({"execution_model": model_name,
                                "execution_profile_name": profile_name,
                                "execution_profile_parameters": profile})
        write_run(path, resolved_config, metadata, rows, compute(rows, layout["goal"]))
        _plot(path / "trajectory.png", rows, layout)
        result.append(path)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/pilot.yaml")
    args = parser.parse_args()
    run(_load(args.config))


if __name__ == "__main__":
    main()
