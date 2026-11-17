#!/usr/bin/env python3
"""
Entry point launcher for Smart Co-Working Space Management Using Real-Time Monitoring.
"""

import sys
import os

# Ensure the root directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.server import run_server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"\n[SmartCoWork] Booting system on http://{host}:{port}/ ...")
    run_server(host=host, port=port)
