# SCALE agent contract

## Highest-order principle: paper first

The highest project-level decision rule is to take the simplest sufficient path
to a credible, publishable SCALE paper. Judge every task from first principles:
does it directly strengthen the evidence needed for `P x lambda` or
E0/E1/E2 -> E3, or materially improve the validity, reproducibility, or clarity
of that evidence? If not, defer or remove it.

- Prefer minimum sufficient engineering over platform completeness.
- Use the smallest experiment or implementation that can answer the current
  scientific question defensibly.
- Stop polishing a stage once it has enough evidence and validation for its role
  in the paper.
- Do not spend time on code aesthetics, rare edge cases, abstractions, tooling,
  or hardening that cannot materially change the paper's conclusions.
- Treat scientific integrity, validity, provenance, and necessary reproducibility
  as part of "sufficient," never as optional detail.
- When alternatives are scientifically sound, choose the one that produces the
  strongest defensible paper evidence with the least time and complexity.

## Scope

The research core is only `P x lambda` and E0/E1/E2 -> E3 prediction. Phase 0 is deterministic, planar, and synthetic. Do not independently turn any of these into a primary direction: a new planner, MARP, PCTM as independent novelty, dynamic footprint, SLAM, sensor reliability, FOV planning, perception, multi-robot, or a dual-platform benchmark.

## Scientific integrity

- Never fabricate results.
- Never label synthetic data as physical data.
- Prevent train/test or evaluation leakage when E2 is introduced.
- Never cherry-pick runs manually without recording the selection rule and exclusions.
- Never hard-code a benchmark outcome.

## Engineering principles

- Build the minimum working loop first.
- Prefer configuration over hard-coded experiment parameters.
- Prefer simple code over premature abstraction.
- Test the mathematics and geometry.
- Put reproducibility first: configuration -> run -> raw data -> metric -> figure/table.

If a feature cannot clearly help answer RQ1 or RQ2, do not implement it by default.

Long-term model routing: a high-capability primary model exclusively owns requirements, architecture, scientific and risk decisions, contracts, and final acceptance. Select the lowest-cost sufficient single submodel only for bounded mechanical work; the primary model performs small, coupled tasks directly. Submodels may not expand scope or nest delegation. The primary model reviews the resulting diff and validation evidence.
