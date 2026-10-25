@echo off
cd /d "%~dp0"
py -m motionstudio.gui
if errorlevel 1 (
 echo.
 echo Missing dependencies? Run INSTALL_WINDOWS.bat first.
 pause
)
