# RQ1 Evaluation Stability Audit

> POST HOC, DESCRIPTIVE ONLY — no significance test or scientific GO/NO-GO decision.

## Analysis contract

This read-only audit compares each E1 episode with the same planner/layout under E0. Discovery and holdout remain separate. The source is `/home/artrc/SCALE/data/rq1_synthetic/episodes.csv` (880 valid episodes; lock `355a6b600b50409b680ffb0e06ee53d75e1a915fb3142bddfb3a3a3180f9c8d5`).
Outcome flip, failure-set Jaccard, terminal-mode transitions, and TEB-versus-TR preference stability were fixed before reading scenario-level results. Intervals are 95% layout-level percentile bootstrap intervals (5,000 resamples; seed 20260829) and are descriptive uncertainty only.

Terminal modes use the exhaustive priority `success > collision > planner_failure > timeout`. A failure-set Jaccard of 1 means identical failed-layout sets; the failure-set sizes and union denominator are always shown.

## Outcome and failure-set stability

### Discovery

| Planner | Profile | E0→profile success | Flip | S→F / F→S | Failure sets E0/profile/union | Jaccard | Terminal agreement |
|---|---|---:|---:|---:|---:|---:|---:|
| tr | delay_050 | 0.65→0.65 | 0.00 [0.00, 0.00] | 0/0 | 7/7/7 | 1.00 [1.00, 1.00] | 1.00 |
| tr | delay_100 | 0.65→0.65 | 0.00 [0.00, 0.00] | 0/0 | 7/7/7 | 1.00 [1.00, 1.00] | 1.00 |
| tr | delay_200 | 0.65→0.60 | 0.05 [0.00, 0.15] | 1/0 | 7/8/8 | 0.88 [0.60, 1.00] | 0.90 |
| tr | tau_x_100 | 0.65→0.65 | 0.00 [0.00, 0.00] | 0/0 | 7/7/7 | 1.00 [1.00, 1.00] | 1.00 |
| tr | tau_x_300 | 0.65→0.65 | 0.00 [0.00, 0.00] | 0/0 | 7/7/7 | 1.00 [1.00, 1.00] | 1.00 |
| tr | tau_y_150 | 0.65→0.60 | 0.05 [0.00, 0.15] | 1/0 | 7/8/8 | 0.88 [0.60, 1.00] | 0.95 |
| tr | tau_y_300 | 0.65→0.60 | 0.05 [0.00, 0.15] | 1/0 | 7/8/8 | 0.88 [0.60, 1.00] | 0.95 |
| tr | tau_y_500 | 0.65→0.65 | 0.00 [0.00, 0.00] | 0/0 | 7/7/7 | 1.00 [1.00, 1.00] | 1.00 |
| tr | tau_w_100 | 0.65→0.60 | 0.05 [0.00, 0.15] | 1/0 | 7/8/8 | 0.88 [0.60, 1.00] | 0.95 |
| tr | tau_w_300 | 0.65→0.60 | 0.05 [0.00, 0.15] | 1/0 | 7/8/8 | 0.88 [0.60, 1.00] | 0.95 |
| teb | delay_050 | 0.95→0.95 | 0.00 [0.00, 0.00] | 0/0 | 1/1/1 | 1.00 [1.00, 1.00] | 1.00 |
| teb | delay_100 | 0.95→0.90 | 0.05 [0.00, 0.15] | 1/0 | 1/2/2 | 0.50 [0.00, 1.00] | 0.95 |
| teb | delay_200 | 0.95→0.90 | 0.05 [0.00, 0.15] | 1/0 | 1/2/2 | 0.50 [0.00, 1.00] | 0.95 |
| teb | tau_x_100 | 0.95→0.95 | 0.00 [0.00, 0.00] | 0/0 | 1/1/1 | 1.00 [1.00, 1.00] | 1.00 |
| teb | tau_x_300 | 0.95→0.95 | 0.00 [0.00, 0.00] | 0/0 | 1/1/1 | 1.00 [1.00, 1.00] | 1.00 |
| teb | tau_y_150 | 0.95→0.95 | 0.00 [0.00, 0.00] | 0/0 | 1/1/1 | 1.00 [1.00, 1.00] | 1.00 |
| teb | tau_y_300 | 0.95→0.90 | 0.05 [0.00, 0.15] | 1/0 | 1/2/2 | 0.50 [0.00, 1.00] | 0.95 |
| teb | tau_y_500 | 0.95→0.85 | 0.10 [0.00, 0.25] | 2/0 | 1/3/3 | 0.33 [0.00, 1.00] | 0.90 |
| teb | tau_w_100 | 0.95→0.95 | 0.00 [0.00, 0.00] | 0/0 | 1/1/1 | 1.00 [1.00, 1.00] | 1.00 |
| teb | tau_w_300 | 0.95→0.90 | 0.05 [0.00, 0.15] | 1/0 | 1/2/2 | 0.50 [0.00, 1.00] | 0.95 |

