#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m motionstudio.gui
fi
printf 'Please run INSTALL_MAC.command first.\n'
exit 1
