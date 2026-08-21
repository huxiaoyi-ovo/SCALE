# DWA E0 minimal trace diagnosis

## Boundary and selection

This is a post hoc, read-only instrument diagnosis of the frozen Phase 2 run.
No episode was rerun and no Phase 2 data, protocol, or result was changed.

`near-start timeout` was defined before calculation as DWA/E0,
`logical_timeout`, and recorded path length at most 0.30 m. The first three
eligible layouts in lexicographic order were selected: `discovery_01`,
`discovery_02`, and `discovery_03`. Their matching `tau_y_150` episodes were
included. `discovery_16` was included because it is the only DWA/E0 success.

## Definitions

- Planner-command RMS is reported per component `(vx, vy, wz)` and as the RMS
  Euclidean norm over planner calls.
- Sign changes ignore exact zeros and count flips between consecutive nonzero
  samples independently for `(vx, vy, wz)`.
- Zero-command fraction is the fraction of planner calls for which all three
  components are zero within `1e-12`.
- Net displacement is the Euclidean distance from the fixed layout start to the
  final executed position.
- Final normalized global-path progress is the final-position projection onto
  the stored path divided by total path arc length, clipped to `[0, 1]`.

## Results

| Layout / execution | Outcome | RMS `(vx, vy, wz)` | RMS norm | Sign changes `(vx, vy,wz)` | Zero fraction | Net displacement (m) | Final path progress |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: |
| discovery_01 / E0 | timeout | (0.00134, 0.01373, 0.00846) | 0.01618 | (3, 1, 3) | 0.000 | 0.0780 | 0.0097 |
| discovery_01 / tau_y_150 | success | (0.34652, 0.18354, 0.28979) | 0.48759 | (1, 6, 16) | 0.000 | 4.7800 | 0.9882 |
| discovery_02 / E0 | timeout | (0.01378, 0.01577, 0.03697) | 0.04249 | (5, 5, 5) | 0.000 | 0.1119 | 0.0131 |
| discovery_02 / tau_y_150 | timeout | (0.13756, 0.05124, 0.14939) | 0.20944 | (9, 12, 14) | 0.000 | 1.5543 | 0.3105 |
| discovery_03 / E0 | timeout | (0.00134, 0.01373, 0.00846) | 0.01618 | (3, 1, 3) | 0.000 | 0.0780 | 0.0091 |
| discovery_03 / tau_y_150 | timeout | (0.18541, 0.07853, 0.14273) | 0.24681 | (8, 11, 26) | 0.000 | 2.7496 | 0.4594 |
| discovery_16 / E0 | success | (0.34304, 0.21117, 0.34200) | 0.52842 | (1, 0, 28) | 0.000 | 4.7732 | 0.9889 |

The selected DWA logs contain no case-insensitive match for `oscillation`,
`invalid trajectory`, `no-valid-command`, or `no valid velocity`. They contain
only normal startup INFO messages and the terminal summary. Because debug-level
trajectory-rejection messages were not recorded, absence of a match does not
establish absence of rejected trajectories.

## Minimal interpretation

The near-start timeouts are not caused by exact zero commands or reported
planner failure. They are associated with persistent, very small nonzero command
RMS and approximately 1% final path progress. `tau_y_150` changes the closed-loop
command regime substantially and rescues one selected layout, but does not
reliably rescue all three. This supports an instrument calibration check; it is
not evidence for a scientific execution-profile interaction.

The official ROS Noetic DWA source states that setting
`forward_point_distance` to zero discards the alignment critic, while the
parameter otherwise shifts the additional forward scoring point. See
[`dwa_planner.cpp`](https://github.com/ros-planning/navigation/blob/noetic-devel/dwa_local_planner/src/dwa_planner.cpp)
and [`DWAPlanner.cfg`](https://github.com/ros-planning/navigation/blob/noetic-devel/dwa_local_planner/cfg/DWAPlanner.cfg).
Testing exactly `forward_point_distance=0.0` is therefore the only authorized
calibration change. No further parameter search is justified by this diagnosis.