Diagnostic flags: hidden-churn heuristic `0/20`; high-stability heuristic `10/20`. These are screening descriptions, not decision thresholds.

### Holdout

| Planner | Profile | E0→profile success | Flip | S→F / F→S | Failure sets E0/profile/union | Jaccard | Terminal agreement |
|---|---|---:|---:|---:|---:|---:|---:|
| tr | delay_050 | 0.60→0.60 | 0.10 [0.00, 0.25] | 1/1 | 8/8/9 | 0.78 [0.50, 1.00] | 0.90 |
| tr | delay_100 | 0.60→0.65 | 0.05 [0.00, 0.15] | 0/1 | 8/7/8 | 0.88 [0.60, 1.00] | 0.95 |
| tr | delay_200 | 0.60→0.60 | 0.20 [0.05, 0.40] | 2/2 | 8/8/10 | 0.60 [0.29, 0.90] | 0.80 |
| tr | tau_x_100 | 0.60→0.55 | 0.05 [0.00, 0.15] | 1/0 | 8/9/9 | 0.89 [0.64, 1.00] | 0.95 |
| tr | tau_x_300 | 0.60→0.70 | 0.10 [0.00, 0.25] | 0/2 | 8/6/8 | 0.75 [0.40, 1.00] | 0.90 |
| tr | tau_y_150 | 0.60→0.65 | 0.05 [0.00, 0.15] | 0/1 | 8/7/8 | 0.88 [0.60, 1.00] | 0.95 |
| tr | tau_y_300 | 0.60→0.50 | 0.10 [0.00, 0.25] | 2/0 | 8/10/10 | 0.80 [0.50, 1.00] | 0.90 |
| tr | tau_y_500 | 0.60→0.45 | 0.15 [0.00, 0.30] | 3/0 | 8/11/11 | 0.73 [0.43, 1.00] | 0.80 |
| tr | tau_w_100 | 0.60→0.55 | 0.05 [0.00, 0.15] | 1/0 | 8/9/9 | 0.89 [0.62, 1.00] | 0.95 |
| tr | tau_w_300 | 0.60→0.60 | 0.10 [0.00, 0.25] | 1/1 | 8/8/9 | 0.78 [0.50, 1.00] | 0.90 |
| teb | delay_050 | 0.90→0.90 | 0.10 [0.00, 0.25] | 1/1 | 2/2/3 | 0.33 [0.00, 1.00] | 0.90 |
| teb | delay_100 | 0.90→0.95 | 0.05 [0.00, 0.15] | 0/1 | 2/1/2 | 0.50 [0.00, 1.00] | 0.95 |
| teb | delay_200 | 0.90→0.80 | 0.10 [0.00, 0.25] | 2/0 | 2/4/4 | 0.50 [0.00, 1.00] | 0.90 |
| teb | tau_x_100 | 0.90→0.90 | 0.00 [0.00, 0.00] | 0/0 | 2/2/2 | 1.00 [1.00, 1.00] | 1.00 |
| teb | tau_x_300 | 0.90→0.95 | 0.05 [0.00, 0.15] | 0/1 | 2/1/2 | 0.50 [0.00, 1.00] | 0.95 |
| teb | tau_y_150 | 0.90→0.90 | 0.00 [0.00, 0.00] | 0/0 | 2/2/2 | 1.00 [1.00, 1.00] | 1.00 |
| teb | tau_y_300 | 0.90→0.85 | 0.05 [0.00, 0.15] | 1/0 | 2/3/3 | 0.67 [0.00, 1.00] | 0.95 |
| teb | tau_y_500 | 0.90→0.75 | 0.15 [0.00, 0.30] | 3/0 | 2/5/5 | 0.40 [0.00, 1.00] | 0.85 |
| teb | tau_w_100 | 0.90→0.90 | 0.00 [0.00, 0.00] | 0/0 | 2/2/2 | 1.00 [1.00, 1.00] | 1.00 |
| teb | tau_w_300 | 0.90→0.90 | 0.00 [0.00, 0.00] | 0/0 | 2/2/2 | 1.00 [1.00, 1.00] | 1.00 |

