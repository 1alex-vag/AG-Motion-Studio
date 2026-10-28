@echo off
setlocal
set "APP_SOURCE=%~dp0AG_Astro_Motion_Studio_v1.9_Experimental"
set "APP_TARGET=%LOCALAPPDATA%\AG Astro Motion Studio\Application"
if not exist "%APP_SOURCE%\AG_Astro_Motion_Studio_v1.9_Experimental.exe" (
 echo Extract the entire Windows release ZIP first. The application folder is missing.
 pause
 exit /b 1
)
xcopy "%APP_SOURCE%\*" "%APP_TARGET%\" /E /I /Y
if errorlevel 1 (
 echo Installation failed. Existing user data was preserved.
 pause
 exit /b 1
)
echo Installed to: %APP_TARGET%
echo No Python installation or administrator rights are required.
echo To start, open AG_Astro_Motion_Studio_v1.9_Experimental.exe in that folder.
pause
