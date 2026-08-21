# Phase 2B Baseline Calibration Report

## Status

**CALIBRATION FAIL — STOP**

The frozen 30-episode calibration completed, but the amended DWA configuration
remained at the success floor. No further DWA tuning or Phase 2B experiment was
started.

## Instrument amendment

- Commit: `0de6823` (`fix: compare feedback yaw on wrapped angle domain`)
- Change: executed-odom feedback yaw is compared on the wrapped angular domain.
- Unchanged: tolerance (`1e-9`), all non-angular feedback comparisons, odom
  production, execution, bridge semantics, timing, collision truth, planners,
  layouts, and schedule.
- Validation: 5 targeted tests passed; 48 full pytest tests passed; catkin build
  passed; DWA/TEB x E0/E1 two-restart trace regressions each had maximum absolute
  difference `0.0` (required `<= 1e-9`).

The two earlier attempts are preserved under
`data/phase2b_baseline_viable_screening/pre_amendment_excluded/` and are marked
`PRE-AMENDMENT — EXCLUDED FROM CALIBRATION DECISION`. They were not reused.

## Frozen calibration results

| Configuration | Success | Rate | Terminal reasons | Median normalized path progress | Median executed path length (m) |
|---|---:|---:|---|---:|---:|
| Original DWA E0 | 0/10 | 0% | 10 logical timeout | 0.012966 | 0.296864 |
| DWA E0, `forward_point_distance=0.0` | 0/10 | 0% | 10 logical timeout | 0.040829 | 0.579224 |
| Current TEB E0 | 9/10 | 90% | 9 external tolerance; 1 no valid velocity command | 0.988649 | 5.855723 |

All 30 terminal rows were produced on the first attempt and classified as
algorithm outcomes; there were no infrastructure retries or contract failures.

## Calibration decision

`forward_point_distance=0.0` increased median progress relative to the original
DWA configuration, but success remained `0/10`. It therefore did **not** escape
the baseline floor or reach the preregistered approximate 20–80% usable range.

Per the decision boundary, calibration stops here. These calibration-only results
support no Planner x execution-profile scientific claim.
