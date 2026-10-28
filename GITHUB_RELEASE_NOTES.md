# AG Astro Motion Studio V1.9 — Experimental 3D Cloud preview (Windows)

V1.9 adds an isolated particle-cloud engine alongside the unchanged **Classic 2.5D** renderer. Classic remains the default, including for older projects.

- Build a deterministic XYZ nebula cloud from Starless RGB, current/generated/refined/manual depth, structure-aware density and correlated Z thickness.
- Adaptive sampling suppresses empty background and retains dark dust structures through density and alpha opacity. Cloud Density, Thickness, Softness, Opacity and Dust Bias remain high-level controls.
- Full Scene, Nebula Only and Stars Only. **Nebula Only works without a Star Mask.**
- Independent stable 3D star objects, projected sphere cores, optional restrained glow, 4/6/8 screen-space diffraction spikes and Original Sprite compatibility mode.
- Existing X/Y/Z, yaw/pitch/roll/FOV, camera keyframes, Cinematic paths, timeline scrubbing, Play/Pause, Build Preview and video encoder/export workflow.
- Cloud geometry is built once and cached. Camera motion never rebuilds it. Relevant changes show “3D Cloud needs rebuild”. Separate preview/final particle budgets and memory limits prevent unbounded allocations.
- Near clipping and screen-radius caps prevent giant particles at the camera. A non-blocking viewing-range warning allows advanced camera positions.
- Project files store renderer/content/cloud/star/spike settings, not huge point-cloud data. Cloud geometry is rebuilt after reopening.

## Rendering and encoding

3D rendering uses **CPU/Numba**. A GPU rendering backend is not included in this preview: packaging stability and CPU fallback take priority over adding an unvalidated OpenGL/CUDA driver dependency. Existing NVENC, Quick Sync and AMF probes select only working **video encoders**; GPU encoding is not GPU cloud rendering.

## Installation

Extract the complete `AG_Astro_Motion_Studio_v1.9_Experimental_Windows.zip`. Start `AG_Astro_Motion_Studio_v1.9_Experimental/AG_Astro_Motion_Studio_v1.9_Experimental.exe`, or run `INSTALL_WINDOWS.bat`. Keep the EXE and `_internal` folder together. Python and FFmpeg are bundled.

## Experimental limitations

Experimental 3D Cloud creates an artistic and structurally plausible 3D interpretation of the supplied image and depth information. It is not a scientific reconstruction of the true nebula geometry. A single 2D image cannot uniquely determine hidden geometry.

Sparse regions, alpha-splat grain, stratification and disocclusion holes can appear, particularly at large offsets or rear/side views. Source color is preserved per particle; overall brightness/contrast depends on particle coverage and opacity. Dust uses simplified alpha absorption; stars are composited over the cloud without full per-star volumetric extinction. Classic-specific nebula protection, motion-over-nebula, synthetic background additions and star motion blur are not emulated by the new sphere compositor; they remain available in Classic. The prototype has no physically based scattering, 3D gas dynamics, GPU rasterization or guaranteed interactive FPS at high density. Source preparation is capped at 1200 pixels on the long edge; final rasterization keeps full selected output resolution and uses a larger geometry budget. Dense input stars retain the existing detection limits. Cloud generation and final export are exclusive background operations; mid-build cancellation is deferred.

See `VALIDATION.md` and the included measurements for actual results and limits. No physical clean-machine, user GPU, long 4K stress run or real user image pair is claimed validated. No macOS package is built. No GitHub release is published automatically.

## Recommended for V2.0

Verified optional GPU splatting and screen-space LOD; improved sampling/antialiasing and image fidelity metrics; volumetric star extinction and dust absorption; cancellable generation; conservative framing/coverage tools; tests against real astrophotography pairs; independent geometry/style caches and a broader hardware matrix.

## Verified preview release

91 tests passed. The Windows frozen-runtime smoke test passed for Classic and Experimental Cloud. Four synthetic field types, three cloud densities, and short 1080p H.264 exports at 24/30 FPS were checked. See the validation report for timings and known limitations.