Diagnostic flags: hidden-churn heuristic `1/20`; high-stability heuristic `4/20`. These are screening descriptions, not decision thresholds.

## Non-zero terminal-mode transitions

### Discovery

| Planner | Profile | E0 mode → profile mode | Count / 20 | Rate within E0 source mode |
|---|---|---|---:|---:|
| tr | delay_050 | success → success | 13 | 1.00 |
| tr | delay_050 | timeout → timeout | 7 | 1.00 |
| tr | delay_100 | success → success | 13 | 1.00 |
| tr | delay_100 | timeout → timeout | 7 | 1.00 |
| tr | delay_200 | success → success | 12 | 0.92 |
| tr | delay_200 | success → collision | 1 | 0.08 |
| tr | delay_200 | timeout → collision | 1 | 0.14 |
| tr | delay_200 | timeout → timeout | 6 | 0.86 |
| tr | tau_x_100 | success → success | 13 | 1.00 |
| tr | tau_x_100 | timeout → timeout | 7 | 1.00 |
| tr | tau_x_300 | success → success | 13 | 1.00 |
| tr | tau_x_300 | timeout → timeout | 7 | 1.00 |
| tr | tau_y_150 | success → success | 12 | 0.92 |
| tr | tau_y_150 | success → timeout | 1 | 0.08 |
| tr | tau_y_150 | timeout → timeout | 7 | 1.00 |
| tr | tau_y_300 | success → success | 12 | 0.92 |
| tr | tau_y_300 | success → timeout | 1 | 0.08 |
| tr | tau_y_300 | timeout → timeout | 7 | 1.00 |
| tr | tau_y_500 | success → success | 13 | 1.00 |
| tr | tau_y_500 | timeout → timeout | 7 | 1.00 |
| tr | tau_w_100 | success → success | 12 | 0.92 |
| tr | tau_w_100 | success → collision | 1 | 0.08 |
| tr | tau_w_100 | timeout → timeout | 7 | 1.00 |
| tr | tau_w_300 | success → success | 12 | 0.92 |
| tr | tau_w_300 | success → timeout | 1 | 0.08 |
| tr | tau_w_300 | timeout → timeout | 7 | 1.00 |
| teb | delay_050 | success → success | 19 | 1.00 |
| teb | delay_050 | planner_failure → planner_failure | 1 | 1.00 |
| teb | delay_100 | success → success | 18 | 0.95 |
| teb | delay_100 | success → planner_failure | 1 | 0.05 |
| teb | delay_100 | planner_failure → planner_failure | 1 | 1.00 |
| teb | delay_200 | success → success | 18 | 0.95 |
| teb | delay_200 | success → planner_failure | 1 | 0.05 |
| teb | delay_200 | planner_failure → planner_failure | 1 | 1.00 |
| teb | tau_x_100 | success → success | 19 | 1.00 |
| teb | tau_x_100 | planner_failure → planner_failure | 1 | 1.00 |
| teb | tau_x_300 | success → success | 19 | 1.00 |
| teb | tau_x_300 | planner_failure → planner_failure | 1 | 1.00 |
| teb | tau_y_150 | success → success | 19 | 1.00 |
| teb | tau_y_150 | planner_failure → planner_failure | 1 | 1.00 |
| teb | tau_y_300 | success → success | 18 | 0.95 |
| teb | tau_y_300 | success → collision | 1 | 0.05 |
| teb | tau_y_300 | planner_failure → planner_failure | 1 | 1.00 |
| teb | tau_y_500 | success → success | 17 | 0.89 |
| teb | tau_y_500 | success → collision | 1 | 0.05 |
| teb | tau_y_500 | success → planner_failure | 1 | 0.05 |
| teb | tau_y_500 | planner_failure → planner_failure | 1 | 1.00 |
| teb | tau_w_100 | success → success | 19 | 1.00 |
| teb | tau_w_100 | planner_failure → planner_failure | 1 | 1.00 |
| teb | tau_w_300 | success → success | 18 | 0.95 |
| teb | tau_w_300 | success → timeout | 1 | 0.05 |
| teb | tau_w_300 | planner_failure → planner_failure | 1 | 1.00 |

