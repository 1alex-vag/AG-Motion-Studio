# AG Astro Motion Studio V1.5 — Depth Editor, Volumetric Look & Native Builds

Built directly on V1.4, retaining the original observed-star engine, cinematic
controls, smooth camera paths, loop modes, reset and input compatibility handling.

- Replaced optional model-related UI with deterministic offline Depth Refinement.
- Added a dedicated depth editor: Raise, Lower, Smooth, Restore and Flatten;
  source-pixel brush size, strength, softness, brush cursor, Before/After,
  per-stroke Undo/Redo and Reset Depth Map.
- Preserved Generated, Refined and Manual Depth separately in schema 6 projects.
- Added optional Volumetric Look and 0–100% strength, using existing image data
  for subtle opacity/softness/haze/glow and depth-band separation.
- Added a clickable subject anchor alongside image-center locking.
- Moved depth generation, refinement, detection, preview preparation and project
  opening into guarded background jobs with visible progress and error recovery.
- Added Landscape/Portrait orientation with HD, Full HD, QHD/2K and 4K presets,
  custom even dimensions, 24/30/60 FPS and collapsed encoder/worker/quality controls.
- Added per-frame render status, portable project paths and writable runtime
  caches outside packaged application folders.
- Added locked native PyInstaller builds, Windows user installer, macOS app
  installer, dependency notices and offline packaged-runtime smoke tests.

See VALIDATION.md and DISTRIBUTION.md for actual build/test evidence and remaining
platform limitations. Build scripts alone are not presented as native binaries.
