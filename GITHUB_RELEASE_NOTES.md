# AG Astro Motion Studio V1.6 — Windows performance & star fidelity

V1.6 builds on V1.5 with a reusable preview frame cache, stable timeline controls and more faithful scaling of observed stars.

- Reuse completed unchanged frames through a bounded 512 MB LRU cache (64–1024 MB configurable).
- Debounce scrubbing by 125 ms, replace pending requests and reject obsolete results. Timeline movement keeps the sidebar enabled.
- Play/Pause beside the timeline, independent preview FPS, frame skipping under load and optional Loop Preview.
- Preserve Original Star Size enabled by default; advanced Size Scale, Bloom and Sharpness controls saved in projects.
- Preserve observed RGB profiles, exact source/output scaling and compact subpixel points; faint stars receive no added halo.
- Trim empty sprite support, cache nebula layer premultiplication and foreground-star weights, and avoid protection work outside the visible frame.
- Keep full-quality final exports, automatic memory-aware frame workers, verified GPU encoder probing and CPU fallback. Render progress names the actual encoder.

Includes the standalone Windows executable, bundled runtime and FFmpeg, README, license notices, test report and V1.5 performance comparison. No manual Python installation required.

This release is Windows-only. macOS V1.5 packages are unchanged. No GitHub release is published automatically.

Limitations: RAM-only preview cache; cache misses still require rendering. Detection may merge touching stars or omit sub-threshold sources. Observed profiles undergo fractional resampling and H.264 color subsampling. GPU hardware is not available on the validation runner. Validation uses reproducible sparse/dense synthetic fields and short exports; the provided screenshots are visual references, not the original scientific source pair. Long 4K stress runs and a physical clean Windows machine are not claimed tested. See the enclosed reports for measured results and platform evidence.
