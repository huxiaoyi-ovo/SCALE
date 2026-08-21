# DWA root-cause diagnostic

## 1. Selected layouts

Exactly three frozen old Phase 2 DWA/E0 near-start timeouts were selected by the
existing read-only rule: `logical_timeout`, recorded path length at most 0.30 m,
then first three layouts in lexicographic order.

| Layout | Old E0 normalized progress |
| --- | ---: |
| `discovery_01` | 0.0097 |
| `discovery_02` | 0.0131 |
| `discovery_03` | 0.0091 |

Variant A changed only `planner.use_dwa` from its normal `true` value to
`false`; the stored path was unchanged. Variant B kept normal DWA and deleted
only the shared 7.1 cm artificial first grid waypoint at `(0.65, 1.95)` from
each stored path. All other geometry, planner parameters, execution settings,
termination rules, and collision truth remained frozen.

## 2. Six-run results

Command RMS uses planner calls with logical time `0.00 <= t < 2.00 s` (40
calls). A command is labelled near-zero when every component RMS is below
0.05; the raw `vy` sign-change count is also reported rather than inferred.

| Variant | Layout | Outcome | Normalized progress | Path length (m) | First-2-s RMS `(vx, vy, wz)` | `vy` sign changes | Command character |
| --- | --- | --- | ---: | ---: | --- | ---: | --- |
| A: no Dynamic Window | `discovery_01` | success | 0.9872 | 5.4931 | (0.3976, 0.1074, 0.3040) | 0 | active, not oscillatory |
| A: no Dynamic Window | `discovery_02` | success | 0.9854 | 5.0597 | (0.4110, 0.0628, 0.1205) | 0 | active, not oscillatory |
| A: no Dynamic Window | `discovery_03` | logical timeout | 0.4645 | 2.8353 | (0.4110, 0.0627, 0.0811) | 0 | active, not oscillatory |
| B: start kink removed | `discovery_01` | logical timeout | 0.3571 | 2.1620 | (0.0273, 0.0395, 0.0616) | 0 | low-amplitude, not oscillatory |
| B: start kink removed | `discovery_02` | logical timeout | 0.0005 | 0.0530 | (0.0034, 0.0312, 0.0211) | 1 | near-zero, not oscillatory |
| B: start kink removed | `discovery_03` | logical timeout | 0.0003 | 0.0530 | (0.0034, 0.0312, 0.0211) | 1 | near-zero, not oscillatory |

All six episodes passed timing, feedback, command-hold, and collision-truth
contracts. There were no collisions or planner failures. The clean formal run
contained one accepted attempt per episode under instrument commit `84efeaf`.

## 3. Brief command-behavior summary

Disabling Dynamic Window produced immediately active commands on all three
layouts, two successes, and substantial progress in the remaining timeout.
Removing only the start kink produced no successes: two layouts remained at
the start and one made partial progress. Thus the path representation can
affect an individual trajectory, but it did not consistently remove the floor.
No variant showed repeated early `vy` sign oscillation in this diagnostic.

## 4. Final classification

**DWA DYNAMIC-WINDOW ISSUE**

The strong, consistent rescue is associated with disabling the Dynamic Window,
not with removing the artificial start-path kink. This supports a
dynamic-window/acceleration-feedback interaction as the main cause within the
tested cases; it is a bounded diagnostic classification, not a general claim
about DWA.
