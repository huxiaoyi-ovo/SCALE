# Robot adapters

SCALE does not copy or replace an existing robot locomotion controller. A future adapter will preserve this boundary:

```text
SCALE [vx, vy, wz]
        |
        v
existing robot interface
```

The adapter may read odometry, IMU, ground-truth pose, joint state, and optional torque. Phase 0 connects to no robot or live sensor.
