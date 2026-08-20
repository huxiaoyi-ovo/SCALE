# SCALE planner bridge

Build from the repository root:

```bash
source /opt/ros/noetic/setup.bash
mkdir -p build/scale_ros
catkin_make -C build/scale_ros --source navigation
```

Run either official planner through the same bridge after sourcing `/opt/ros/noetic/setup.bash` and `build/scale_ros/devel/setup.bash`:

```bash
roscore
roslaunch scale_planner_bridge dwa_e0_bridge.launch
# Or: roslaunch scale_planner_bridge teb_e0_bridge.launch
```

In a third terminal, use the project virtual environment so the smoke test shares SCALE's canonical Shapely collision evaluator:

```bash
.venv/bin/python navigation/scale_planner_bridge/scripts/dwa_e0_smoke.py
# Or: .venv/bin/python navigation/scale_planner_bridge/scripts/teb_e0_smoke.py
```

Run the independent-process determinism gate with:

```bash
.venv/bin/python navigation/scale_planner_bridge/scripts/determinism_regression.py --planner dwa --runs 10 --tolerance 1e-9
.venv/bin/python navigation/scale_planner_bridge/scripts/determinism_regression.py --planner teb --runs 10 --tolerance 1e-9
```

`planner_period` controls planner calls and planner-visible ROS time; `configs/pilot.yaml` keeps the separate E0 integration step. Before each planner call, the bridge serially accepts the latest executed pose and velocity as odometry. SCALE alone applies integration, external termination, and continuous physical-footprint collision checks.

The smoke tests are E0-only infrastructure evidence. They do not establish real-time, sensor, recovery, E1, or hardware behavior.
