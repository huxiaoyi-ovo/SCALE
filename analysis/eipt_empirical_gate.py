#!/usr/bin/env python3
"""Analyse the frozen EIPT snapshot margins and apply the hard scientific gate."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "configs/eipt/protocol.yaml"
DEFAULT_OUTPUT = ROOT / "data/eipt_empirical_gate"
PLANNERS = ("tr", "teb", "dwa")
GROUPS = PLANNERS + ("pooled",)
ORDINARY = ("e_v", "e_x", "c_min", "u_magnitude", "delta_u_magnitude", "m_p")
THETA = ("delay", "tau_x", "tau_y", "tau_w")
INDIVIDUAL = ORDINARY + ("theta_magnitude", "m_pf")
SCORE_SIGN = {"e_v": 1, "e_x": 1, "c_min": -1, "u_magnitude": 1,
              "delta_u_magnitude": 1, "m_p": -1, "theta_magnitude": 1, "m_pf": -1}


def _write(path, rows, fields=None):
    fields = fields or tuple(rows[0])
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def _auc(labels, scores):
    positive = [score for label, score in zip(labels, scores) if label]
    negative = [score for label, score in zip(labels, scores) if not label]
    if not positive or not negative: return float("nan")
    wins = sum(1.0 if left > right else 0.5 if left == right else 0.0 for left in positive for right in negative)
    return wins / (len(positive) * len(negative))


def _average_precision(labels, scores):
    positives = sum(labels)
    if positives == 0: return float("nan")
    groups = defaultdict(list)
    for label, score in zip(labels, scores): groups[float(score)].append(bool(label))
    true_positive = false_positive = 0
    recall_previous = average_precision = 0.0
    for score in sorted(groups, reverse=True):
        true_positive += sum(groups[score]); false_positive += len(groups[score]) - sum(groups[score])
        recall = true_positive / positives
        precision = true_positive / (true_positive + false_positive)
        average_precision += (recall - recall_previous) * precision
        recall_previous = recall
    return average_precision


def _metric_pair(rows, score_name):
    labels = [int(row["y_bad"]) for row in rows]
    scores = [SCORE_SIGN[score_name] * float(row[score_name]) for row in rows]
    return _auc(labels, scores), _average_precision(labels, scores)


def _load(output):
    output = Path(output)
    schedule_payload = json.loads((output / "snapshot_schedule.json").read_text())
    snapshots = schedule_payload["snapshots"]
    if len(snapshots) != 144 or len({row["snapshot_id"] for row in snapshots}) != 144:
        raise RuntimeError("requires 144 unique frozen snapshots")
    protocol = yaml.safe_load(PROTOCOL_PATH.read_text())
    rows = []
    mechanism_names = ("collision", "planner_failure", "command_collapse", "progress_stall",
                       "oscillatory_reversal_vy", "oscillatory_reversal_wz")
    theta_scales = protocol["execution_margin"]["scales"]
    for snapshot in snapshots:
        result_path = output / "query_results" / (snapshot["snapshot_id"] + ".json")
        if not result_path.is_file(): raise RuntimeError("missing query result: " + snapshot["snapshot_id"])
        result = json.loads(result_path.read_text())
        row = {
            "snapshot_id": snapshot["snapshot_id"], "source": snapshot["source"],
            "partition": snapshot["partition"], "planner": snapshot["planner"],
            "layout_id": snapshot["layout_id"], "layout_cluster": snapshot["layout_cluster"],
            "episode_id": snapshot["episode_id"], "profile_id": snapshot["profile_id"],
            "call_index": snapshot["call_index"], "snapshot_time": snapshot["snapshot_time"],
            "normalized_path_progress": snapshot["normalized_path_progress"],
            "y_bad": int(snapshot["y_bad"]), "mechanisms": ";".join(snapshot["mechanisms"]),
        }
        for mechanism in mechanism_names: row["label_" + mechanism] = int(mechanism in snapshot["mechanisms"])
        for name in THETA:
            row[name] = float(snapshot["theta"][name])
            row[name + "_normalized"] = row[name] / float(theta_scales[name])
        row["theta_magnitude"] = math.sqrt(sum(row[name + "_normalized"] ** 2 for name in THETA))
        for name in ORDINARY + ("m_pf",): row[name] = float(result[name])
        for name in ("m_p_censored", "m_pf_censored", "baseline_query_mismatch", "nominal_rollout_failure"):
            row[name] = int(bool(result[name]))
        row["m_p_queries"] = int(result["m_p_queries"]); row["m_pf_queries"] = int(result["m_pf_queries"])
        row["recorded_command"] = json.dumps(snapshot["recorded_command"], sort_keys=True, separators=(",", ":"))
        row["baseline_query_command"] = json.dumps(result["baseline_query_command"], sort_keys=True, separators=(",", ":"))
        rows.append(row)
    return protocol, schedule_payload, rows


def _instrument(protocol, rows):
    contract = protocol["instrument_contract"]
    overall = sum(row["baseline_query_mismatch"] for row in rows) / len(rows)
    per_planner = {planner: sum(row["baseline_query_mismatch"] for row in rows if row["planner"] == planner) /
                   sum(row["planner"] == planner for row in rows) for planner in PLANNERS}
    passed = overall <= contract["maximum_overall_mismatch_fraction"] + 1e-12 and all(
        value <= contract["maximum_per_planner_mismatch_fraction"] + 1e-12 for value in per_planner.values())
    return passed, overall, per_planner


def _fit_transform(discovery, include_mpf):
    continuous = list(ORDINARY) + [name + "_normalized" for name in THETA]
    if include_mpf: continuous.append("m_pf")
    means = {name: float(np.mean([row[name] for row in discovery])) for name in continuous}
    scales = {name: float(np.std([row[name] for row in discovery], ddof=0)) for name in continuous}
    scales = {name: value if value > 1e-12 else 1.0 for name, value in scales.items()}
    return continuous, means, scales


def _design(rows, transform):
    continuous, means, scales = transform
    matrix = []
    for row in rows:
        values = [1.0] + [(float(row[name]) - means[name]) / scales[name] for name in continuous]
        values += [float(row["planner"] == "tr"), float(row["planner"] == "teb")]
        matrix.append(values)
    return np.asarray(matrix, dtype=float)


def _logistic_fit(matrix, labels, penalty):
    labels = np.asarray(labels, dtype=float); coefficients = np.zeros(matrix.shape[1])
    penalized = np.ones(matrix.shape[1]); penalized[0] = 0.0
    for _ in range(100):
        linear = np.clip(matrix @ coefficients, -35, 35)
        probability = 1.0 / (1.0 + np.exp(-linear))
        weights = np.maximum(probability * (1.0 - probability), 1e-8)
        gradient = matrix.T @ (labels - probability) - penalty * penalized * coefficients
        hessian = (matrix.T * weights) @ matrix + penalty * np.diag(penalized) + 1e-8 * np.eye(matrix.shape[1])
        step = np.linalg.solve(hessian, gradient)
        coefficients += step
        if np.max(np.abs(step)) < 1e-8: break
    return coefficients


def _predict(matrix, coefficients):
    return 1.0 / (1.0 + np.exp(-np.clip(matrix @ coefficients, -35, 35)))


def _fit_models(discovery, penalty):
    labels = [row["y_bad"] for row in discovery]
    result = {}
    for name, include_mpf in (("ordinary_combined", False), ("ordinary_plus_m_pf", True)):
        transform = _fit_transform(discovery, include_mpf)
        coefficients = _logistic_fit(_design(discovery, transform), labels, penalty)
        result[name] = (transform, coefficients)
    return result


def _model_pair(rows, model):
    transform, coefficients = model
    scores = _predict(_design(rows, transform), coefficients)
    labels = [row["y_bad"] for row in rows]
    return _auc(labels, scores), _average_precision(labels, scores)


def _groups(rows, partition):
    partition_rows = [row for row in rows if row["partition"] == partition]
    return {group: partition_rows if group == "pooled" else [row for row in partition_rows if row["planner"] == group]
            for group in GROUPS}


def _predictive(rows, models):
    output = []
    for partition in ("discovery", "holdout"):
        for group, group_rows in _groups(rows, partition).items():
            for metric in INDIVIDUAL:
                auroc, auprc = _metric_pair(group_rows, metric)
                output.extend([
                    {"partition": partition, "group": group, "predictor": metric, "statistic": "auroc", "estimate": auroc},
                    {"partition": partition, "group": group, "predictor": metric, "statistic": "auprc", "estimate": auprc},
                ])
            for model_name, model in models.items():
                auroc, auprc = _model_pair(group_rows, model)
                output.extend([
                    {"partition": partition, "group": group, "predictor": model_name, "statistic": "auroc", "estimate": auroc},
                    {"partition": partition, "group": group, "predictor": model_name, "statistic": "auprc", "estimate": auprc},
                ])
    return output


def _resample_layouts(rows, rng):
    grouped = defaultdict(list)
    for row in rows: grouped[row["layout_cluster"]].append(row)
    keys = sorted(grouped)
    sampled = []
    for _ in keys: sampled.extend(grouped[keys[rng.randrange(len(keys))]])
    return sampled


def _percentile(values, quantile):
    values = sorted(values); position = (len(values) - 1) * quantile
    lower = int(position); upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _bootstrap(protocol, rows, models, predictive):
    settings = protocol["evaluation"]
    holdout_groups = _groups(rows, "holdout")
    result = []
    estimates = {(row["group"], row["predictor"], row["statistic"]): row["estimate"] for row in predictive if row["partition"] == "holdout"}
    for group, group_rows in holdout_groups.items():
        for predictor in INDIVIDUAL + ("ordinary_combined", "ordinary_plus_m_pf"):
            for statistic_index, statistic in enumerate(("auroc", "auprc")):
                rng = random.Random(settings["bootstrap_seed"] + int(hashlib.sha256("{}|{}|{}".format(group, predictor, statistic).encode()).hexdigest()[:8], 16))
                values = []
                for _ in range(settings["bootstrap_resamples"]):
                    sampled = _resample_layouts(group_rows, rng)
                    pair = _metric_pair(sampled, predictor) if predictor in INDIVIDUAL else _model_pair(sampled, models[predictor])
                    if math.isfinite(pair[statistic_index]): values.append(pair[statistic_index])
                if len(values) < int(.9 * settings["bootstrap_resamples"]): raise RuntimeError("too few valid layout bootstrap samples")
                result.append({"partition": "holdout", "group": group, "contrast": predictor,
                               "statistic": statistic, "estimate": estimates[(group, predictor, statistic)],
                               "ci_low": _percentile(values, .025), "ci_high": _percentile(values, .975),
                               "valid_resamples": len(values)})
        for statistic_index, statistic in enumerate(("auroc", "auprc")):
            rng = random.Random(settings["bootstrap_seed"] + int(hashlib.sha256("{}|delta|{}".format(group, statistic).encode()).hexdigest()[:8], 16))
            values = []
            for _ in range(settings["bootstrap_resamples"]):
                sampled = _resample_layouts(group_rows, rng)
                baseline = _model_pair(sampled, models["ordinary_combined"])[statistic_index]
                extended = _model_pair(sampled, models["ordinary_plus_m_pf"])[statistic_index]
                if math.isfinite(baseline) and math.isfinite(extended): values.append(extended - baseline)
            estimate = estimates[(group, "ordinary_plus_m_pf", statistic)] - estimates[(group, "ordinary_combined", statistic)]
            result.append({"partition": "holdout", "group": group, "contrast": "extended_minus_baseline",
                           "statistic": statistic, "estimate": estimate, "ci_low": _percentile(values, .025),
                           "ci_high": _percentile(values, .975), "valid_resamples": len(values)})
    return result


def _matched(protocol, rows):
    settings = protocol["matched_examples"]
    holdout = [row for row in rows if row["partition"] == settings["partition"]]
    candidates = []
    for planner in PLANNERS:
        bad = [row for row in holdout if row["planner"] == planner and row["y_bad"]]
        nominal = [row for row in holdout if row["planner"] == planner and not row["y_bad"]]
        for left in bad:
            for right in nominal:
                ev = abs(left["e_v"] - right["e_v"]); mp = abs(left["m_p"] - right["m_p"])
                mpf = right["m_pf"] - left["m_pf"]
                if ev <= settings["maximum_e_v_difference"] + 1e-12 and mp <= settings["maximum_m_p_difference"] + 1e-12 and mpf >= settings["minimum_m_pf_difference"] - 1e-12:
                    candidates.append((mpf - ev - mp, planner, left, right))
    selected, used_planners = [], set()
    for score, planner, bad, nominal in sorted(candidates, key=lambda item: (-item[0], item[1], item[2]["snapshot_id"], item[3]["snapshot_id"])):
        if planner in used_planners: continue
        selected.append({"pair_id": "pair_{:02d}".format(len(selected) + 1), "planner": planner,
                         "bad_snapshot_id": bad["snapshot_id"], "nominal_snapshot_id": nominal["snapshot_id"],
                         "bad_mechanisms": bad["mechanisms"], "bad_e_v": bad["e_v"], "nominal_e_v": nominal["e_v"],
                         "bad_m_p": bad["m_p"], "nominal_m_p": nominal["m_p"],
                         "bad_m_pf": bad["m_pf"], "nominal_m_pf": nominal["m_pf"], "selection_score": score})
        used_planners.add(planner)
        if len(selected) >= settings["maximum_pairs"]: break
    return selected


def _lookup(predictive, group, predictor, statistic):
    return next(row["estimate"] for row in predictive if row["partition"] == "holdout" and row["group"] == group and row["predictor"] == predictor and row["statistic"] == statistic)


def _decision(protocol, rows, predictive, matched, models):
    baseline = {stat: _lookup(predictive, "pooled", "ordinary_combined", stat) for stat in ("auroc", "auprc")}
    extended = {stat: _lookup(predictive, "pooled", "ordinary_plus_m_pf", stat) for stat in ("auroc", "auprc")}
    delta = {stat: extended[stat] - baseline[stat] for stat in baseline}
    qualifying = [stat for stat, threshold in (("auroc", protocol["decision"]["go_delta_auroc"]), ("auprc", protocol["decision"]["go_delta_auprc"])) if delta[stat] >= threshold - 1e-12]
    planner_delta = {planner: {stat: _lookup(predictive, planner, "ordinary_plus_m_pf", stat) - _lookup(predictive, planner, "ordinary_combined", stat) for stat in ("auroc", "auprc")} for planner in PLANNERS}
    positive = [planner for planner, values in planner_delta.items() if values["auroc"] > 0 or values["auprc"] > 0]
    holdout = [row for row in rows if row["partition"] == "holdout"]
    loo = {}
    for cluster in sorted({row["layout_cluster"] for row in holdout}):
        subset = [row for row in holdout if row["layout_cluster"] != cluster]
        loo[cluster] = {stat: _model_pair(subset, models["ordinary_plus_m_pf"])[index] - _model_pair(subset, models["ordinary_combined"])[index]
                        for index, stat in enumerate(("auroc", "auprc"))}
    layout_robust = bool(qualifying) and any(all(values[stat] > 0 for values in loo.values()) for stat in qualifying)
    criteria = {
        "incremental_threshold": bool(qualifying), "not_single_layout": layout_robust,
        "two_planners_positive": len(positive) >= 2, "teb_positive": "teb" in positive,
        "beyond_m_p_baseline": bool(qualifying), "matched_mechanism": bool(matched),
    }
    return ("EIPT EMPIRICAL GO" if all(criteria.values()) else "EIPT EMPIRICAL NO-GO"), baseline, extended, delta, planner_delta, criteria, loo


def _figures(output, predictive, bootstrap, matched):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"auroc": "#0072B2", "auprc": "#D55E00"}
    predictors = list(INDIVIDUAL) + ["ordinary_combined", "ordinary_plus_m_pf"]
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained", sharey=True)
    for axis, group in zip(axes.flat, GROUPS):
        for offset, statistic in ((-.10, "auroc"), (.10, "auprc")):
            values = [_lookup(predictive, group, predictor, statistic) for predictor in predictors]
            axis.scatter([index + offset for index in range(len(predictors))], values, color=colors[statistic],
                         marker="o" if statistic == "auroc" else "s", label=statistic.upper())
        axis.axhline(.5, color="#777777", linewidth=.8, linestyle="--")
        axis.set_title(group.upper()); axis.set_ylim(0, 1); axis.set_ylabel("Held-out predictive performance")
        axis.set_xticks(range(len(predictors))); axis.set_xticklabels(predictors, rotation=45, ha="right", fontsize=8)
        axis.legend(frameon=False)
    figure.savefig(output / "metric_predictive_comparison.png", dpi=180); plt.close(figure)
    if not matched: return
    figure, axes = plt.subplots(1, 3, figsize=(10, 3.6), layout="constrained")
    for axis, metric, label in zip(axes, ("e_v", "m_p", "m_pf"), ("tracking error", "ordinary margin", "execution margin")):
        for index, pair in enumerate(matched):
            left, right = pair["bad_" + metric], pair["nominal_" + metric]
            axis.plot([left, right], [index, index], color="#777777", linewidth=1)
            axis.scatter(left, index, color="#D55E00", marker="x", s=55, label="future bad" if index == 0 else None)
            axis.scatter(right, index, color="#0072B2", marker="o", facecolors="none", s=55, label="nominal" if index == 0 else None)
        axis.set_xlabel(label); axis.set_yticks(range(len(matched))); axis.set_yticklabels([pair["planner"].upper() for pair in matched])
    axes[0].legend(frameon=False); figure.savefig(output / "matched_vulnerability_examples.png", dpi=180); plt.close(figure)


def _report(protocol, schedule, rows, predictive, bootstrap, matched, instrument, decision_data):
    passed, overall, per_planner = instrument
    classification, baseline, extended, delta, planner_delta, criteria, loo = decision_data
    counts = Counter((row["planner"], row["partition"], row["y_bad"]) for row in rows)
    censored = {planner: sum(row["m_pf_censored"] for row in rows if row["planner"] == planner) for planner in PLANNERS}
    lines = ["# EIPT Empirical Discrimination Gate", "", "> SYNTHETIC — NOT PHYSICALLY IDENTIFIED. Post hoc one-day kill test; bootstrap intervals are descriptive, not significance tests.", "",
             "## Frozen design and provenance", "", "- Snapshots: 144; every planner × partition contains 12 future-bad and 12 nominal snapshots.",
             "- Source data: immutable RQ1 TR/TEB traces and immutable Phase-2 standard-DWA traces; discovery and holdout remain separate.",
             "- Query-schedule protocol SHA-256: `{}`; final analysis protocol SHA-256: `{}`. The latter adds only pre-analysis matching/decision closure after query execution.".format(schedule["protocol_sha256"], hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest()),
             "- Material transition: normalized command L2 change ≥0.35, frozen maneuver-mode/sign/collapse rules, or planner query failure.",
             "- `m_P`: 14 fixed velocity-state directions; `m_PF`: 10 fixed execution-parameter directions, H=10 planner cycles. Both use 0.25 coarse steps and 0.03125 bisection resolution; 2.0 denotes no transition found in the frozen search domain.",
             "- Baseline model: all ordinary metrics + nominal θ + planner identity. Extended model adds only `m_PF`. Both are fixed ridge-logistic models fitted on discovery and evaluated on holdout.", "",
             "## Instrument contract", "", "- Baseline replay mismatch: {:.1%} overall; TR {:.1%}, TEB {:.1%}, DWA {:.1%}. Contract: **{}**.".format(overall, per_planner["tr"], per_planner["teb"], per_planner["dwa"], "PASS" if passed else "FAIL"),
             "- `m_PF` search-censored snapshots: TR {}, TEB {}, DWA {} of 48 each.".format(censored["tr"], censored["teb"], censored["dwa"]), "",
             "## Held-out predictive comparison", "", "| Group | Baseline AUROC / AUPRC | +m_PF AUROC / AUPRC | ΔAUROC / ΔAUPRC |", "|---|---:|---:|---:|"]
    for group in GROUPS:
        base = {stat: _lookup(predictive, group, "ordinary_combined", stat) for stat in ("auroc", "auprc")}
        ext = {stat: _lookup(predictive, group, "ordinary_plus_m_pf", stat) for stat in ("auroc", "auprc")}
        lines.append("| {} | {:.3f} / {:.3f} | {:.3f} / {:.3f} | {:+.3f} / {:+.3f} |".format(group, base["auroc"], base["auprc"], ext["auroc"], ext["auprc"], ext["auroc"] - base["auroc"], ext["auprc"] - base["auprc"]))
    lines += ["", "Individual metric AUROC/AUPRC and 95% layout-bootstrap intervals are retained in `predictive_metrics.csv` and `bootstrap_summary.csv`. Bootstrap intervals condition on the discovery-fitted model and are descriptive only. AUPRC is conditional on the deliberately balanced 1:1 snapshot sample and is not a natural-prevalence estimate.", "",
              "## Hard-rule audit", "", "- Pooled incremental threshold: {} (ΔAUROC {:+.3f}; ΔAUPRC {:+.3f}).".format("PASS" if criteria["incremental_threshold"] else "FAIL", delta["auroc"], delta["auprc"]),
              "- Not explained by one holdout layout: {} (leave-one-layout-out deltas retained in analysis code path; minimum qualifying delta must stay >0).".format("PASS" if criteria["not_single_layout"] else "FAIL"),
              "- Positive information in at least two planners: {}. TEB participates: {}.".format("PASS" if criteria["two_planners_positive"] else "FAIL", "PASS" if criteria["teb_positive"] else "FAIL"),
              "- Increment beyond a baseline already containing `m_P`: {}.".format("PASS" if criteria["beyond_m_p_baseline"] else "FAIL"),
              "- Frozen equal-error/similar-`m_P`/different-`m_PF` examples: {} ({} retained).".format("PASS" if criteria["matched_mechanism"] else "FAIL", len(matched)), ""]
    if matched:
        lines += ["| Pair | Planner | bad / nominal snapshots | e_v bad/nominal | m_P bad/nominal | m_PF bad/nominal |", "|---|---|---|---:|---:|---:|"]
        for pair in matched:
            lines.append("| {pair_id} | {planner} | {bad_snapshot_id} / {nominal_snapshot_id} | {bad_e_v:.3f}/{nominal_e_v:.3f} | {bad_m_p:.3f}/{nominal_m_p:.3f} | {bad_m_pf:.3f}/{nominal_m_pf:.3f} |".format(**pair))
    lines += ["", "## Scientific classification", "", "# {}".format(classification), "",
              "This classification applies only to EIPT/PETM as the primary paper direction under this frozen synthetic kill test. It does not establish physical fidelity or authorize a governor, new planner, or broader navigation matrix.", ""]
    return "\n".join(lines)


def analyse(output=DEFAULT_OUTPUT):
    output = Path(output); protocol, schedule, rows = _load(output)
    snapshot_fields = tuple(rows[0]); _write(output / "snapshot_metrics.csv", rows, snapshot_fields)
    instrument = _instrument(protocol, rows)
    if not instrument[0]:
        for name in ("predictive_metrics.csv", "bootstrap_summary.csv", "matched_examples.csv"):
            _write(output / name, [], ("status",))
        classification = "EIPT EMPIRICAL INCONCLUSIVE"
        (output / "EIPT_EMPIRICAL_GATE.md").write_text("# EIPT Empirical Discrimination Gate\n\nInstrument contract failed: baseline replay mismatch exceeded the frozen limit.\n\n# {}\n".format(classification))
        print(classification); return classification
    discovery = [row for row in rows if row["partition"] == "discovery"]
    models = _fit_models(discovery, float(protocol["evaluation"]["ridge_penalty"]))
    predictive = _predictive(rows, models); _write(output / "predictive_metrics.csv", predictive)
    bootstrap = _bootstrap(protocol, rows, models, predictive); _write(output / "bootstrap_summary.csv", bootstrap)
    matched = _matched(protocol, rows)
    _write(output / "matched_examples.csv", matched, tuple(matched[0]) if matched else ("pair_id", "planner"))
    decision_data = _decision(protocol, rows, predictive, matched, models)
    _figures(output, predictive, bootstrap, matched)
    report = _report(protocol, schedule, rows, predictive, bootstrap, matched, instrument, decision_data)
    (output / "EIPT_EMPIRICAL_GATE.md").write_text(report, encoding="utf-8")
    print(decision_data[0]); return decision_data[0]


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", default=str(DEFAULT_OUTPUT)); args = parser.parse_args()
    analyse(Path(args.output))


if __name__ == "__main__": main()
