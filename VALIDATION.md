# V1.9 Experimental Windows validation

Backend: CPU/Numba. No GPU rendering backend is shipped or claimed. GPU video encoding remains separate. All sources are deterministic synthetic fixtures; real user data and physical clean-machine testing are not claimed.

## Four field types

- emission: 37,500 XYZ particles, build 0.040 s, cloud arrays 1.43 MB, steady preview 5.8 FPS at 640×400.
- dust: 37,500 XYZ particles, build 0.030 s, cloud arrays 1.43 MB, steady preview 5.8 FPS at 640×400.
- mixed: 37,500 XYZ particles, build 0.032 s, cloud arrays 1.43 MB, steady preview 5.8 FPS at 640×400.
- widefield: 37,500 XYZ particles, build 0.029 s, cloud arrays 1.43 MB, steady preview 5.8 FPS at 640×400.

## Multiple particle densities

[
  {
    "density": 0.25,
    "particles": 18750,
    "array_bytes": 750000,
    "build_seconds": 0.025462400000037633,
    "first_frame_seconds": 0.11718959999996059
  },
  {
    "density": 1.0,
    "particles": 75000,
    "array_bytes": 3000000,
    "build_seconds": 0.04379489999996622,
    "first_frame_seconds": 0.22436330000005
  },
  {
    "density": 2.0,
    "particles": 150000,
    "array_bytes": 6000000,
    "build_seconds": 0.06835269999999127,
    "first_frame_seconds": 0.2663679999999431
  }
]

## Full-quality video

[
  {
    "fps": 24,
    "seconds": 9.3128410999999,
    "particles": 112500,
    "quality": 18,
    "encoder": "libx264",
    "workers": 1,
    "frames": 6
  },
  {
    "fps": 30,
    "seconds": 12.327168799999981,
    "particles": 112500,
    "quality": 18,
    "encoder": "libx264",
    "workers": 1,
    "frames": 8
  }
]

1080p CPU H.264 clips at 24 and 30 FPS passed decode/dimension/rate checks. Clips are 0.25 seconds; no long-duration stress test is claimed. Generated comparison PNGs show neutral, translated/orbit and in-cloud camera poses. Source tests separately cover 74 Classic/previous regressions plus cloud generation, spheres/glow/spikes, clipping, optional mask, saved projects, deterministic loops, cache reuse and memory limits.

## Limits and V2.0 recommendations

The result is an artistic and structurally plausible 3D interpretation of the supplied image and depth information, not a scientific reconstruction of true nebula geometry. Side/rear views are underconstrained. Sparse regions, synthetic layers, alpha-splat grain and disocclusion holes may be visible, especially at extreme offsets. Dust is an alpha/opacity approximation. CPU rendering can be slow at high density; the UI supports prebuilt previews. Stored array bytes exclude source images, transient sorting/projection buffers, Qt and video buffers.

V2.0: optional verified GPU splatting; adaptive screen-space LOD and antialiasing; stronger absorption/occlusion model; quality metrics against real user pairs; independent per-component caches; cancellable cloud generation; advanced safe-camera framing; stronger temporal filtering.

Pytest results: {"tests": 91, "failures": 0, "errors": 0, "skipped": 0}. See validation/pytest.xml.


## Final native validation

{"tests": 91, "failures": 0, "errors": 0, "skipped": 0}

The frozen Windows executable passed Classic startup/depth/editing/Numba/loop/export checks and Experimental Cloud rasterization, sphere/spike rendering, cloud H.264 export and Nebula Only without a mask. System Python and FFmpeg were removed from PATH.

Built commit: 7644de9f011c4763497550cdaeb9765ea3189368. Run: https://github.com/1alex-vag/AG-Motion-Studio/actions/runs/40608456025. The delivered application ZIP is the exact CI archive; no runtime or archive entries were changed afterwards. ZIP CRC checks passed. SHA-256: 6afe7d6d1e419cd00041cb55e7e621812ae073fd853121868e853833b724180e.

No macOS build or tests were performed. No GitHub release was published. Preview particle budgets are bounded; full-quality cloud exports use a higher budget. Native smoke tests do not certify a physical clean installation, real user image fidelity or user GPU drivers.
