# V1.6 Windows validation results

Baseline: db0849a0a363c3ecc868bfbce4b50c226a9da15e. All timings measured on this Windows hosted runner. Short synthetic clips; no pristine physical end-user machine or long-duration 4K stress test.

## Performance

- sparse: 247 stars; V1.5 preview 23.37 ms, V1.6 22.98 ms (1.02×); cached lookup 0.00030 ms. Video speedup 1.02×.
- dense: 25,938 stars; V1.5 preview 83.97 ms, V1.6 58.53 ms (1.43×); cached lookup 0.00030 ms. Video speedup 1.75×.

## Output checks

Six dense-field CPU H.264 exports passed decode/dimension/FPS checks: Full HD, QHD (2K), 4K, each landscape and portrait. Each clip has three frames. Sparse/dense source-derived profile comparisons and repeat-render determinism passed. GUI cache, rapid scrubbing, latest-request, playback, pause, reset and unchanged enabled-state checks run in pytest.

The full pytest result and frozen runtime smoke result are separate build evidence. Side-by-side PNGs support visual review; screenshots are references, not the original scientific image pair. Hardware encoders require user hardware and are not claimed validated here.

Pytest results: {"tests": 68, "failures": 0, "errors": 0, "skipped": 0}. See validation/pytest.xml.


## Native executable validation

The Windows x64 frozen executable passed its embedded-runtime self-test with external Python and FFmpeg removed from PATH. Checks: Qt startup, generated depth, manual edit/undo, compiled Numba renderer, exact volumetric loop closure, H.264 encode/decode, FITS/TIFF, cached timeline reuse and Play/Pause.

Built commit: 47fc7c6121533a18da74cfa3cd7ff72d1131f454. Native run: https://github.com/1alex-vag/AG-Motion-Studio/actions/runs/40244226179.

No macOS build or test was performed. No GitHub release was published. Runtime files below the application directory are identical to the tested CI archive. Physical clean-machine, actual user GPU and long-duration 4K stress validation remain outside these results.
