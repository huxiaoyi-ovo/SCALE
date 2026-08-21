# SCALE local process parallelism assessment

Calibration date: 2026-08-21. All measurements used the non-study `pilot_arena` engineering fixture; no Phase 2/2B scientific episode or result was changed.

## 1. Machine configuration

- CPU: Intel Core Ultra 9 285H, 16 physical cores / 16 logical CPUs, no SMT, one NUMA node. CPU0-5 advertise 5.4 GHz, CPU6-13 4.5 GHz, and CPU14-15 2.5 GHz maximum.
- Frequency/power: active `intel_pstate`, `powersave` dynamic governor; about 5.1 GHz was observed on CPU0. AC power was online. Package temperature was about 57-58 C during inspection. Thermal counters are cumulative, so this short probe cannot exclude intermittent throttling.
- Memory: 30 GiB total, about 19 GiB initially available, 2 GiB swap with 0 used. No memory pressure was observed.
- Storage: repository, results, and `/tmp` are on `/dev/nvme0n1p6`, ext4, on a YMTC NVMe SSD; about 200 GiB free. No meaningful I/O wait or storage limit was observed.
- OS: Ubuntu 20.04.6 LTS, Linux 6.14.0-37-generic.
- Initial load average: about 2.58 / 2.42 / 2.58. The execution namespace did not expose the complete host process list, so background load is reflected in system CPU/load measurements rather than attributed to named host processes.

## 2. Current serial bottleneck

Persistent roscore startup was only 0.38 s. The dominant cost is per-episode ROS parameter/process/service orchestration, not planner computation or disk I/O.

| Case | Episode wall (s) | Pre/post-smoke overhead | Smoke phase (s) | Planner compute total (s) | Calls / steps |
|---|---:|---:|---:|---:|---:|
| DWA E0 | 3.23 | 50.7% | 1.59 | 0.48 | 82 / 406 |
| DWA E1 (`tau_y_150`) | 3.42 | 47.9% | 1.78 | 0.52 | 163 / 812 |
| TEB E0 | 2.96 | 58.4% | 1.23 | 0.19 | 56 / 279 |
| TEB E1 (`tau_y_150`) | 2.86 | 55.9% | 1.26 | 0.23 | 57 / 281 |

Approximate typical RSS was 94 MiB for the roscore tree, 22 MiB for `planner_bridge_node`, 68 MiB for the Python smoke process, and 60 MiB for the probe/worker Python process. A complete episode consumed roughly one CPU core in aggregate, split among ROS CLI/startup, bridge, smoke, and Python work. DWA bridge CPU was about 17-18% of one core over episode wall time; TEB bridge CPU was about 8-10%; roscore was about 5%; the smoke Python process was about 18-25%.

## 3. Benchmark methodology

- Fixed workload: 32 episodes, eight repeats each of DWA E0, DWA representative E1, TEB E0, and TEB representative E1.
- Every worker had a private `ROS_MASTER_URI`, roscore, planner bridge lifecycle, temporary directory, `ROS_HOME`, `ROS_LOG_DIR`, and worker log tree.
- One parent queue distributed jobs. Workers returned complete summaries/traces; they never appended to the shared terminal CSV.
- Candidate counts were 1, 2, 4, 6, 8, 12, and 16. No oversubscription beyond the 16 logical CPUs was tested.
- CPU is mean whole-system utilization during each run; load is peak one-minute load average. Memory RSS is an approximate upper sum of classified workload processes.
- An initial 8-worker exploratory run exposed a bind/release race: an ephemeral roscore master port was claimed by another roslaunch XML-RPC server. Final runs used centrally selected master ports below Linux's ephemeral range; all final candidates then had zero startup errors.

## 4. Worker-count results

