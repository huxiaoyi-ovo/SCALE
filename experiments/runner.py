"""Create one E0 and one E1 Phase-0 run from a pilot configuration."""
import argparse
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
import subprocess
import sys
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
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
        git_info = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel", "HEAD"],
            cwd=PROJECT_ROOT, text=True, stderr=subprocess.DEVNULL,
        ).rstrip("\n")
    except (OSError, subprocess.CalledProcessError):
        return None
    top_level, separator, commit = git_info.rpartition("\n")
    if separator and Path(top_level).resolve() == PROJECT_ROOT:
        return commit
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
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for number in count(1):
        path = output / "run_{:04d}".format(number)
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path


def run(config):
    profiles = config["execution_profiles"]
    profiles_from_file = isinstance(profiles, (str, Path))
    selected_profile_name = config["execution_profile"]
    profile_document = _load(profiles) if profiles_from_file else profiles
    selected_profile = profile_document["profiles"][selected_profile_name]
    layout_spec = config["layout"]
    if isinstance(layout_spec, (str, Path)):
        layout_file = _load(layout_spec)
        layout_spec = layout_file.get("layout", layout_file)
    layout = load_layout(layout_spec)
    shape = footprint(config["robot_footprint"])
    commit = _git_commit()
    result = []
    for model_name, profile_name in (("E0", "ideal"), ("E1", selected_profile_name)):
        profile = {} if model_name == "E0" else selected_profile
        execution = IdealExecution(layout["start"]) if model_name == "E0" else FirstOrderExecution.from_profile(profile, layout["start"])
        rows = Simulator(layout, execution, shape, config["dt"], config["duration"]).run(config["scripted_commands"])
        path = _run_dir(config["output_directory"])
        metadata = {"run_id": path.name, "execution_model": model_name, "execution_profile": profile_name,
                    "layout": layout["layout_id"], "seed": config["seed"], "git_commit": commit,
                    "timestamp": datetime.now(timezone.utc).isoformat(), "valid": True}
        resolved_config = dict(config)
        resolved_config.update({"layout": layout_spec, "execution_model": model_name,
                                "execution_profiles": {"profiles": {selected_profile_name: selected_profile}},
                                "execution_profile_name": profile_name,
                                "execution_profile_parameters": profile})
        if profiles_from_file:
            resolved_config["execution_profiles_source"] = str(profiles)
        _plot(path / "trajectory.png", rows, layout)
        write_run(path, resolved_config, metadata, rows, compute(rows, layout["goal"]))
        result.append(path)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    if args.config is None:
        config_path = PROJECT_ROOT / "configs/pilot.yaml"
        reference_roots = (PROJECT_ROOT,)
    else:
        config_path = args.config.resolve()
        reference_roots = (Path.cwd(), config_path.parent, PROJECT_ROOT)

    config = _load(config_path)
    for key in ("execution_profiles", "layout"):
        source = config[key]
        if isinstance(source, str) and not Path(source).is_absolute():
            candidates = [root / source for root in reference_roots]
            config[key] = str(next((path for path in candidates if path.is_file()), candidates[0]))
    run(config)


if __name__ == "__main__":
    main()
