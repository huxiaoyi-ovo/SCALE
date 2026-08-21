# EIPT Empirical Discrimination Gate

> SYNTHETIC — NOT PHYSICALLY IDENTIFIED. Post hoc one-day kill test; bootstrap intervals are descriptive, not significance tests.

## Frozen design and provenance

- Snapshots: 144; every planner × partition contains 12 future-bad and 12 nominal snapshots.
- Source data: immutable RQ1 TR/TEB traces and immutable Phase-2 standard-DWA traces; discovery and holdout remain separate.
- Query-schedule protocol SHA-256: `a285652941209e046b9bdfe101a42f727545bb631869b85e2e39264b4761432e`; final analysis protocol SHA-256: `dbdf290995f7bd25c1e4bd5711dbcb0aec5751af9c2637dc12f8699d21214732`. The latter adds only pre-analysis matching/decision closure after query execution.
- Material transition: normalized command L2 change ≥0.35, frozen maneuver-mode/sign/collapse rules, or planner query failure.
- `m_P`: 14 fixed velocity-state directions; `m_PF`: 10 fixed execution-parameter directions, H=10 planner cycles. Both use 0.25 coarse steps and 0.03125 bisection resolution; 2.0 denotes no transition found in the frozen search domain.
- Baseline model: all ordinary metrics + nominal θ + planner identity. Extended model adds only `m_PF`. Both are fixed ridge-logistic models fitted on discovery and evaluated on holdout.

## Instrument contract

- Baseline replay mismatch: 1.4% overall; TR 0.0%, TEB 4.2%, DWA 0.0%. Contract: **PASS**.
- `m_PF` search-censored snapshots: TR 5, TEB 3, DWA 18 of 48 each.

## Held-out predictive comparison

| Group | Baseline AUROC / AUPRC | +m_PF AUROC / AUPRC | ΔAUROC / ΔAUPRC |
|---|---:|---:|---:|
| tr | 0.424 / 0.536 | 0.417 / 0.556 | -0.007 / +0.020 |
| teb | 0.417 / 0.633 | 0.472 / 0.648 | +0.056 / +0.016 |
| dwa | 0.736 / 0.664 | 0.833 / 0.759 | +0.097 / +0.095 |
| pooled | 0.549 / 0.575 | 0.600 / 0.628 | +0.050 / +0.053 |

Individual metric AUROC/AUPRC and 95% layout-bootstrap intervals are retained in `predictive_metrics.csv` and `bootstrap_summary.csv`. Bootstrap intervals condition on the discovery-fitted model and are descriptive only. AUPRC is conditional on the deliberately balanced 1:1 snapshot sample and is not a natural-prevalence estimate.

## Hard-rule audit

- Pooled incremental threshold: FAIL (ΔAUROC +0.050; ΔAUPRC +0.053).
- Not explained by one holdout layout: FAIL (leave-one-layout-out deltas retained in analysis code path; minimum qualifying delta must stay >0).
- Positive information in at least two planners: PASS. TEB participates: PASS.
- Increment beyond a baseline already containing `m_P`: FAIL.
- Frozen equal-error/similar-`m_P`/different-`m_PF` examples: PASS (3 retained).

| Pair | Planner | bad / nominal snapshots | e_v bad/nominal | m_P bad/nominal | m_PF bad/nominal |
|---|---|---|---:|---:|---:|
| pair_01 | dwa | eipt_074 / eipt_088 | 0.123/0.140 | 0.156/0.153 | 0.500/2.000 |
| pair_02 | teb | eipt_101 / eipt_114 | 0.077/0.102 | 0.250/0.250 | 0.047/0.672 |
| pair_03 | tr | eipt_124 / eipt_136 | 0.116/0.105 | 0.219/0.219 | 0.188/0.766 |

## Scientific classification

# EIPT EMPIRICAL NO-GO

This classification applies only to EIPT/PETM as the primary paper direction under this frozen synthetic kill test. It does not establish physical fidelity or authorize a governor, new planner, or broader navigation matrix.
