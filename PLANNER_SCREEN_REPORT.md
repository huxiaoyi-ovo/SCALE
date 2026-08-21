# TrajectoryPlannerROS replacement-planner screen

## 1. Candidate

- Plugin: `base_local_planner/TrajectoryPlannerROS`
- Interface: installed ROS Noetic plugin declared as
  `nav_core::BaseLocalPlanner`
- Integration: loaded through the existing SCALE planner bridge; no planner
  implementation or bridge-core logic was added
- Frozen screen commit: `df977bc`
- Screen lock: `d9c286df8496c0b7ea754d6ad449c35318c49fbe0768dcc1a39db58c5bf53b89`

The plugin loaded successfully, produced commands, and moved the robot in the
existing bridge. The completed calibration episodes therefore also provide
stronger interface evidence than a separate one-case smoke rerun.

## 2. Configuration summary

The candidate used E0 execution and the same map, global paths, footprint,
0.05 s planner period, external success criterion, collision truth, and ten
calibration-only layouts as the existing instrument. It was configured as
holonomic with `dwa: false`, lateral samples from -0.35 to 0.35 m/s, forward
speed up to 0.45 m/s, angular speed from -0.8 to 0.8 rad/s, and acceleration
limits `(0.8, 0.8, 1.5)`. Reverse escape speed was -0.15 m/s. No
performance-oriented parameter search was performed.

## 3. Ten-layout results

| Layout | Terminal outcome | Normalized path progress | Path length (m) |
| --- | --- | ---: | ---: |
| `calibration_01` | collision | 0.3553 | 2.1257 |
| `calibration_02` | planner-command failure | 0.2290 | 1.9726 |
| `calibration_03` | timeout | 0.5387 | 2.7736 |
| `calibration_04` | planner-command failure | 0.0575 | 1.0208 |
| `calibration_05` | timeout | 0.1335 | 1.1096 |
| `calibration_06` | collision | 0.1154 | 0.9332 |
| `calibration_07` | planner-command failure | 0.1129 | 1.4471 |
| `calibration_08` | collision | 0.2276 | 1.2214 |
| `calibration_09` | planner-command failure | 0.3646 | 2.3684 |
| `calibration_10` | planner-command failure | 0.4194 | 2.5839 |

All ten episodes passed the timing, feedback, command-hold, and
collision-truth contracts. Every episode had exactly one accepted algorithm
attempt; no algorithm outcome was rerun.

## 4. Aggregate outcomes

- Success: **0/10**
- Timeout: **2/10**
- Planner-command failure: **5/10**
- Collision: **3/10**
- Median normalized path progress: **0.2283**
- Median path length: **1.7098 m**

The failures are not a systematic near-start instrument floor: even the
shortest episode travelled 0.93 m, and the candidate produced commands under
all four instrument contracts. The observed failures comprise five explicit
no-valid-command terminations plus later timeout or collision outcomes. Some
runs had low net path progress, but only after non-trivial executed motion.

## 5. Baseline viability judgment

TrajectoryPlannerROS is loadable and instrument-compatible, but 0/10 success
does not provide a usable second-planner baseline for the planned synthetic
Planner x Execution study. There is no single obvious configuration or
interface error supported by the traces, so further tuning is outside this
screen.

The only other installed `nav_core::BaseLocalPlanner` plugins are the already
used DWA and TEB plugins. No additional candidate was installed or tested.

## 6. Final decision

**PLANNER CANDIDATE FAIL**
