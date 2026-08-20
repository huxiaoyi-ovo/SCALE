# SCALE planner bridge

Build from the repository root:

```bash
source /opt/ros/noetic/setup.bash
mkdir -p build/scale_ros
catkin_make -C build/scale_ros --source navigation
```

Run any cell of the shared planner x execution matrix after sourcing `/opt/ros/noetic/setup.bash` and `build/scale_ros/devel/setup.bash`:

```bash
roscore
roslaunch scale_planner_bridge planner_execution.launch planner:=dwa execution:=e0
# planner:=dwa|teb, execution:=e0|e1
```

In a third terminal, use the project virtual environment so the smoke test shares SCALE's canonical Shapely collision evaluator:

```bash
.venv/bin/python navigation/scale_planner_bridge/scripts/planner_execution_smoke.py
```

Run the independent-process determinism gate with:

```bash
.venv/bin/python navigation/scale_planner_bridge/scripts/determinism_regression.py \
  --planner teb --execution e1 --runs 10 --tolerance 1e-9
```

`planner_period` is 0.05 s and `execution.dt` is 0.01 s, so each planner command is held for five execution substeps. Before every planner call, the bridge serially accepts the latest executed pose and velocity as odometry. SCALE alone applies integration, external termination, and continuous physical-footprint collision checks.

All four Phase 1C matrix cells use the same 10 s infrastructure-smoke timeout from `matrix_common.yaml`; it is not a planner-performance claim.

The E1 profile is explicitly `SYNTHETIC - NOT PHYSICALLY IDENTIFIED`. These smoke tests validate execution machinery only; they do not establish a planner-performance effect, physical grounding, real-time behavior, sensing, recovery, E2, or hardware behavior. The original `dwa_e0_bridge.launch`, `teb_e0_bridge.launch`, and thin smoke entry points remain available for Phase 1A/1B reproduction.
