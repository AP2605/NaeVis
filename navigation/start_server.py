"""
Master Live Server Launcher.
============================
Starts the Navis P3 Real-Time Telemetry & Simulation Bridge Server.

Usage:
  python start_server.py
  python start_server.py --port 8765
"""

import sys
import os
import argparse

# Add current folder to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from navigation.server.stream_server import main

if __name__ == "__main__":
    main()
