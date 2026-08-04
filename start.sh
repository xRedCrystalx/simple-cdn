#!/usr/bin/env bash
set -euo pipefail

if [ ! -d "logs" ] || [ ! -f "main.db" ]; then
    echo "Missing logs/ or main.db. Please run 'python setup.py' first." >&2
    exit 1
fi

.venv/bin/python main.py