### Holdout

| Planner | Profile | E0 mode → profile mode | Count / 20 | Rate within E0 source mode |
|---|---|---|---:|---:|
| tr | delay_050 | success → success | 11 | 0.92 |
| tr | delay_050 | success → timeout | 1 | 0.08 |
| tr | delay_050 | timeout → success | 1 | 0.12 |
| tr | delay_050 | timeout → timeout | 7 | 0.88 |
| tr | delay_100 | success → success | 12 | 1.00 |
| tr | delay_100 | timeout → success | 1 | 0.12 |
| tr | delay_100 | timeout → timeout | 7 | 0.88 |
| tr | delay_200 | success → success | 10 | 0.83 |
| tr | delay_200 | success → collision | 1 | 0.08 |
| tr | delay_200 | success → planner_failure | 1 | 0.08 |
| tr | delay_200 | timeout → success | 2 | 0.25 |
| tr | delay_200 | timeout → timeout | 6 | 0.75 |
| tr | tau_x_100 | success → success | 11 | 0.92 |
| tr | tau_x_100 | success → timeout | 1 | 0.08 |
| tr | tau_x_100 | timeout → timeout | 8 | 1.00 |
| tr | tau_x_300 | success → success | 12 | 1.00 |
| tr | tau_x_300 | timeout → success | 2 | 0.25 |
| tr | tau_x_300 | timeout → timeout | 6 | 0.75 |
| tr | tau_y_150 | success → success | 12 | 1.00 |
| tr | tau_y_150 | timeout → success | 1 | 0.12 |
| tr | tau_y_150 | timeout → timeout | 7 | 0.88 |
| tr | tau_y_300 | success → success | 10 | 0.83 |
| tr | tau_y_300 | success → collision | 2 | 0.17 |
| tr | tau_y_300 | timeout → timeout | 8 | 1.00 |
| tr | tau_y_500 | success → success | 9 | 0.75 |
| tr | tau_y_500 | success → collision | 1 | 0.08 |
| tr | tau_y_500 | success → planner_failure | 1 | 0.08 |
| tr | tau_y_500 | success → timeout | 1 | 0.08 |
| tr | tau_y_500 | timeout → collision | 1 | 0.12 |
| tr | tau_y_500 | timeout → timeout | 7 | 0.88 |
| tr | tau_w_100 | success → success | 11 | 0.92 |
| tr | tau_w_100 | success → timeout | 1 | 0.08 |
| tr | tau_w_100 | timeout → timeout | 8 | 1.00 |
| tr | tau_w_300 | success → success | 11 | 0.92 |
| tr | tau_w_300 | success → timeout | 1 | 0.08 |
| tr | tau_w_300 | timeout → success | 1 | 0.12 |
| tr | tau_w_300 | timeout → timeout | 7 | 0.88 |
| teb | delay_050 | success → success | 17 | 0.94 |
| teb | delay_050 | success → planner_failure | 1 | 0.06 |
| teb | delay_050 | planner_failure → success | 1 | 0.50 |
| teb | delay_050 | planner_failure → planner_failure | 1 | 0.50 |
| teb | delay_100 | success → success | 18 | 1.00 |
| teb | delay_100 | planner_failure → success | 1 | 0.50 |
| teb | delay_100 | planner_failure → planner_failure | 1 | 0.50 |
| teb | delay_200 | success → success | 16 | 0.89 |
| teb | delay_200 | success → planner_failure | 2 | 0.11 |
| teb | delay_200 | planner_failure → planner_failure | 2 | 1.00 |
| teb | tau_x_100 | success → success | 18 | 1.00 |
| teb | tau_x_100 | planner_failure → planner_failure | 2 | 1.00 |
| teb | tau_x_300 | success → success | 18 | 1.00 |
| teb | tau_x_300 | planner_failure → success | 1 | 0.50 |
| teb | tau_x_300 | planner_failure → planner_failure | 1 | 0.50 |
| teb | tau_y_150 | success → success | 18 | 1.00 |
| teb | tau_y_150 | planner_failure → planner_failure | 2 | 1.00 |
| teb | tau_y_300 | success → success | 17 | 0.94 |
| teb | tau_y_300 | success → planner_failure | 1 | 0.06 |
| teb | tau_y_300 | planner_failure → planner_failure | 2 | 1.00 |
| teb | tau_y_500 | success → success | 15 | 0.83 |
| teb | tau_y_500 | success → collision | 1 | 0.06 |
| teb | tau_y_500 | success → planner_failure | 2 | 0.11 |
| teb | tau_y_500 | planner_failure → planner_failure | 2 | 1.00 |
| teb | tau_w_100 | success → success | 18 | 1.00 |
| teb | tau_w_100 | planner_failure → planner_failure | 2 | 1.00 |
| teb | tau_w_300 | success → success | 18 | 1.00 |
| teb | tau_w_300 | planner_failure → planner_failure | 2 | 1.00 |

