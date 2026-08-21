#!/usr/bin/env python3
"""Post hoc, descriptive stability audit of the frozen 880-episode RQ1 data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import random
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/rq1_synthetic/episodes.csv"
DEFAULT_OUTPUT = ROOT / "data/rq1_synthetic/stability_analysis"
PARTITIONS = ("discovery", "holdout")
PLANNERS = ("tr", "teb")
PROFILES = (
    "e0", "delay_050", "delay_100", "delay_200", "tau_x_100",
    "tau_x_300", "tau_y_150", "tau_y_300", "tau_y_500",
    "tau_w_100", "tau_w_300",
)
E1_PROFILES = PROFILES[1:]
MODES = ("success", "collision", "planner_failure", "timeout")
METRICS = ("success", "normalized_path_progress")
EXPECTED_LOCK = "355a6b600b50409b680ffb0e06ee53d75e1a915fb3142bddfb3a3a3180f9c8d5"
BOOTSTRAP_SEED = 20260829
RESAMPLES = 5000
PREFERENCE_TOLERANCE = 1e-12


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _bool(value: str) -> bool:
    if value not in ("true", "false"):
        raise RuntimeError("invalid boolean value: {!r}".format(value))
    return value == "true"


def _terminal_mode(row: dict[str, str]) -> str:
    if _bool(row["success"]):
        return "success"
    if _bool(row["collision"]):
        return "collision"
    if int(row["planner_failures"]) > 0:
        return "planner_failure"
    if row["reason"] in ("duration", "logical_timeout") or row["raw_reason"] in ("duration", "logical_timeout"):
        return "timeout"
    raise RuntimeError("unclassified terminal reason for {}: {!r}/{!r}".format(
        row["episode_id"], row["reason"], row["raw_reason"]))


def _metric(row: dict[str, str], metric: str) -> float:
    if metric == "success":
        return float(_bool(row["success"]))
    if metric == "normalized_path_progress":
        return float(row[metric])
    raise KeyError(metric)


def _seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return BOOTSTRAP_SEED + int(digest[:8], 16)


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _bootstrap_scalar(items, statistic, seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(items)
    samples = []
    for _ in range(RESAMPLES):
        draw = [items[rng.randrange(n)] for _ in range(n)]
        samples.append(statistic(draw))
    return _percentile(samples, .025), _percentile(samples, .975)


def _validate(records: list[dict[str, str]]) -> None:
    required = {
        "episode_id", "partition", "layout_id", "planner", "profile_id",
        "lock_hash", "valid", "success", "reason", "raw_reason", "collision",
        "planner_failures", "normalized_path_progress", "time_contract",
        "feedback_contract", "command_hold_contract", "collision_truth_contract",
    }
    if len(records) != 880 or len({row.get("episode_id") for row in records}) != 880:
        raise RuntimeError("analysis requires exactly 880 unique episodes")
    if not records or not required.issubset(records[0]):
        raise RuntimeError("episodes.csv is missing required fields")
    if {row["lock_hash"] for row in records} != {EXPECTED_LOCK}:
        raise RuntimeError("unexpected or mixed RQ1 lock hash")
    contract_fields = ("valid", "time_contract", "feedback_contract", "command_hold_contract", "collision_truth_contract")
    for row in records:
        if not all(_bool(row[field]) for field in contract_fields):
            raise RuntimeError("invalid episode or failed contract: {}".format(row["episode_id"]))
        progress = float(row["normalized_path_progress"])
        if not 0.0 <= progress <= 1.0:
            raise RuntimeError("normalized progress outside [0,1]: {}".format(row["episode_id"]))
        _terminal_mode(row)
    keys = {(r["partition"], r["layout_id"], r["planner"], r["profile_id"]) for r in records}
    if len(keys) != 880:
        raise RuntimeError("duplicate matrix cell")
    if {r["partition"] for r in records} != set(PARTITIONS):
        raise RuntimeError("partition mismatch")
    if {r["planner"] for r in records} != set(PLANNERS):
        raise RuntimeError("planner mismatch")
    if {r["profile_id"] for r in records} != set(PROFILES):
        raise RuntimeError("profile mismatch")
    for partition in PARTITIONS:
        layouts = sorted({r["layout_id"] for r in records if r["partition"] == partition})
        if len(layouts) != 20:
            raise RuntimeError("{} does not contain 20 layouts".format(partition))
        expected = {(partition, layout, planner, profile) for layout in layouts for planner in PLANNERS for profile in PROFILES}
        if not expected.issubset(keys):
            raise RuntimeError("incomplete matrix in {}".format(partition))


def _jaccard(pairs) -> float:
    intersection = sum((not base) and (not profile) for base, profile in pairs)
    union = sum((not base) or (not profile) for base, profile in pairs)
    return intersection / union if union else 1.0


def _preference(delta: float) -> str:
    if delta > PREFERENCE_TOLERANCE:
        return "teb"
    if delta < -PREFERENCE_TOLERANCE:
        return "tr"
    return "tie"


def _write(path: Path, rows: list[dict], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _analyse(records: list[dict[str, str]]):
    index = {(r["partition"], r["layout_id"], r["planner"], r["profile_id"]): r for r in records}
    scenarios, summaries, transitions, preferences = [], [], [], []

    for partition in PARTITIONS:
        layouts = sorted({r["layout_id"] for r in records if r["partition"] == partition})
        for planner in PLANNERS:
            for profile in E1_PROFILES:
                paired = []
                for layout in layouts:
                    base = index[(partition, layout, planner, "e0")]
                    altered = index[(partition, layout, planner, profile)]
                    base_success, profile_success = _bool(base["success"]), _bool(altered["success"])
                    base_mode, profile_mode = _terminal_mode(base), _terminal_mode(altered)
                    paired.append((base_success, profile_success, base_mode, profile_mode))
                    scenarios.append({
                        "partition": partition, "planner": planner, "profile_id": profile,
                        "layout_id": layout, "e0_success": str(base_success).lower(),
                        "profile_success": str(profile_success).lower(),
                        "outcome_flip": str(base_success != profile_success).lower(),
                        "flip_direction": ("failure_to_success" if not base_success and profile_success else
                                           "success_to_failure" if base_success and not profile_success else "unchanged"),
                        "e0_terminal_mode": base_mode, "profile_terminal_mode": profile_mode,
                        "terminal_mode_changed": str(base_mode != profile_mode).lower(),
                        "e0_failure_member": str(not base_success).lower(),
                        "profile_failure_member": str(not profile_success).lower(),
                        "e0_normalized_path_progress": float(base["normalized_path_progress"]),
                        "profile_normalized_path_progress": float(altered["normalized_path_progress"]),
                    })

                n = len(paired)
                base_rate = sum(p[0] for p in paired) / n
                profile_rate = sum(p[1] for p in paired) / n
                flip = sum(p[0] != p[1] for p in paired) / n
                agreement = 1.0 - flip
                failure_pairs = [(p[0], p[1]) for p in paired]
                jaccard = _jaccard(failure_pairs)
                flip_ci = _bootstrap_scalar(paired, lambda d: sum(x[0] != x[1] for x in d) / len(d), _seed(partition, planner, profile, "flip"))
                agreement_ci = _bootstrap_scalar(paired, lambda d: sum(x[0] == x[1] for x in d) / len(d), _seed(partition, planner, profile, "agreement"))
                jaccard_ci = _bootstrap_scalar(failure_pairs, _jaccard, _seed(partition, planner, profile, "jaccard"))
                failure_e0 = sum(not p[0] for p in paired)
                failure_profile = sum(not p[1] for p in paired)
                intersection = sum((not p[0]) and (not p[1]) for p in paired)
                union = sum((not p[0]) or (not p[1]) for p in paired)
                delta = profile_rate - base_rate
                summaries.append({
                    "partition": partition, "planner": planner, "profile_id": profile, "n_layouts": n,
                    "e0_success_rate": base_rate, "profile_success_rate": profile_rate,
                    "success_rate_delta": delta, "outcome_flip_rate": flip,
                    "outcome_flip_ci_low": flip_ci[0], "outcome_flip_ci_high": flip_ci[1],
                    "outcome_agreement_rate": agreement, "outcome_agreement_ci_low": agreement_ci[0],
                    "outcome_agreement_ci_high": agreement_ci[1],
                    "success_to_failure_count": sum(p[0] and not p[1] for p in paired),
                    "failure_to_success_count": sum((not p[0]) and p[1] for p in paired),
                    "failure_n_e0": failure_e0, "failure_n_profile": failure_profile,
                    "failure_intersection_n": intersection, "failure_union_n": union,
                    "failure_jaccard": jaccard, "failure_jaccard_ci_low": jaccard_ci[0],
                    "failure_jaccard_ci_high": jaccard_ci[1],
                    "terminal_mode_agreement_rate": sum(p[2] == p[3] for p in paired) / n,
                    "hidden_churn_flag": str(abs(delta) <= .05 + 1e-12 and flip >= .20).lower(),
                    "high_stability_flag": str(flip < .05 and jaccard > .90).lower(),
                })
                mode_counts = Counter((p[2], p[3]) for p in paired)
                source_counts = Counter(p[2] for p in paired)
                for source in MODES:
                    for target in MODES:
                        count = mode_counts[(source, target)]
                        transitions.append({
                            "partition": partition, "planner": planner, "profile_id": profile,
                            "e0_terminal_mode": source, "profile_terminal_mode": target,
                            "count": count, "rate_total": count / n,
                            "e0_source_count": source_counts[source],
                            "rate_from_e0_mode": count / source_counts[source] if source_counts[source] else "",
                        })

        for profile in E1_PROFILES:
            for metric in METRICS:
                states = []
                for layout in layouts:
                    base_delta = _metric(index[(partition, layout, "teb", "e0")], metric) - _metric(index[(partition, layout, "tr", "e0")], metric)
                    profile_delta = _metric(index[(partition, layout, "teb", profile)], metric) - _metric(index[(partition, layout, "tr", profile)], metric)
                    states.append((_preference(base_delta), _preference(profile_delta), base_delta, profile_delta))
                change = lambda d: sum(x[0] != x[1] for x in d) / len(d)
                reversal = lambda d: sum({x[0], x[1]} == {"tr", "teb"} for x in d) / len(d)
                change_ci = _bootstrap_scalar(states, change, _seed(partition, profile, metric, "preference_change"))
                reversal_ci = _bootstrap_scalar(states, reversal, _seed(partition, profile, metric, "preference_reversal"))
                base_mean_delta = sum(x[2] for x in states) / len(states)
                profile_mean_delta = sum(x[3] for x in states) / len(states)
                counts = Counter((x[0], x[1]) for x in states)
                row = {
                    "partition": partition, "profile_id": profile, "metric": metric,
                    "n_layouts": len(states), "preference_change_rate": change(states),
                    "preference_change_ci_low": change_ci[0], "preference_change_ci_high": change_ci[1],
                    "strict_reversal_rate": reversal(states), "strict_reversal_ci_low": reversal_ci[0],
                    "strict_reversal_ci_high": reversal_ci[1],
                    "aggregate_teb_minus_tr_e0": base_mean_delta,
                    "aggregate_teb_minus_tr_profile": profile_mean_delta,
                    "aggregate_preference_e0": _preference(base_mean_delta),
                    "aggregate_preference_profile": _preference(profile_mean_delta),
                    "aggregate_preference_flip": str(_preference(base_mean_delta) != _preference(profile_mean_delta)).lower(),
                }
                for source in ("tr", "tie", "teb"):
                    for target in ("tr", "tie", "teb"):
                        row["{}_to_{}".format(source, target)] = counts[(source, target)]
                preferences.append(row)
    return scenarios, summaries, transitions, preferences


def _format(value) -> str:
    if isinstance(value, float):
        return "{:.3f}".format(value)
    return str(value)


def _report(records, summaries, transitions, preferences, source: Path) -> str:
    lock_hash = records[0]["lock_hash"]
    lines = [
        "# RQ1 Evaluation Stability Audit",
        "",
        "> POST HOC, DESCRIPTIVE ONLY — no significance test or scientific GO/NO-GO decision.",
        "",
        "## Analysis contract",
        "",
        "This read-only audit compares each E1 episode with the same planner/layout under E0. "
        "Discovery and holdout remain separate. The source is `{}` (880 valid episodes; lock `{}`).".format(source.as_posix(), lock_hash),
        "Outcome flip, failure-set Jaccard, terminal-mode transitions, and TEB-versus-TR preference stability were fixed before reading scenario-level results. "
        "Intervals are 95% layout-level percentile bootstrap intervals (5,000 resamples; seed 20260829) and are descriptive uncertainty only.",
        "",
        "Terminal modes use the exhaustive priority `success > collision > planner_failure > timeout`. "
        "A failure-set Jaccard of 1 means identical failed-layout sets; the failure-set sizes and union denominator are always shown.",
        "",
        "## Outcome and failure-set stability",
    ]
    for partition in PARTITIONS:
        lines += ["", "### {}".format(partition.title()), "", "| Planner | Profile | E0→profile success | Flip | S→F / F→S | Failure sets E0/profile/union | Jaccard | Terminal agreement |", "|---|---|---:|---:|---:|---:|---:|---:|"]
        for row in summaries:
            if row["partition"] != partition:
                continue
            lines.append("| {planner} | {profile_id} | {e0_success_rate:.2f}→{profile_success_rate:.2f} | {outcome_flip_rate:.2f} [{outcome_flip_ci_low:.2f}, {outcome_flip_ci_high:.2f}] | {success_to_failure_count}/{failure_to_success_count} | {failure_n_e0}/{failure_n_profile}/{failure_union_n} | {failure_jaccard:.2f} [{failure_jaccard_ci_low:.2f}, {failure_jaccard_ci_high:.2f}] | {terminal_mode_agreement_rate:.2f} |".format(**row))
        hidden = sum(r["partition"] == partition and r["hidden_churn_flag"] == "true" for r in summaries)
        stable = sum(r["partition"] == partition and r["high_stability_flag"] == "true" for r in summaries)
        lines += ["", "Diagnostic flags: hidden-churn heuristic `{}/20`; high-stability heuristic `{}/20`. These are screening descriptions, not decision thresholds.".format(hidden, stable)]

    lines += ["", "## Non-zero terminal-mode transitions"]
    for partition in PARTITIONS:
        lines += ["", "### {}".format(partition.title()), "", "| Planner | Profile | E0 mode → profile mode | Count / 20 | Rate within E0 source mode |", "|---|---|---|---:|---:|"]
        for row in transitions:
            if row["partition"] == partition and row["count"]:
                within = "NA" if row["rate_from_e0_mode"] == "" else "{:.2f}".format(row["rate_from_e0_mode"])
                lines.append("| {planner} | {profile_id} | {e0_terminal_mode} → {profile_terminal_mode} | {count} | {within} |".format(within=within, **row))

    lines += ["", "## Planner-preference stability", "", "Preference is reported separately for binary success and normalized path progress; no composite score is used. `TEB` means TEB−TR > 1e-12, `TR` means < −1e-12, otherwise tie. Progress preference is therefore an exact-score descriptive comparison and can be sensitive to very small differences."]
    for partition in PARTITIONS:
        lines += ["", "### {}".format(partition.title()), "", "| Metric | Profile | Any state change | Strict TEB↔TR reversal | Aggregate E0→profile preference | Aggregate TEB−TR E0→profile |", "|---|---|---:|---:|---|---:|"]
        for row in preferences:
            if row["partition"] != partition:
                continue
            lines.append("| {metric} | {profile_id} | {preference_change_rate:.2f} [{preference_change_ci_low:.2f}, {preference_change_ci_high:.2f}] | {strict_reversal_rate:.2f} [{strict_reversal_ci_low:.2f}, {strict_reversal_ci_high:.2f}] | {aggregate_preference_e0}→{aggregate_preference_profile} | {aggregate_teb_minus_tr_e0:.3f}→{aggregate_teb_minus_tr_profile:.3f} |".format(**row))

    lines += [
        "", "## Evidence boundary", "",
        "This audit measures agreement of outcomes under the tested synthetic execution assumptions. It does not establish physical fidelity, generalize beyond these 40 layouts and two local planners, or justify the stronger claim that planners have substantially different execution-response fingerprints. The accountable researcher must make the Scientific Gate decision after reviewing discovery/holdout replication and the CSV-level transitions.",
        "",
    ]
    return "\n".join(lines)


def analyse(input_path: Path, output_dir: Path) -> None:
    records = _read(input_path)
    _validate(records)
    scenarios, summaries, transitions, preferences = _analyse(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(output_dir / "scenario_stability.csv", scenarios, tuple(scenarios[0]))
    _write(output_dir / "stability_summary.csv", summaries, tuple(summaries[0]))
    _write(output_dir / "terminal_transitions.csv", transitions, tuple(transitions[0]))
    _write(output_dir / "preference_stability.csv", preferences, tuple(preferences[0]))
    (output_dir / "EVALUATION_STABILITY_REPORT.md").write_text(
        _report(records, summaries, transitions, preferences, input_path), encoding="utf-8")
    print("stability audit complete: {} scenario pairs, {} summary cells".format(len(scenarios), len(summaries)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    analyse(args.input, args.output)


if __name__ == "__main__":
    main()
