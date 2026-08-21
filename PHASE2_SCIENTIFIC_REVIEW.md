# Phase 2 Scientific Review Gate

## Status

**Internal review draft — scientific decision intentionally deferred.**

This document reviews the locked Phase 2 execution-profile screening without
changing the protocol, excluding outcomes, rerunning episodes, or introducing a
post-result parameter choice. The accountable human reviewer must approve any
subsequent `GO`, `REVISE-INSTRUMENT`, or `NO-GO` decision.

All evidence is synthetic and not physically identified. This review cannot
support claims about a physical robot, planner superiority in general, or
cross-fidelity prediction.

## Review question

Does the locked screening provide an interpretable first signal that planner
response depends on the execution profile, while keeping planner identity as the
only planner-side change?

The review separates two questions:

1. Did the experimental instrument and data pipeline operate according to the
   preregistered contract?
2. Does the observed endpoint distribution have enough dynamic range to support
   a scientific interpretation of `Planner x execution profile`?

Passing the first question does not imply passing the second.

## Evidence register

| ID | Evidence | Role | Verification state |
| --- | --- | --- | --- |
| E01 | [`PHASE2_PREREGISTRATION.md`](PHASE2_PREREGISTRATION.md) and [`protocol.yaml`](configs/phase2/protocol.yaml) | Frozen design, outcomes, retries, and inference boundary | Machine-checked; human approval pending |
| E02 | [`lock.json`](analysis/phase2_execution_screening/lock.json) and [`preflight.json`](analysis/phase2_execution_screening/preflight.json) | Source/input hashes and contract evidence | Machine-checked; human approval pending |
| E03 | [`attempts.csv`](analysis/phase2_execution_screening/attempts.csv) and [`episodes.csv`](analysis/phase2_execution_screening/episodes.csv) | Complete attempt and terminal-outcome ledgers | Machine-checked; human approval pending |
| E04 | [`descriptive.csv`](analysis/phase2_execution_screening/descriptive.csv), [`bootstrap_ci.csv`](analysis/phase2_execution_screening/bootstrap_ci.csv), and [`paired_effects.csv`](analysis/phase2_execution_screening/paired_effects.csv) | Descriptive and within-planner summaries | Machine-generated from E03; human approval pending |
| E05 | [`interaction_contrasts.csv`](analysis/phase2_execution_screening/interaction_contrasts.csv) | TEB-minus-DWA differences in profile-minus-E0 changes | Machine-generated from E03; human approval pending |
| E06 | [`REPORT.md`](analysis/phase2_execution_screening/REPORT.md), figures, and [`figure_manifest.json`](analysis/phase2_execution_screening/figure_manifest.json) | Compact result presentation | Machine-generated from E03-E05; human approval pending |
| E07 | [`PHASE2_ARTIFACT_MANIFEST.sha256`](PHASE2_ARTIFACT_MANIFEST.sha256) | Hash index for all 1,784 local result artifacts, including 880 compressed traces | Hash verification passed; raw traces remain local |

## Instrument and data-integrity assessment

### Strengths

- The locked matrix is complete: 880 unique terminal episodes, split evenly
  between discovery and holdout, DWA and TEB, and all 11 profiles. [E02, E03]
- All 880 attempt rows are classified as algorithm outcomes. There were no
  infrastructure retries, selective reruns, exclusions, duplicate terminal rows,
  or unreadable compressed traces. [E03, E07]
- Timing, executed-odometry feedback, command hold, collision truth, and restart
  determinism passed before the study lock was created. The recorded restart
  trace difference is zero for DWA/TEB under E0/E1. [E02]
- Layouts, stored global paths, footprint, limits, planner period, execution
  substep, external termination, and collision truth were shared. The execution
  profiles are one-factor manipulations. [E01]
- Discovery and holdout remain separate for uncertainty estimates and interaction
  contrasts. Combined rows are descriptive only. [E01, E04, E05]

### Engineering assessment

The experiment instrument and provenance chain are internally complete for this
screening. No contract failure requires invalidating or rerunning the locked run.
This is an engineering-integrity conclusion, not a scientific `GO` decision.

## Baseline viability

### E0 success rate

| Partition | DWA | TEB |
| --- | ---: | ---: |
| Discovery | 0.05, 95% bootstrap interval [0.00, 0.15], n=20 | 0.90 [0.75, 1.00], n=20 |
| Holdout | 0.00 [0.00, 0.00], n=20 | 0.90 [0.75, 1.00], n=20 |

Source: E04. Intervals are paired-layout percentile bootstrap summaries and are
not significance tests.

### E0 terminal outcomes

| Partition / planner | Success | Timeout | Planner failure | Collision |
| --- | ---: | ---: | ---: | ---: |
| Discovery / DWA | 1 | 18 | 0 | 1 |
| Holdout / DWA | 0 | 20 | 0 | 0 |
| Discovery / TEB | 18 | 0 | 2 | 0 |
| Holdout / TEB | 18 | 0 | 2 | 0 |

Source: E03; all denominators are 20 layouts.

The baseline difference is not a near-goal tolerance artifact. Median DWA E0
path length was 0.297 m in discovery and 0.189 m in holdout, with median final
position errors of 4.751 m and 4.776 m. The corresponding TEB medians were
5.802/5.283 m path length and 0.060/0.076 m final error. [E04]

### Critical validity concern: endpoint floor and ceiling

