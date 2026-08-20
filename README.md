# SCALE

## What

SCALE (Stack-Conditioned Assessment of Local-planner Execution) studies how locomotion execution changes local-planner evaluation and how much execution fidelity is needed to predict physical results. Phase 0 is a minimal deterministic harness for scripted holonomic commands, collision/clearance, and six outcome metrics.

## Research Questions

- RQ1: planner x execution profile (`P x lambda`) sensitivity.
- RQ2: cross-fidelity prediction from E0/E1/E2 to physical E3.

Phase 0 does not answer either question; it establishes the smallest reproducible loop they both need.

## Current Phase

Phase 0 is active: repository plus minimal simulation framework. Run it from the repository root:

```bash
python3 experiments/runner.py --config configs/pilot.yaml
```

## Architecture

```text
Planner (future)
      |
      v
[vx, vy, wz]
      |
      v
Execution: E0 / E1 / E2 / E3
      |
      v
Trajectory -> Metrics
```

`configs/pilot.yaml` currently supplies the future planner boundary with four scripted command segments. Each invocation creates one E0 and one E1 `data/run_xxxx/` artifact.

## Roadmap

- Phase 0: repository plus minimal simulation framework.
- Phase 1: DWA / TEB -> E0 / E1.
- Phase 2: execution-profile sweep pilot.
- Phase 3: Go / No-Go based on the `P x lambda` interaction.
- Phase 4: physical command-response data -> E1/E2 identification.
- Phase 5: third planner plus main randomized simulation.
- Phase 6: 24-36 physical E3 validation runs.
- Phase 7: interaction statistics plus cross-fidelity analysis.
- Phase 8: paper.

Profiles are synthetic smoke tests, **NOT experimentally grounded**. Install the seven declared Python dependencies in an isolated project environment before running tests.
