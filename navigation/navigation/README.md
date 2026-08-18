# P3 Navigation & Localization Subsystem

This package implements the **GPS-Denied Autonomous Drone Navigation System** for P3.

## Features
- **INS Dead Reckoning**: 100+ Hz accelerometer & gyroscope state propagation.
- **ORB Visual Odometry**: Monocular 30 FPS feature tracking, essential matrix estimation, and relative pose recovery.
- **15-State Extended Kalman Filter (EKF)**: Fuses INS and VO predictions/updates into a unified state estimate.
- **Visual SLAM & Loop Closure**: Keyframe management, 3D point cloud generation, and place-recognition drift correction.
- **Quantitative Evaluation**: ATE and RPE trajectory error metrics.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Main Navigation Engine
```bash
python main.py
```

### 3. Master Plan & Roadmap
See [P3_NAVIGATION_PLAN.md](../P3_NAVIGATION_PLAN.md) for the complete blueprint, phase breakdown, and milestone schedule.