## Planner-preference stability

Preference is reported separately for binary success and normalized path progress; no composite score is used. `TEB` means TEB−TR > 1e-12, `TR` means < −1e-12, otherwise tie. Progress preference is therefore an exact-score descriptive comparison and can be sensitive to very small differences.

### Discovery

| Metric | Profile | Any state change | Strict TEB↔TR reversal | Aggregate E0→profile preference | Aggregate TEB−TR E0→profile |
|---|---|---:|---:|---|---:|
| success | delay_050 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | delay_050 | 0.05 [0.00, 0.15] | 0.05 [0.00, 0.15] | teb→teb | 0.264→0.266 |
| success | delay_100 | 0.05 [0.00, 0.15] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.250 |
| normalized_path_progress | delay_100 | 0.05 [0.00, 0.15] | 0.05 [0.00, 0.15] | teb→teb | 0.264→0.248 |
| success | delay_200 | 0.10 [0.00, 0.25] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | delay_200 | 0.30 [0.10, 0.50] | 0.25 [0.10, 0.45] | teb→teb | 0.264→0.246 |
| success | tau_x_100 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | tau_x_100 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | teb→teb | 0.264→0.264 |
| success | tau_x_300 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | tau_x_300 | 0.15 [0.00, 0.30] | 0.15 [0.00, 0.30] | teb→teb | 0.264→0.260 |
| success | tau_y_150 | 0.05 [0.00, 0.15] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.350 |
| normalized_path_progress | tau_y_150 | 0.05 [0.00, 0.15] | 0.05 [0.00, 0.15] | teb→teb | 0.264→0.304 |
| success | tau_y_300 | 0.10 [0.00, 0.25] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | tau_y_300 | 0.05 [0.00, 0.15] | 0.05 [0.00, 0.15] | teb→teb | 0.264→0.247 |
| success | tau_y_500 | 0.10 [0.00, 0.25] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.200 |
| normalized_path_progress | tau_y_500 | 0.15 [0.00, 0.35] | 0.15 [0.00, 0.30] | teb→teb | 0.264→0.239 |
| success | tau_w_100 | 0.05 [0.00, 0.15] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.350 |
| normalized_path_progress | tau_w_100 | 0.05 [0.00, 0.15] | 0.05 [0.00, 0.15] | teb→teb | 0.264→0.301 |
| success | tau_w_300 | 0.10 [0.00, 0.25] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | tau_w_300 | 0.05 [0.00, 0.15] | 0.05 [0.00, 0.15] | teb→teb | 0.264→0.302 |

