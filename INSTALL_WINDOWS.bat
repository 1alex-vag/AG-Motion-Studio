@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 (
 echo Python launcher unavailable; trying python instead...
 python -m pip install -r requirements.txt
)

echo.
echo Checking accelerated renderer...
py -c "import numba; print('Numba acceleration OK - version', numba.__version__)" 2>nul
if errorlevel 1 (
  python -c "import numba; print('Numba acceleration OK - version', numba.__version__)" 2>nul
  if errorlevel 1 (
    echo WARNING: Numba was not installed. Rendering will be VERY slow.
    echo Try: py -m pip install numba
  )
)

pause
