# V1.7 Windows validation results

Baseline: 553ed21bd09d514f0cdcf66f5c038e8e73d906c5. All timings measured on this Windows hosted runner. Short synthetic clips; no pristine physical end-user machine or long-duration 4K stress test.

## Performance

- sparse: 247 stars; V1.6 preview 22.91 ms, V1.7 22.93 ms (1.00×); cached lookup 0.00030 ms. Video speedup 0.99×.
- dense: 25,938 stars; V1.6 preview 61.05 ms, V1.7 60.64 ms (1.01×); cached lookup 0.00030 ms. Video speedup 1.01×.

## Built preview

{"build_seconds": 1.1404103999999506, "frames": 16, "bytes": 5374081, "decode_median_seconds": 0.004599499999983436, "render_calls_during_cached_playback": 0}

## Output checks

Six dense-field CPU H.264 exports passed decode/dimension/FPS checks: Full HD, QHD (2K), 4K, each landscape and portrait. Each clip has three frames. Sparse/dense source-derived profile comparisons and repeat-render determinism passed. GUI cache, rapid scrubbing, latest-request, playback, pause, reset and unchanged enabled-state checks run in pytest.

The full pytest result and frozen runtime smoke result are separate build evidence. Side-by-side PNGs support visual review; screenshots are references, not the original scientific image pair. Hardware encoders require user hardware and are not claimed validated here.

Pytest results: {"tests": 74, "failures": 0, "errors": 0, "skipped": 0}. See validation/pytest.xml.


## Native executable validation

The Windows x64 frozen executable passed its embedded-runtime self-test with external Python and FFmpeg removed from PATH. Checks: Qt startup, generated depth, manual edit/undo, compiled Numba renderer, exact volumetric loop closure, H.264 encode/decode, FITS/TIFF, cached timeline reuse and Play/Pause.

Built commit: 8f25155d8955a663eb4289973568b894e039b73b. Native run: https://github.com/1alex-vag/AG-Motion-Studio/actions/runs/40248513284.

No macOS build or test was performed. No GitHub release was published. Runtime files below the application directory are identical to the tested CI archive. Physical clean-machine, actual user GPU and long-duration 4K stress validation remain outside these results.
