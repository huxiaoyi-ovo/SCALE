# SCALE planner bridge

Build from the repository root:

```bash
source /opt/ros/noetic/setup.bash
mkdir -p build/scale_ros
catkin_make -C build/scale_ros --source navigation
```

Run in two terminals after sourcing `/opt/ros/noetic/setup.bash` and `build/scale_ros/devel/setup.bash`:

```bash
roscore
roslaunch scale_planner_bridge dwa_e0_bridge.launch
rosrun scale_planner_bridge dwa_e0_smoke.py
```

The smoke test is E0-only: it proves a fixed map/plan can drive the official local-planner plugin through the synchronous bridge. It does not establish real-time, sensor, recovery, or hardware behavior.
