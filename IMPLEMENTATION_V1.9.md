# V1.9 implementation summary

Classic Scene, original sprite renderer, star catalog and video pipeline remain unchanged from verified V1.7. The GUI adds an opt-in Cloud adapter sharing existing camera keyframes, timeline cache and encoder export contracts. Geometry, settings, raster kernels and memory budgeting live in motionstudio/cloud.py. No GL/CUDA dependency is added.

Cloud preparation downsamples source analysis to a bounded grid, combines the current depth with image structure, builds an adaptive signal/dust density map and samples fixed-seed particles. Correlated multiscale noise and coherent strata supply Z thickness; XY is generated along source camera rays. Every particle stores immutable XYZ, RGB, opacity, size, density and dust weight. The depth-sorted CPU/Numba alpha splatter applies perspective, near fade/clipping and screen-size caps. Independent star objects use existing detected depths and stable identifiers; sphere cores, glow and screen-space spikes are composed separately.

The GUI distinguishes Classic/Cloud and Full/Nebula Only/Stars Only, supports optional masks, explicit cloud building/rebuild status, cloud presets, safe-range warnings and reset-camera controls. Projects store settings and references, never large point arrays. Geometry invalidation depends on source/depth/cloud settings, not timeline position. Final geometry is prepared once at a higher budget before the existing video pipeline consumes it.

This is a CPU proof of concept, not scientific reconstruction or physically based volumetric transfer. See the release notes and report for Classic-specific features not replicated by the sphere compositor and V2.0 recommendations.
