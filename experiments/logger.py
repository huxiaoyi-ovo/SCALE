import csv
import json
import math
from pathlib import Path


def write_run(path, config, metadata, trajectory, metrics):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    json_metrics = dict(metrics)
    if json_metrics.get("minimum_clearance") == math.inf:
        json_metrics["minimum_clearance"] = None
    metrics_text = json.dumps(json_metrics, indent=2, sort_keys=True, allow_nan=False) + "\n"
    import yaml
    (path / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=True))
    (path / "metrics.json").write_text(metrics_text)
    with (path / "trajectory.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=trajectory[0].keys())
        writer.writeheader(); writer.writerows(trajectory)
    metadata_temp = path / ".metadata.json.tmp"
    metadata_temp.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    metadata_temp.replace(path / "metadata.json")