### Holdout

| Metric | Profile | Any state change | Strict TEB↔TR reversal | Aggregate E0→profile preference | Aggregate TEB−TR E0→profile |
|---|---|---:|---:|---|---:|
| success | delay_050 | 0.20 [0.05, 0.40] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | delay_050 | 0.10 [0.00, 0.25] | 0.10 [0.00, 0.25] | teb→teb | 0.251→0.263 |
| success | delay_100 | 0.10 [0.00, 0.25] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | delay_100 | 0.10 [0.00, 0.25] | 0.10 [0.00, 0.25] | teb→teb | 0.251→0.221 |
| success | delay_200 | 0.25 [0.10, 0.45] | 0.05 [0.00, 0.15] | teb→teb | 0.300→0.200 |
| normalized_path_progress | delay_200 | 0.45 [0.25, 0.65] | 0.40 [0.20, 0.60] | teb→teb | 0.251→0.184 |
| success | tau_x_100 | 0.05 [0.00, 0.15] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.350 |
| normalized_path_progress | tau_x_100 | 0.05 [0.00, 0.15] | 0.05 [0.00, 0.15] | teb→teb | 0.251→0.293 |
| success | tau_x_300 | 0.15 [0.00, 0.30] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.250 |
| normalized_path_progress | tau_x_300 | 0.35 [0.15, 0.55] | 0.15 [0.00, 0.30] | teb→teb | 0.251→0.217 |
| success | tau_y_150 | 0.05 [0.00, 0.15] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.250 |
| normalized_path_progress | tau_y_150 | 0.10 [0.00, 0.25] | 0.10 [0.00, 0.25] | teb→teb | 0.251→0.230 |
| success | tau_y_300 | 0.15 [0.00, 0.35] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.350 |
| normalized_path_progress | tau_y_300 | 0.10 [0.00, 0.25] | 0.10 [0.00, 0.25] | teb→teb | 0.251→0.316 |
| success | tau_y_500 | 0.30 [0.10, 0.50] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | tau_y_500 | 0.15 [0.00, 0.30] | 0.15 [0.00, 0.30] | teb→teb | 0.251→0.286 |
| success | tau_w_100 | 0.05 [0.00, 0.15] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.350 |
| normalized_path_progress | tau_w_100 | 0.10 [0.00, 0.25] | 0.10 [0.00, 0.25] | teb→teb | 0.251→0.294 |
| success | tau_w_300 | 0.10 [0.00, 0.25] | 0.00 [0.00, 0.00] | teb→teb | 0.300→0.300 |
| normalized_path_progress | tau_w_300 | 0.10 [0.00, 0.25] | 0.10 [0.00, 0.25] | teb→teb | 0.251→0.229 |

## Evidence boundary

This audit measures agreement of outcomes under the tested synthetic execution assumptions. It does not establish physical fidelity, generalize beyond these 40 layouts and two local planners, or justify the stronger claim that planners have substantially different execution-response fingerprints. The accountable researcher must make the Scientific Gate decision after reviewing discovery/holdout replication and the CSV-level transitions.

## Primary-model Gate reading

- Success/failure identity was mostly stable: mean profile-versus-E0 flip was 2.75% in discovery and 7.25% in holdout; the maximum was 10% and 20%, respectively.
- The hidden-churn screening pattern appeared in only 1 of 40 planner-partition-profile cells (TR, holdout, `delay_200`) and did not replicate in discovery.
- Aggregate TEB-versus-TR preference did not flip in any of the 40 partition-profile-metric comparisons. Success-based strict planner reversals were absent in discovery and reached at most 5% in holdout.
- A narrower repeated sensitivity appeared for normalized path progress under `delay_200`: strict scenario-level TEB/TR reversals were 25% in discovery and 40% in holdout, while the aggregate preference still favored TEB.

Therefore, the current 880 episodes do **not** satisfy the proposed strong-evidence branch for freezing broad *evaluation instability* as SCALE's first main line. They support only a narrower, post hoc observation that scenario-level progress ranking can be delay-sensitive even when aggregate planner preference is stable. This is Gate evidence for human review, not a manuscript claim or authorization for new experiments.
