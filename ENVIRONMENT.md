# Known environment snapshot

| Item | Observed value |
|---|---|
| OS / kernel / architecture | Ubuntu 20.04.6 / 6.14.0-37-generic / x86_64 |
| CPU / RAM | Intel Core Ultra 9 285H, 16 CPUs / 30 GiB |
| Disk (`/home`) | 288 G total, 209 G free |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU; driver 580.126.09; 8151 MiB |
| CUDA | Driver reports CUDA 13.0 compatibility; CUDA toolkit/`nvcc` is not installed or not on `PATH` |
| Python / pip | Python 3.8.10 / `pip3` missing |
| Git | 2.25.1 |
| GCC / G++ / CMake | 9.4.0 / 9.4.0 / 3.16.3 |
| ROS | `ROS_DISTRO=noetic`; `catkin_make=/opt/ros/noetic/bin/catkin_make` |
| Shell | `/bin/bash` |

A project-local Conda environment was created at `.venv` with Python 3.8.20 and the seven packages declared in `requirements.txt`. System Python, ROS, the existing Conda environments, the NVIDIA driver, and the CUDA installation were not modified.

System Python dependency probe: `numpy 1.17.4`, `PyYAML 5.3.1`, `matplotlib 3.1.2`, and `pytest 4.6.9` are present; `scipy`, `pandas`, and `shapely` are absent. There is no system `pip` or `ensurepip`; validation therefore uses the project-isolated `.venv`.

Within the Codex sandbox, `nvidia-smi` fails because GPU device nodes are isolated. Host verification found `/dev/nvidia0` and related nodes, so this is not evidence of a driver fault.
