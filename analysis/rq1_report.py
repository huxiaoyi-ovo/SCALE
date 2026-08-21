#!/usr/bin/env python3
"""Fail-closed, descriptive-only report for the frozen synthetic RQ1 matrix."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data/rq1_synthetic"
PROFILE_IDS = ("e0", "delay_050", "delay_100", "delay_200", "tau_x_100", "tau_x_300", "tau_y_150", "tau_y_300", "tau_y_500", "tau_w_100", "tau_w_300")
PLANNERS = ("tr", "teb")
PARTITIONS = ("discovery", "holdout")
BOOTSTRAP_SEED = 20260828
RESAMPLES = 5000


def _rows(path):
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pct(values, quantile):
    values = sorted(values)
    index = (len(values) - 1) * quantile
    lo, hi = int(index), min(int(index) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def _seed(*parts):
    return BOOTSTRAP_SEED + int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16) % 100000


def _bootstrap(values, seed):
    if not values:
        raise RuntimeError("cannot bootstrap empty layout group")
    rng = random.Random(seed)
    estimates = [sum(values[rng.randrange(len(values))] for _ in values) / len(values) for _ in range(RESAMPLES)]
    estimate = sum(values) / len(values)
    return estimate, _pct(estimates, .025), _pct(estimates, .975)


def _value(row, metric):
    if metric == "success":
        return float(row["success"].lower() == "true")
    if metric == "normalized_path_progress":
        return float(row[metric])
    if metric == "collision":
        return float(row["collision"].lower() == "true")
    if metric == "logical_timeout":
        return float(row["reason"] in ("duration", "logical_timeout"))
    if metric == "planner_failure":
        return float(float(row["planner_failures"]) > 0)
    raise KeyError(metric)


def _write(path, data, fields):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)


def _check(output):
    output = Path(output)
    lock = json.loads((output / "lock.json").read_text())
    core = lock.get("lock_core", {})
    if not lock.get("success") or _hash(core) != lock.get("lock_hash"):
        raise RuntimeError("invalid RQ1 lock")
    contracts = core.get("preflight", {}).get("contracts", {})
    if not all(contracts.get(name) is True for name in ("timing", "feedback", "command_hold", "determinism")):
        raise RuntimeError("preflight contract is not locked as passed")
    if any(_file_hash(ROOT / path) != digest for path, digest in core.get("code_hashes", {}).items()):
        raise RuntimeError("source hash drift")
    records = _rows(output / "episodes.csv")
    if len(records) != 880 or len({row["episode_id"] for row in records}) != 880:
        raise RuntimeError("report requires exactly 880 unique episodes")
    if any(row.get("valid") != "true" or row.get("lock_hash") != lock["lock_hash"] for row in records):
        raise RuntimeError("invalid terminal episode lock")
    if any("normalized_path_progress" not in row for row in records):
        raise RuntimeError("missing normalized_path_progress")
    keys = {(row["partition"], row["layout_id"], row["planner"], row["profile_id"]) for row in records}
    if len(keys) != 880 or {row["planner"] for row in records} != set(PLANNERS) or {row["profile_id"] for row in records} != set(PROFILE_IDS):
        raise RuntimeError("episode matrix mismatch")
    if any(sum(row["partition"] == partition for row in records) != 440 for partition in PARTITIONS):
        raise RuntimeError("partition episode count mismatch")
    for partition in PARTITIONS:
        layouts = {row["layout_id"] for row in records if row["partition"] == partition}
        if len(layouts) != 20:
            raise RuntimeError("partition layout count mismatch")
        for layout in layouts:
            for planner in PLANNERS:
                for profile in PROFILE_IDS:
                    if (partition, layout, planner, profile) not in keys:
                        raise RuntimeError("incomplete layout planner profile cell")
    for row in records:
        if not all(row.get(name) == "true" for name in ("time_contract", "feedback_contract", "command_hold_contract", "collision_truth_contract")):
            raise RuntimeError("episode contract failure")
        try:
            with gzip.open(output / "traces" / (row["episode_id"] + ".json.gz"), "rt") as handle:
                json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("unreadable locked trace: {}".format(row["episode_id"])) from error
    return lock, records


def _descriptive(records):
    results = []
    metrics = ("success", "normalized_path_progress", "collision", "logical_timeout", "planner_failure")
    groups = defaultdict(list)
    for row in records:
        groups[(row["partition"], row["planner"], row["profile_id"])].append(row)
    for (partition, planner, profile), group in sorted(groups.items()):
        for metric in metrics:
            values = [_value(row, metric) for row in group]
            estimate, low, high = _bootstrap(values, _seed(partition, planner, profile, metric, "descriptive"))
            results.append({"partition": partition, "planner": planner, "profile_id": profile, "metric": metric,
                            "n_layouts": len(values), "estimate": estimate, "ci_low": low, "ci_high": high})
    return results


def _contrasts(records):
    index = {(r["partition"], r["layout_id"], r["planner"], r["profile_id"]): r for r in records}
    effects, interactions = [], []
    for partition in PARTITIONS:
        layouts = sorted({r["layout_id"] for r in records if r["partition"] == partition})
        for planner in PLANNERS:
            for profile in PROFILE_IDS[1:]:
                for metric in ("success", "normalized_path_progress"):
                    values = [_value(index[(partition, layout, planner, profile)], metric) - _value(index[(partition, layout, planner, "e0")], metric) for layout in layouts]
                    estimate, low, high = _bootstrap(values, _seed(partition, planner, profile, metric, "paired"))
                    effects.append({"partition": partition, "planner": planner, "profile_id": profile, "metric": metric,
                                    "contrast": "profile_minus_e0", "n_layouts": len(values), "estimate": estimate, "ci_low": low, "ci_high": high})
        for profile in PROFILE_IDS[1:]:
            for metric in ("success", "normalized_path_progress"):
                values = [(_value(index[(partition, layout, "teb", profile)], metric) - _value(index[(partition, layout, "teb", "e0")], metric)) - (_value(index[(partition, layout, "tr", profile)], metric) - _value(index[(partition, layout, "tr", "e0")], metric)) for layout in layouts]
                estimate, low, high = _bootstrap(values, _seed(partition, profile, metric, "interaction"))
                interactions.append({"partition": partition, "profile_id": profile, "metric": metric,
                                     "contrast": "TEB_minus_TR_profile_minus_E0", "n_layouts": len(values), "estimate": estimate, "ci_low": low, "ci_high": high})
    return effects, interactions


def _figures(destination, descriptive, interactions):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors, markers = {"tr": "#0072B2", "teb": "#D55E00"}, {"tr": "o", "teb": "s"}
    positions = list(range(len(PROFILE_IDS)))
    def selected(partition, planner, metric):
        return [next(row for row in descriptive if row["partition"] == partition and row["planner"] == planner and row["profile_id"] == profile and row["metric"] == metric) for profile in PROFILE_IDS]
    def save(figure, name):
        figure.savefig(destination / name, dpi=180, bbox_inches="tight")
        plt.close(figure)

    for metric, name, ylabel in (("success", "success_response.png", "success rate"), ("normalized_path_progress", "progress_response.png", "mean normalized path progress")):
        figure, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
        for axis, partition in zip(axes, PARTITIONS):
            for planner, offset in (("tr", -0.08), ("teb", 0.08)):
                data = selected(partition, planner, metric)
                axis.errorbar([x + offset for x in positions], [r["estimate"] for r in data],
                              yerr=[[r["estimate"] - r["ci_low"] for r in data], [r["ci_high"] - r["estimate"] for r in data]],
                              color=colors[planner], marker=markers[planner], label=planner.upper(), capsize=2)
            axis.set_ylim(0, 1); axis.set_ylabel(partition + "\n" + ylabel); axis.legend()
        axes[-1].set_xticks(positions); axes[-1].set_xticklabels(PROFILE_IDS, rotation=40, ha="right")
        save(figure, name)

    figure, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    failure_metrics, hatches = ("collision", "logical_timeout", "planner_failure"), ("//", "\\\\", "xx")
    for axis, partition in zip(axes, PARTITIONS):
        for planner, offset in (("tr", -0.2), ("teb", 0.2)):
            bottom = [0.0] * len(PROFILE_IDS)
            for metric, hatch in zip(failure_metrics, hatches):
                values = [r["estimate"] for r in selected(partition, planner, metric)]
                axis.bar([x + offset for x in positions], values, .36, bottom=bottom, color=colors[planner], hatch=hatch,
                         alpha=.8, edgecolor="black", linewidth=.35, label="{} {}".format(planner.upper(), metric))
                bottom = [a + b for a, b in zip(bottom, values)]
        axis.set_ylim(0, 1); axis.set_ylabel(partition + "\nfailure rate"); axis.legend(ncol=3, fontsize=7)
    axes[-1].set_xticks(positions); axes[-1].set_xticklabels(PROFILE_IDS, rotation=40, ha="right")
    save(figure, "failure_modes.png")

    figure, axes = plt.subplots(2, 2, figsize=(12, 6.5), sharex=True)
    for column, partition in enumerate(PARTITIONS):
        for row, metric in enumerate(("success", "normalized_path_progress")):
            axis = axes[row, column]
            data = [next(item for item in interactions if item["partition"] == partition and item["profile_id"] == profile and item["metric"] == metric) for profile in PROFILE_IDS[1:]]
            axis.axhline(0, color="black", linewidth=.7)
            axis.errorbar(range(len(data)), [item["estimate"] for item in data],
                          yerr=[[item["estimate"] - item["ci_low"] for item in data], [item["ci_high"] - item["estimate"] for item in data]],
                          color="#009E73", marker="D", linestyle="none", capsize=2)
            axis.set_title("{} — {}".format(partition, metric)); axis.set_ylabel("TEB − TR interaction")
            axis.set_xticks(range(len(data))); axis.set_xticklabels(PROFILE_IDS[1:], rotation=40, ha="right", fontsize=8)
    save(figure, "interaction_contrasts.png")


def analyze(output=OUT):
    output = Path(output)
    lock, records = _check(output)
    destination = output / "analysis"
    destination.mkdir(parents=True, exist_ok=True)
    descriptive = _descriptive(records)
    effects, interactions = _contrasts(records)
    _write(destination / "descriptive.csv", descriptive, ("partition", "planner", "profile_id", "metric", "n_layouts", "estimate", "ci_low", "ci_high"))
    _write(destination / "paired_effects.csv", effects, ("partition", "planner", "profile_id", "metric", "contrast", "n_layouts", "estimate", "ci_low", "ci_high"))
    _write(destination / "interaction_contrasts.csv", interactions, ("partition", "profile_id", "metric", "contrast", "n_layouts", "estimate", "ci_low", "ci_high"))
    _figures(destination, descriptive, interactions)
    outcomes = Counter(row["reason"] for row in records)
    attempts = Counter(row["status"] for row in _rows(output / "attempts.csv")) if (output / "attempts.csv").exists() else Counter()
    partition_summary = {}
    for partition in PARTITIONS:
        partition_summary[partition] = {}
        for planner in PLANNERS:
            subset = [row for row in records if row["partition"] == partition and row["planner"] == planner]
            e0 = [row for row in subset if row["profile_id"] == "e0"]
            partition_summary[partition][planner] = {
                "e0_success_rate": round(sum(_value(row, "success") for row in e0) / len(e0), 6),
                "e0_mean_normalized_path_progress": round(sum(_value(row, "normalized_path_progress") for row in e0) / len(e0), 6),
                "all_profile_success_rate": round(sum(_value(row, "success") for row in subset) / len(subset), 6),
                "all_profile_mean_normalized_path_progress": round(sum(_value(row, "normalized_path_progress") for row in subset) / len(subset), 6),
                "terminal_reasons": dict(sorted(Counter(row["reason"] for row in subset).items())),
            }
    report = """# Synthetic RQ1 Planner × Execution Study

