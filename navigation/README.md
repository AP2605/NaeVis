# Navis — GPS-Denied Autonomous Navigation & Localization (P3)

The **Navigation & Localization (P3)** engine for the Navis Drone Navigation System. Provides real-time 6-DOF state estimation, Visual-Inertial Odometry, 15-State Extended Kalman Filter sensor fusion, 3D Visual SLAM mapping, and zero-drift loop closure in GPS-denied environments.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Test Suite (50 Unit Tests)
```bash
python run_tests.py
```

### 3. Run Navigation Engine (with 3D/2D Plotting & ATE/RPE Benchmarking)
```bash
python main.py --mock figure_eight --duration 5.0 --eval --plot
```

### 4. Export Synthetic Blender Flight Datasets for Teammates
```bash
python export_dataset.py --trajectory figure_eight --duration 5.0 --output ./sample_flight_data
```

---

## 📁 Repository Structure

```
.
├── navigation/                    # Core Navigation & Localization Package
│   ├── configs/                  # Camera intrinsics and EKF noise configuration YAMLs
│   ├── ins/                      # 100+ Hz IMU dead reckoning and gravity removal
│   ├── visual_odometry/          # ORB feature extraction, RANSAC VO, scale estimator
│   ├── fusion/                   # 15-State Error-State EKF (ES-EKF) sensor fusion
│   ├── slam/                     # KeyFrames, 3D MapPoints, and Loop Closure (PGO)
│   ├── evaluation/               # ATE/RPE benchmarking and 2D/3D trajectory plotters
│   ├── utils/                    # Math utilities, Blender dataset loader, mock generator
│   ├── engine.py                 # Top-level unified pipeline orchestrator (matches info.md)
│   └── tests/                    # Comprehensive unit test suite (50 tests)
├── main.py                       # Master CLI executable for running and evaluating flights
├── run_tests.py                  # Automated test runner
├── export_dataset.py             # CLI tool to generate Blender-compatible flight datasets
├── requirements.txt              # Package dependencies
├── setup.py                      # Package installation script
└── .gitignore                    # Git ignore file for Python cache and heavy datasets
```

---

## 📡 Data Contracts (matches `info.md`)

- **Input (`SensorPacket`)**: Consumes synchronized camera frame (image path or in-memory array) + 100 Hz IMU acceleration and gyroscope data.
- **Output (`EstimatedPose`)**: Emits estimated 3D position $(x, y, z)$, attitude $(\text{roll}, \text{pitch}, \text{yaw})$, velocity, tracking health state, and confidence score for P4's React Dashboard.