DWA E0 is at an empirical success floor while TEB E0 is near a ceiling. Binary
success therefore has little symmetric room to measure additional degradation:
DWA can mainly remain failed or improve, while TEB can mainly remain successful
or worsen. A difference in profile-minus-E0 success may consequently combine:

- genuine planner-conditioned execution sensitivity;
- baseline planner/layout/global-path compatibility;
- rescue or regularization by execution lag;
- saturation of the binary success endpoint.

The locked data do not distinguish among these explanations or identify their
relative contributions. Treating the large DWA-versus-TEB baseline gap as
evidence that one planner is generally better would exceed the design.

## Profile-conditioned observations

The table below reports the preregistered success interaction contrast:
`(TEB profile - TEB E0) - (DWA profile - DWA E0)`.

| Profile | Discovery estimate [95% interval] | Holdout estimate [95% interval] |
| --- | ---: | ---: |
| delay 0.05 s | 0.05 [0.00, 0.15] | 0.00 [0.00, 0.00] |
| delay 0.10 s | 0.05 [-0.10, 0.20] | -0.10 [-0.25, 0.00] |
| delay 0.20 s | -0.05 [-0.20, 0.10] | -0.10 [-0.25, 0.00] |
| tau_x 0.10 s | 0.00 [-0.15, 0.15] | 0.00 [0.00, 0.00] |
| tau_x 0.30 s | -0.10 [-0.30, 0.00] | 0.00 [0.00, 0.00] |
| tau_y 0.15 s | -0.25 [-0.45, -0.10] | -0.30 [-0.50, -0.10] |
| tau_y 0.30 s | -0.10 [-0.35, 0.10] | -0.10 [-0.25, 0.00] |
| tau_y 0.50 s | -0.15 [-0.30, 0.00] | -0.15 [-0.30, 0.00] |
| tau_w 0.10 s | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| tau_w 0.30 s | -0.10 [-0.25, 0.00] | -0.05 [-0.15, 0.00] |

Source: E05. These are descriptive screening intervals, not multiplicity-adjusted
confirmatory inferences.

The most partition-consistent nonzero pattern is associated with `tau_y`, but it
is not a monotonic degradation curve. Under `tau_y=0.15 s`, DWA success increased
from 0.05 to 0.30 in discovery and from 0.00 to 0.30 in holdout, while TEB stayed
at 0.90 in both partitions. At larger `tau_y`, DWA success returned toward its
floor while TEB decreased only at the largest levels. [E04, E05]

This pattern is scientifically interesting as a candidate response difference,
but it is equally compatible with execution lag temporarily regularizing an
already unstable DWA baseline. It must not be called a degradation slope or a
planner ranking reversal without resolving the baseline mechanism.

## Other interpretation limits

- Each partition contains 20 layouts. Bootstrap intervals quantify layout
  resampling uncertainty within these fixed generators; they do not establish
  transportability to other map distributions. [E01, E04]
- The profiles are synthetic and one-factor. No result identifies a physically
  plausible operating range or predicts E3 behavior. [E01]
- Failure modes are categorical and materially planner-dependent. Collapsing
  timeout, planner failure, and collision into one undifferentiated penalty would
  hide distinct mechanisms. [E03, E06]
- Continuous outcomes after terminal failure are descriptive of the terminal
  process and can be strongly conditioned on failure type. They should not be
  interpreted as ordinary trajectory-quality measurements without stratification.
- The review was performed after observing the locked outcomes. Any diagnostic
  not named in the preregistration is exploratory and cannot be relabeled as
  prespecified. [E01]

## Gate checklist

| Gate | Current evidence | Status before decision |
| --- | --- | --- |
| Instrument contracts | All five contracts passed; source/input lock matches | Satisfied |
| Completion and retry policy | 880/880; no exclusions or infrastructure retries | Satisfied |
| Reproducibility assets | Protocol, layouts, schedule, compact results, figures, lock, and raw-artifact hashes archived | Satisfied |
| Baseline dynamic range | DWA E0 0-5% success; TEB E0 90% | Major concern |
| Discovery-to-holdout consistency | `tau_y` pattern repeats; several other contrasts are zero, weak, or partition-dependent | Partial evidence |
| Ordered execution response | `tau_y` success response is non-monotonic; other factors provide limited gradient information | Unresolved |
| Failure-mechanism attribution | DWA E0 mostly times out after very short travel; cause is not identified by this screen | Unresolved |
| Physical grounding and external validity | Profiles are synthetic; no E3 evidence | Outside Phase 2 |

## Inputs required for the scientific decision

The next decision meeting should use the locked evidence only and answer:

1. Is DWA's near-start E0 behavior a valid planner outcome under a fair common
   benchmark, or does it reveal an instrument/planner-interface incompatibility?
2. Can failure-mode-stratified and continuous endpoints identify execution
   sensitivity without relying on the saturated success endpoint?
3. Is the repeated `tau_y` pattern a plausible response mechanism, or primarily a
   baseline rescue effect?
4. Is the available dynamic range sufficient to justify a new physically grounded
   stage, or is a separately preregistered Phase 2B instrument revision required?

If an instrument revision is selected later, the present protocol, data, and
review remain immutable. Any revised layout difficulty, path construction,
timeout, planner parameter, or endpoint must be justified and preregistered as a
new study before new episodes are run.

## Decision boundary

No `GO`, `REVISE-INSTRUMENT`, or `NO-GO` decision is made in this document. No
MPPI, E2, physical-robot work, or additional screening run is authorized by this
review. The project is stopped at the scientific-review Gate.