SYNTHETIC — NOT PHYSICALLY IDENTIFIED. All uncertainty is descriptive layout-level percentile bootstrap (95%, 5,000 resamples); no hypothesis tests, significance claims, or GO/NO-GO decision are made here.

## Frozen provenance

- Lock: `{lock}`
- Protocol/layout/schedule hashes: `{protocol}` / `{layouts}` / `{schedule}`
- Seeds: layouts 20260826; schedule 20260827; bootstrap 20260828.
- 880 valid locked episodes and readable traces: 440 discovery, 440 holdout.
- TR is official `dwa_local_planner/DWAPlannerROS` with `planner.use_dwa: false`; TEB is official `teb_local_planner/TebLocalPlannerROS`.
- Preflight records static checks, one TR/E0 executor probe, and TR/TEB × E0/E1 restart determinism. Each retained episode independently passed timing, executed-feedback, command-hold, and collision-truth contracts.
- Attempts: `{attempts}`. Exclusions: none; algorithm outcomes remain terminal observations.

## Separate discovery and holdout summaries

`descriptive.csv` reports each partition separately for success, normalized global-path progress, and terminal-reason composition. `paired_effects.csv` contains within-planner profile-minus-E0 changes for success and progress. `interaction_contrasts.csv` contains TEB-minus-TR profile-minus-E0 contrasts. The four figures retain the same profile order and separate discovery from holdout.

Discovery, partition × planner (`E0` then all-profile aggregate plus terminal counts): `{discovery}`.

Holdout, partition × planner (`E0` then all-profile aggregate plus terminal counts): `{holdout}`.

Terminal reasons over all locked episodes: `{outcomes}`.

This report is the endpoint of the synthetic execution run and stops for primary scientific review.
""".format(lock=lock["lock_hash"], protocol=lock["lock_core"]["protocol_hash"], layouts=lock["lock_core"]["layouts_hash"], schedule=lock["lock_core"]["schedule_hash"], attempts=dict(sorted(attempts.items())), discovery=partition_summary["discovery"], holdout=partition_summary["holdout"], outcomes=dict(sorted(outcomes.items())))
    (destination / "REPORT.md").write_text(report)
    return {"episodes": 880, "analysis": str(destination)}


if __name__ == "__main__":
    print(json.dumps(analyze(), sort_keys=True))
