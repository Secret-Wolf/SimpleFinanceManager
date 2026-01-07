#!/usr/bin/env python3
"""
Finanzmanager - Startup Script
"""
import uvicorn
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

if __name__ == "__main__":
    # Ensure data directory exists
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(data_dir, exist_ok=True)

    print("=" * 50)
    print("  Finanzmanager")
    print("  http://localhost:8000")
    print("=" * 50)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
