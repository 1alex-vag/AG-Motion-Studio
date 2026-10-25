# AG Astro Motion Studio V1.5 — Validation

Date: 25 October 2026. Source baseline: the completed V1.4 workspace/package.
The repository's historical V1.3.1 ZIP was preserved and was not used to rebuild
or replace the working V1.4 functionality.

## Implemented

Offline Depth Refinement; separate Generated/Refined/Manual Depth; depth painting
with Raise/Lower/Smooth/Restore/Flatten; source-pixel brushes, cursor,
Before/After, stroke Undo/Redo and undoable reset; optional Volumetric Look and
preset strengths; selected source-image subject anchor; guarded background jobs;
progress/busy states and final frame counters; landscape/portrait HD/FHD/QHD/4K;
custom even sizes; 24/30/60 FPS; collapsed quality/encoder/worker/output settings;
portable project references and schema 6 migration; writable runtime caches;
native build and installer pipelines.

V1.4 Cinematic Mode, geometry-based strength, smooth paths, loops, original-star
behavior, protection, reset and incompatible-input clearing are retained.
The star catalog, sprite compositor, star wrapper and protection modules are
byte-for-byte identical to V1.4. Engine changes replace the optional model-based
refinement with an offline algorithm. Camera/render changes add the requested
volumetric treatment and subject anchor without changing detected star counts.

## Source tests

58 automated tests passed in the clean Linux Python 3.12 build environment.
All 41 previous behavior checks were retained; GUI tests now await completion of
the asynchronous methods. The 17 added checks cover refinement, depth versions,
paint geometry/history, actual editor mouse events, timer responsiveness while
work is blocked, duplicate-job suppression, failure recovery, manual apply/cancel,
moved project roundtrips, every export preset/FPS setting, volumetric identity and
subtlety, shared anchor projection, presets, UI wording, path recovery and quality/
frame-status propagation.

A strict 40-ms timer-count assertion was found to depend on macOS timer coalescing.
It was replaced with an event-driven bounded heartbeat check while the worker
remains deliberately blocked. This verifies UI responsiveness without requiring
identical timer scheduling across operating systems. No application behavior was
weakened or disabled to pass that check.

During integration, lifetime management was added to retain running QThreads
until their finished signal. No source test or packaged smoke test bypasses the
actual compiled star compositor, real Qt controls or FFmpeg encoder.

## Real export matrix

24 actual full-quality CPU MP4 outputs were encoded and decoded: all eight
prescribed HD/FHD/QHD/4K landscape/portrait sizes at 24, 30 and 60 FPS. Every output
had the requested dimensions and FPS. These are deliberately one-frame synthetic
plumbing checks, not full-duration 4K render/performance stress tests. Loop motion
and ordered parallel multi-frame rendering are covered separately.
Raw results: validation/export_matrix_v15.json.

## Preview and volumetric loop benchmark

Seeded synthetic 1280×720 nebula/star texture; 1,419 detected sources; manually
raised central region; Cinematic Strength 110%, Volumetric Look 25%, Seamless Drift.
Same complete source catalog in both paths. First-frame/JIT warm-up excluded from
five timed frame samples.

| Path | Frame size | Median frame | Scene preparation |
|---|---|---:|---:|
| Fast Preview | 640×360 | 29.48 ms | 273.39 ms |
| Final quality | 1280×720 | 145.28 ms | 356.34 ms |

Fast Preview was 4.93× faster per frame for this specific comparison.
It uses lower resolution and fewer layer/blur samples. This is not a guarantee
for arbitrary input sizes or a comparison with V1.4 speed. The exact t=0 / full-
duration pixel error including blur history was 0.
A 5-second / 24-FPS / 120-frame CPU-encoded loop is included, together with four
rendered times and benchmark_v15.json in examples. The fixture is synthetic and
is not an astronomical observation or the user's original image pair.

## Native build evidence

The build uses an embedded Python runtime, Qt, OpenCV, Numba/LLVM and bundled
FFmpeg. A package is archived only after its actual executable passes an offline
smoke test with system Python/FFmpeg removed from PATH. The smoke test exercises
Qt startup, asynchronous depth generation, painting undo/redo, compiled Numba
signatures, volumetric loop endpoint equality, real CPU H.264 encode/decode,
TIFF and FITS. PACKAGED_SELF_TEST.json and BUILD_INFO.json are included in each
native distribution.

Successful native jobs already observed during this implementation:

| Platform | GitHub run | Job | Result |
|---|---:|---:|---|
| Windows x64 | 40219194661 | 121246853575 | Source tests, frozen app self-test and archive succeeded |
| macOS Apple Silicon | 40219194661 | 121246853487 | Source tests, frozen app self-test and archive succeeded |
| macOS Intel | 40219474717 | 121247697009 | Source tests, frozen app self-test and archive succeeded |

A common final run at the corrected test/dependency commit is recorded below
once completed. Intel macOS uses Numba 0.62.1 / llvmlite 0.45.1 binary wheels,
because current upstream versions no longer publish Intel Mac wheels. The
accelerated renderer is checked at runtime; there is no silent pure-Python
substitution in a successful native package.

Linux freezing/startup/rendering also passed locally; its report is retained in
validation/linux_packaged_self_test.json. The Linux bundle is validation evidence,
not a Windows or macOS build.

## Limits

Native jobs are hosted-runner validations, not interactive tests on the user's
own completely clean computers. Real GPU encoders/drivers, OS-level installer
copying, Apple Developer signing/notarization, the user's real image pair and
long-duration dense-field 4K memory/performance were not tested. Hardware failure
and unavailable-encoder fallback are covered with controlled failure conditions;
CPU encoding is exercised for real.

macOS packages are architecture-specific, ad-hoc signed/unsigned and not notarized.
Use the included operating-system-specific installation instructions. The locked
NumPy wheels require modern macOS; macOS 15 was the tested runner OS. Original
images are referenced rather than embedded, so moved projects need their inputs.
Undo history is bounded/session-local; all depth versions persist. Artistic
2.5D limits such as reflected edges, stretching/ghosting at extreme motion and
anchor clamping to the output crop remain. No physical gas reconstruction or
hidden-structure generation is claimed.
