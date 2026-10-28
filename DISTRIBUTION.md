# V1.9 Experimental Windows distribution

Extract the entire ZIP and keep the executable and `_internal` directory together. Run `AG_Astro_Motion_Studio_v1.9_Experimental/AG_Astro_Motion_Studio_v1.9_Experimental.exe`, or `INSTALL_WINDOWS.bat` for a per-user installation without administrator privileges. Python, Qt, OpenCV, Numba/LLVM and FFmpeg are bundled.

Classic 2.5D is the initial renderer. To try clouds: load Starless, select Experimental 3D Cloud, select Nebula Only (no Star Mask required) or Full Scene (mask required), Generate/Refine/Edit Depth as desired, then Build 3D Cloud. Inspect with existing drag/wheel/camera controls, Build Preview for repeated playback, and Render MP4 through the existing export panel. Rebuild Cloud when its settings or depth inputs change. Camera movement reuses geometry. Reset Camera restores the current camera transform; existing keyframes remain editable.

Project files reference images and depth sidecars; cloud geometry and preview caches are not embedded. Reopening an experimental project requires rebuilding the cloud. Reset Project clears scene/cache state without deleting any original image files. Mutable JIT caches remain in per-user application data, outside the bundle.

Only Windows x64 is built. The workflow runs Classic regressions and new cloud tests, measures four synthetic field types and multiple densities, creates short 1080p/24 and 30 FPS H.264 files, freezes the app and invokes the actual EXE without system Python/FFmpeg on PATH. A package is archived only after its self-test succeeds; ZIP integrity and SHA-256 are checked after closing the archive. GPU render acceleration is not included. GPU video encoding depends on drivers and is distinct from the CPU/Numba renderer.

The report explicitly separates source tests from the frozen-runtime smoke test. Hosted-runner tests do not replace real user image review, a physical clean-machine installation, user GPU tests or long-duration stress tests. macOS packaging is not changed or run for this preview release.
