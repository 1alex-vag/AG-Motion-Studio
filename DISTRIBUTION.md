# V1.5 native builds

Use Python 3.12 on the intended build operating system. End users of the finished
native packages do not install Python. PyInstaller creates a one-folder build
with an embedded interpreter, Qt, OpenCV, Numba/LLVM and FFmpeg.

Build Windows: run BUILD_WINDOWS.bat. Build macOS: run BUILD_MAC.command.
Or run: python packaging/build_release.py --output release
Build dependencies and the test runner are pinned in requirements-build.txt and
requirements-lock.txt. macOS builds are per architecture (Apple Silicon/Intel).

The GitHub workflow builds Windows x64, macOS arm64 and macOS x86_64. It first runs
all source tests, freezes the app, and runs the actual executable with system
Python/FFmpeg removed from PATH. Its offline self-test checks Qt startup, depth
jobs, painting/undo, Numba compilation, volumetric loop identity, CPU H.264
encode/decode, TIFF and FITS. A package is archived only after that test passes.
Artifacts include PACKAGED_SELF_TEST.json, BUILD_INFO.json and dependency notices.
This smoke test does not replace interactive testing on a completely clean user
machine, GPU-driver validation, Apple signing or notarization.

## Windows end user

Extract the complete Windows ZIP. Keep the EXE and its _internal folder together.
Run AG_Astro_Motion_Studio_v1.5/AG_Astro_Motion_Studio_v1.5.exe directly, or run
INSTALL_WINDOWS.bat to copy it to %LOCALAPPDATA%/AG Astro Motion Studio/Application.
No administrator rights are needed. Uninstall by removing only that Application
folder. Project/image files and the separate cache are preserved.

## macOS end user

Extract the macOS ZIP for your architecture. Run INSTALL_TO_APPLICATIONS.command
to install in ~/Applications. APP_INSTALL_SCOPE=system installs in /Applications
only when it is writable. An existing AG Astro app is retained under a timestamped
previous-app name before replacement. Siril and other application bundles are
never modified. User data remains in ~/Library/Application Support/AG Astro Motion Studio.

These builds are unsigned/ad-hoc signed unless a developer identity was supplied.
If macOS blocks the app, inspect the warning and use the operating system's
Privacy & Security / Open Anyway process for this trusted app. Do not disable
Gatekeeper globally. Apple documents this process at https://support.apple.com/102445.
Uninstall by removing AG Astro Motion Studio.app; leave your images and projects.

## Runtime data

Caches: %LOCALAPPDATA%/AG Astro Motion Studio/cache on Windows,
~/Library/Application Support/AG Astro Motion Studio/cache on macOS,
and $XDG_DATA_HOME/AG Astro Motion Studio/cache (or ~/.local/share) on Linux.
No mutable JIT cache is written into the packaged application.
Project save locations are chosen by the user. References are relative where
possible; missing moved legacy inputs can be located when opening the project.
