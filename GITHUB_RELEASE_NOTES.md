# AG Astro Motion Studio V1.7 — Windows

- Build Preview creates a reusable lossless temporary sequence for playback and immediate timeline dragging. Preview RAM remains bounded; disk previews have a 2 GB budget and are removed on reset/invalidation.
- Dragging shows cached imagery; release requests the exact selected position. Latest-request guards remain in place.
- Enhanced Depth adds Overall Depth, Fine Structure Depth, Dust Emphasis, Dust Depth Bias, Local Depth Contrast and edge-aware smoothing. Soft, Balanced, Dusty and Dramatic profiles are starting points. Apply Enhanced Depth recomputes from Generated Depth asynchronously without cumulative reapplication, preserving manual offsets.
- Depth Editor selection brush/subtraction, connected similar-depth Magic Select, Select Similar Depth, diffuse-background selection, feathered selection operations and depth Undo/Redo.
- Explicit minus/plus buttons replace spinbox arrows while retaining keyboard entry. Duration is 1–300 seconds.
- Star atlases are reused independently of nebula changes. Original observed-star profiles, subpixel rendering and full-quality exports remain.
- Hardware video encoders are probed once at startup; unavailable explicit choices are disabled. Rendering remains CPU/Numba; GPU encoding is not described as GPU rendering.

Windows only. No macOS build or GitHub release publication.

Known limits: temporary preview sequence decoding still uses CPU and disk; building a long preview can reach the 2 GB budget. Selection operations on very large maps and selection-brush overlays can be expensive. Magic Select uses connected depth similarity, not semantic object recognition. Background selection is heuristic and should be refined manually. Depth enhancement is artistic, not measured distance. Enhanced Depth is applied explicitly, rather than rebuilding continuously while sliders move. Preview-only FPS/loop choices are session controls. No physical clean-machine or user GPU validation is claimed.

## Windows validation

74 source tests passed; the frozen Windows runtime self-test passed. Six dense-field Full HD/QHD/4K landscape/portrait clips passed encode/decode checks.

- Sparse (247 stars): uncached preview 22.91 ms in V1.6, 22.93 ms in V1.7; cached lookup 0.00030 ms.
- Dense (25,938 stars): uncached preview 61.05 ms in V1.6, 60.64 ms in V1.7; cached lookup 0.00030 ms.

Cache lookup timings exclude Qt display conversion. Synthetic timings are specific to the Windows runner; see the complete raw comparison and limitations in the report.
