# V1.7 Windows standalone distribution

Extract the entire Windows ZIP. Run `AG_Astro_Motion_Studio_v1.7/AG_Astro_Motion_Studio_v1.7.exe` directly or run `INSTALL_WINDOWS.bat` to copy it to `%LOCALAPPDATA%/AG Astro Motion Studio/Application` without administrator privileges. Keep the EXE and `_internal` directory together. Python, Qt, OpenCV, Numba/LLVM and FFmpeg are bundled.

Uninstall by removing only the Application directory. Source images, project files and user data are separate. Reset Project clears application state and preview RAM, never source files. Compiled-kernel caches remain in `%LOCALAPPDATA%/AG Astro Motion Studio/cache`, outside the application folder. Preview frames are session-only and are not saved into project files.

The V1.7 workflow builds Windows x64 only. It runs source regressions and sparse/dense performance measurements against V1.5, validates six short dense exports (Full HD/QHD/4K, landscape/portrait), freezes the application and invokes the real EXE with external Python/FFmpeg removed from PATH. The frozen self-test checks Qt startup, depth jobs, editing/undo, compiled Numba rendering, volumetric loops, H.264 encode/decode, FITS/TIFF, preview cache reuse and Play/Pause. Packages are archived only after the self-test passes.

`VALIDATION.md`, `validation/TEST_REPORT.md`, `validation/pytest.xml`, raw measurements, `PACKAGED_SELF_TEST.json` and `BUILD_INFO.json` record checks and limits. `SOURCE_REVISION.json` identifies the exact native build and CI run. GPU encoder availability is probed on the user's computer; hosted CI does not prove operation of specific user GPU/drivers. Native hosted-runner checks do not replace a physical clean-machine test or long-duration dense 4K stress run.

Developers: use Python 3.12 on Windows and `BUILD_WINDOWS.bat`. Build dependencies are pinned in `requirements-build.txt` / `requirements-lock.txt`. macOS V1.5 releases are unchanged and are not rebuilt or tested for this release. This archive does not publish a GitHub release.
