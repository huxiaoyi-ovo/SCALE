# Phase 2 Execution-Profile Screening Preregistration

## Status and boundary

This protocol is frozen before any Phase 2 study episode is executed. The
screening is synthetic engineering evidence for `Planner x execution profile`.
It is not physically identified, is not a formal confirmatory experiment, and
cannot produce a scientific GO/NO-GO decision.

The study stops at the scientific-review Gate. MPPI, E2, physical-robot work,
and post-result parameter tuning are outside scope.

## Fixed design

The complete matrix contains 880 independently restarted episodes:

- official DWA and official TEB;
- 20 discovery and 20 holdout layouts;
- E0 and 10 E1 one-factor profiles per planner and layout.

All planners share the bridge, map construction, stored global path, footprint,
limits, planner period, execution substep, external success criteria, physical
collision truth, and logical timeout. E1 changes exactly one of command delay,
`tau_x`, `tau_y`, or `tau_w`; the remaining execution parameters are zero. The
exact levels and every other parameter are machine-readable in
`configs/phase2/protocol.yaml`.

## Layout and path selection

The layout generator uses seed `20260820`. It accepts the first 40 candidates
that satisfy only the frozen geometric rules: obstacle bounds and separation,
start/goal exclusion, a collision-free eight-connected A* path after conservative
footprint inflation, and the preregistered path-length interval. Planner output
is never used to generate, reject, reorder, or label a layout. The first 20
accepted layouts are discovery and the next 20 are holdout.

Each accepted layout stores its global path explicitly. Both planners and all
execution profiles receive that same stored path. The full 880-episode order is
then shuffled once with seed `20260821` and stored before execution.

## Outcomes and analysis

Every algorithm outcome is retained: success, planner failure, physical
footprint collision, and logical timeout. Continuous outcomes include capped
time to termination, path length, minimum physical clearance, and final position
error. Discovery and holdout are reported separately; combined values are
descriptive only.

The planned uncertainty summary is a paired, layout-level percentile bootstrap
with 5,000 resamples, 95% intervals, and seed `20260822`. It reports each
planner's profile-minus-E0 change and the TEB-minus-DWA difference in those
changes. No p-values, threshold-based selection, multiplicity-driven follow-up,
or scientific decision is permitted in this phase.

## Failure, retry, and stopping rules

Planner failure, collision, and logical timeout are valid completed episodes and
are never retried. Only enumerated ROS/process/transport/artifact infrastructure
failures may be retried, at most twice after the first attempt. Exhausted
infrastructure retries stop the batch.

A logical-time, executed-odometry, command-hold, benchmark-collision, or restart-
determinism contract failure stops the study immediately and is not retried.
Resume skips only a valid completed episode whose protocol lock matches exactly.
All attempts, including infrastructure failures, remain in an append-only log.

## Reproducibility chain

The required chain is:

```text
protocol + fixed layouts + fixed paths + fixed schedule
  -> preflight lock
  -> attempt ledger + raw compressed traces
  -> episode CSV
  -> deterministic analysis CSV
  -> figures + REPORT
```

The preflight records hashes, software/Git provenance, dependency checks, and
the timing/feedback/collision/determinism checks. Analysis refuses incomplete,
duplicate, contract-invalid, or lock-mismatched data.
