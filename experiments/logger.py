import csv
import json
from pathlib import Path


def write_run(path, config, metadata, trajectory, metrics):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    import yaml
    (path / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=True))
    (path / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    (path / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    with (path / "trajectory.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=trajectory[0].keys())
        writer.writeheader(); writer.writerows(trajectory)
