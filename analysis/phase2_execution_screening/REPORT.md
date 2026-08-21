# Phase 2 execution-profile screening

SYNTHETIC — NOT PHYSICALLY IDENTIFIED. Descriptive screening only; no p-values, scientific interpretation, or GO/NO-GO decision.

## Protocol and provenance

- Lock: `f1c8fd861651f70500a8a3341a4fd79820a6f66c02609af9d8137fd2b70d947b`
- Protocol/layout/schedule hashes: `ce36c4a7f1d3e891d1b6398ad456e56d62456f5c5f734f57fde83ef92dcfe0fa` / `41d5fb73872602222ee6502bc678fbad6fe1f3d35ae5d608b598f3372ca629ba` / `ec893ddf18626fa216c2f2267a7d209173c43a6193ccdb976dfa29de8ddba217`
- Git head / Phase 1C base: `b778f11fe3ca101bdc0560a0117d80dfe832c8d7` / `b778f11`
- Episodes: 880 valid locked traces (440 discovery, 440 holdout).
- Bootstrap: layout-unit percentile 95% CI, 5000 fixed resamples, seed 20260822.
- Preflight contracts: timing, executed odom, command hold, collision truth, and restart determinism passed before the lock was created.

## Completion and outcomes

- Terminal reasons: `{'external_tolerance': 418, 'footprint_collision': 5, 'logical_timeout': 356, 'plugin returned no valid velocity command': 101}`
- Attempt ledger statuses: `{'algorithm': 880}`
- Exclusions: none; algorithm failure, collision, and logical timeout remain valid terminal episodes.
- Infrastructure retries are reported in `attempts.csv`; no algorithm outcome is selectively rerun.

## Tables and figures

- `descriptive.csv`: n, mean, sample SD, median, minimum, and maximum.
- `bootstrap_ci.csv`: partitioned success-rate 95% bootstrap intervals.
- `paired_effects.csv`: within-planner profile-minus-E0 paired changes.
- `interaction_contrasts.csv`: TEB-minus-DWA degradation contrasts.
- Five source-driven PNG/PDF figures, `figure_source_episodes.csv`, and `figure_manifest.json`.

Discovery and holdout remain separate for all bootstrap and interaction estimates; combined rows are descriptive only. The figures are provisional general-purpose scientific graphics, not a journal-compliance claim. This report stops at the scientific review gate and makes no scientific decision.
