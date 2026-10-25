@echo off
cd /d "%~dp0"
py -3.12 -m venv .build-venv
if errorlevel 1 exit /b 1
.build-venv\Scripts\python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
.build-venv\Scripts\python packaging\build_release.py
pause
