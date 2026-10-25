# AG Astro Motion Studio V1.5

Cinematic 2.5D animation from a matching starless image and observed star mask.
Continues the working V1.4 renderer and original RGB star sprites.

## Quick workflow

Load Starless → Load Star Mask → Generate Depth Maps → optional Depth Refinement
or Edit Depth Map → Cinematic Mode → Preview → Render MP4.

Generate Depth Maps, refinement, detection, previews, loop preparation and project
opening run as background jobs. The bottom status/progress area shows the current
stage, known percentages or an animated busy state. Duplicate jobs are blocked;
inputs are temporarily locked until completion. Errors restore usable controls.

## Depth Refinement and Editor

Depth Refinement works offline using image structure, local contrast and
edge-aware smoothing; choose Gentle, Balanced or Strong. It preserves Generated
Depth and stores Refined Depth separately. It is repeatable and non-destructive.

Edit Depth Map opens a dedicated editor with Raise (toward camera), Lower,
Smooth, Restore (to Generated Depth) and Flatten. Brush Size is 10–1000 source
pixels, Strength 1–100%, Softness 0–100%. Paint on the visible color map; the cursor
shows the brush radius. Before/After displays Generated Depth. Undo/Redo act per
stroke (Ctrl/Cmd+Z and platform Redo shortcuts). Reset Depth Map restores Generated
Depth and can be undone. Apply stores a separate Manual Depth; Cancel leaves the
project unchanged. History uses local patches, retaining recent actions within a
128 MiB budget (one unusually large action is always retained). Undo history is
session-local; all three depth versions are saved in the project sidecar.

Changing the refinement preset preserves the manual correction delta relative
to its previous base. Source image pixels and Generated Depth are never edited.

## Cinematic and Volumetric Look

Enable Cinematic Mode for Preset, 3D Strength, Camera Motion, Star Motion,
Atmosphere, Loop Mode and Duration. Advanced Settings retains all existing star,
protection, camera/keyframe, depth-contrast and smoothing controls.

Gentle / Cinematic / Deep 3D / Fly-through retain their V1.4 main slider values.
They additionally set Volumetric Strength to 10 / 25 / 40 / 50%. Volumetric Look
is off by default and must be explicitly enabled in Advanced Settings. It adds
weak depth-dependent opacity, softness, haze, glow derived from the existing
image, and slightly greater differential depth-band motion. Strength 0 is off.
It does not create nebula structures or alter star count. This is an artistic
2.5D look, not physical volumetric reconstruction or measured astronomical depth.

Keep Subject Centered uses the image center by default. Pick Subject Anchor
opens the Starless preview; click the target to retain its normalized source
position. Use Image Center restores the default. The shared camera aims at the
anchor's processed depth, controlling yaw/pitch while leaving roll/FOV editable.
Anchors outside the chosen output crop are limited to its edge and reported in
preview status. Extreme depth, angles or zoom can still show reflected borders,
2.5D stretching or ghosting. Center locking cannot guarantee framing of an entire
extended object.

Linear / Smooth / Cinematic paths, editable keyframes and Push In / Pull Out /
Side Drift / Orbit / Fly-through remain available. Off and Ping-Pong follow the
path; closed Orbit/Drift use its extents with periodic motion. Loop export samples
[0, duration), without a duplicated endpoint. Preview Loop renders up to 480 px,
normally 12 FPS, with at most 240 cached frames; long durations lower preview FPS.

## Video export

Orientation selects Landscape or Portrait. Both offer HD (1280×720 / 720×1280),
Full HD (1920×1080 / 1080×1920), QHD/2K (2560×1440 / 1440×2560) and 4K
(3840×2160 / 2160×3840). FPS: 24, 30, 60. Custom dimensions must be even and between
2 and 8192. Advanced Export Settings exposes dimensions, encoder, bounded frame
workers, output path and CRF/CQ quality (default 18, lower is higher quality).

Fast Preview uses up to 640 px, reduced layer/blur samples; High Quality Preview
uses up to 900 px and final layer quality. Final Render uses the complete catalog
and chosen output size. Video status reports Rendering frame N / Total and the
percentage. Auto probes NVENC, Quick Sync and AMF, falling back to CPU H.264.
GPU encoding accelerates compression; image rendering remains on CPU.

## Projects and reset

Schema 6 saves Generated, Refined and Manual Depth, protection, camera paths,
cinematic/volumetric controls, subject anchor and export settings. Older projects
open with compatible defaults. Save the JSON and .depth.npz together. References
use relative forward-slash paths where possible; source images are not embedded.
If a moved legacy image is missing, opening the project asks you to locate it.

Reset Project clears all project/preview/depth data and default camera state;
it never deletes or rewrites source files. A newly loaded image with incompatible
resolution automatically clears the old counterpart in either direction and
waits for a matching second image. Invalid files leave existing valid inputs intact.

## Installation and building

For a genuine Windows native ZIP: extract it completely, keep the EXE with all
runtime files, and start the EXE or use its user installer. For a macOS native ZIP:
choose the matching CPU architecture and run INSTALL_TO_APPLICATIONS.command.
These packages embed Python and FFmpeg; end users do not install Python.
See DISTRIBUTION.md for building, installation, Gatekeeper and runtime data paths.

For this source package, use Python 3.12 and INSTALL_WINDOWS.bat / INSTALL_MAC.command,
then the corresponding START script. To build standalone packages use
BUILD_WINDOWS.bat / BUILD_MAC.command on the intended operating system. A native
GitHub Actions build matrix and locked build dependencies are included.

Development checks: pip install -r requirements-dev.txt, then
QT_QPA_PLATFORM=offscreen python -m pytest -q tests (set the environment variable
using your platform's shell syntax). See VALIDATION.md for measured results and
any outstanding native verification. English release notes are in
GITHUB_RELEASE_NOTES.md. The original V1.4 README is archived in docs/history.
