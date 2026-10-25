# AG Astro Motion Studio V1.6 — Windows

Windows performance and star fidelity update based on the verified V1.5 codebase.

Extract the entire ZIP. Run `AG_Astro_Motion_Studio_v1.6/AG_Astro_Motion_Studio_v1.6.exe`, or use `INSTALL_WINDOWS.bat` for a per-user copy. Keep the executable and its `_internal` directory together. Python and FFmpeg are bundled. Source images and projects are kept separately and are never deleted by Reset Project.

Load a matching Starless Image and Star Mask, Generate Depth Maps, then move the timeline or press Play beside it. Timeline frames are reused from a 512 MB session-only LRU cache. Advanced star settings allow 64–1024 MB. Cache contents are discarded when scene settings change or a project is reset. Cached retrieval avoids scene rendering; the preview image still requires display conversion.

Play/Pause uses wall-clock timing with skipped frames when rendering cannot meet the requested Preview Playback FPS (Auto/15/24/30). Export FPS remains independent. Loop Preview controls playback repetition independently from export. Cinematic loop selection supplies its initial checkbox state. A compact timeline status shows rendered/cached frames. Rapid scrubbing waits 125 ms, slider release requests the exact selected position, and obsolete work cannot overwrite the current preview.

Advanced star settings include Preserve Original Star Size (on), Star Size Scale (50–150%, default 100%), Star Bloom (0–100%, default 12%), and Star Sharpness (0–100%, default 70%). Observed RGB sprites remain the source of star profiles. Faint stars receive no added bloom; bright-star halos are limited by observed peak. Intensity changes brightness independently. Original Stars / Motion Studio Stars opens a neutral-camera comparison.

All V1.5 features remain: input compatibility handling, Reset Project, depth generation/refinement/manual editing, Nebula Protection, continuous individual star depths, original-stars-only and optional synthetic stars, Cinematic Mode, subject anchor, Volumetric Look, keyframes, portable Save/Open, and landscape/portrait HD through 4K export. New star settings are saved in projects. Older projects use the V1.6 defaults for new settings.

Final renders use all detected stars and full-resolution scene data. Auto encoder probes NVENC, Quick Sync and AMF then falls back to libx264. Render status includes the selected encoder. Automatic frame workers are bounded by cores, available memory and resolution.

See `VALIDATION.md` and `validation/TEST_REPORT.md` for measured results, raw timings, comparison PNGs and short dense-field exports. `PACKAGED_SELF_TEST.json` records checks of the frozen executable without external Python/FFmpeg on PATH. This release does not rebuild or validate macOS.

Known limits: this is artistic 2.5D depth, not a physical gas reconstruction. Source catalog detection can merge touching stars; pixels below detection/support thresholds are not reconstructed. Preview uses the existing 640/900-pixel paths. Fractional resampling and video chroma subsampling can soften subpixel sources. Cache is RAM-only and can evict old frames. An in-flight obsolete render may finish internally. Large depth operations and final export retain their existing exclusive worker. Hardware encoding depends on installed GPU/drivers; hosted Windows validation uses CPU encoding. Long dense 4K sequences and the original scientific source pair require end-user review.
