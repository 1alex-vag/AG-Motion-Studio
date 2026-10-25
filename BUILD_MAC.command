#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
python3.12 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements-build.txt
.build-venv/bin/python packaging/build_release.py