| Workers | Wall (s) | Episodes/min | Speedup | Efficiency | CPU mean | Peak load-1 | Approx RSS | Min available RAM | Planner compute inflation | Errors | Limit observed |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 101.74 | 18.87 | 1.00x | 100.0% | 18.0% | 4.06 | ~0.29 GiB | 18.39 GiB | reference | 0 | startup/orchestration |
| 2 | 51.98 | 36.93 | 1.96x | 97.9% | 21.5% | 3.53 | ~0.51 GiB | 18.56 GiB | +4.2% | 0 | none |
| 4 | 27.22 | 70.55 | 3.74x | 93.5% | 32.1% | 3.73 | ~0.95 GiB | 18.28 GiB | +5.4% | 0 | none |
| 6 | 19.98 | 96.09 | 5.09x | 84.9% | 39.8% | 4.89 | ~1.39 GiB | 18.00 GiB | +5.4% | 0 | mild CPU contention |
| 8 | 14.44 | 132.94 | 7.05x | 88.1% | 50.8% | 6.05 | ~1.81 GiB | 17.75 GiB | -3.4% (noise) | 0 | mild CPU contention |
| 12 | 11.37 | 168.81 | 8.95x | 74.5% | 67.4% | 7.44 | ~2.63 GiB | 17.15 GiB | -3.6% (noise) | 0 | CPU contention, comfortable margin |
| 16 | 10.35 | 185.58 | 9.83x | 61.5% | 77.2% | 8.82 | ~3.51 GiB | 16.64 GiB | +5.9% | 0 | stronger CPU/process contention |

Moving from 12 to 16 workers gained only 9.9% throughput while adding four ROS stacks, reducing efficiency by 13 percentage points, and increasing mean episode wall time from about 3.27 s to 3.92 s. Memory and I/O never approached saturation.

## 5. Serial-versus-parallel determinism

The first four fixed cases from 1-worker and 12-worker execution were compared recursively using the existing `1e-9` tolerance.

- Same terminal reason: 4/4.
- Same planner calls and execution steps: 4/4.
- Same command trace and executed-state trace: 4/4.
- Maximum absolute numeric difference: `0.0`.
- Canonical full-trace SHA-256 digest also matched for all 4/4 cases.

A separate production-path integration check completed 4/4 pilot episodes with four private masters, four parent-written terminal records, four parent-written gzip traces, zero worker-written CSV files, and clean worker shutdown.

## 6. Recommended worker count

Use 12 workers. It is the lowest tested count within 10% of the measured 16-worker maximum, preserves exact traces, has stable startup after the port fix, retains more than 17 GiB available RAM, and avoids the weaker efficiency and longer per-episode time at 16.

Reference command:

```bash
python experiments/phase2_runner.py run --workers 12
```

`--workers 1` remains the reference serial path.

## 7. Expected 880-episode matrix speedup

Measured probe speedup at 12 workers was 8.95x. Applied to the previously observed 86-minute serial matrix, the direct estimate is about 9.6 minutes. Allowing for parent collision validation, gzip/fsync, background load, and layout-dependent episode length, a practical planning estimate is about 10-12 minutes (roughly 7-9x), to be confirmed on the next separately authorized non-study or preregistered batch.

## 8. Is the parallel runner worth keeping?

Yes. The gain is large, the implementation remains a local process queue rather than a distributed framework, and exact deterministic equivalence passed. The runner should default operationally to the explicitly requested `--workers` value; this machine's recommended value is 12.

## 9. Exact code changes

- `experiments/phase2_runner.py`: added `--workers`, a spawn-based central job queue, worker-private ROS masters/state/logs, collision-resistant master-port selection, worker-returned artifacts, parent-only validation/CSV/trace commit, and parallel retry/stop handling. The existing one-worker serial behavior remains available.
- `tests/test_phase2_screening.py`: added checks for private ROS state and for parallel infrastructure retry, parent-only commit, unique terminal rows/traces, and resume behavior.
- `PARALLELISM_ASSESSMENT.md`: records this machine-local calibration and recommendation.
- No DWA/TEB settings, timing, dynamics, collision truth, layout generation, Phase 2 data, or Phase 2B study inputs were changed.

## 10. Remaining risks

- The throughput workload used one non-study pilot layout; different layout difficulty changes absolute time, though the selected knee is dominated by process overhead.
- Complete host background-process attribution was unavailable in this execution namespace.
- Thermal throttle counters were not sampled as before/after deltas; sustained laptop power or thermal changes could shift the optimum.
- A future source change requires a new matching preflight lock before execution; existing locked Phase 2 results remain immutable.

PARALLELISM DECISION:
- USE 12 WORKERS
