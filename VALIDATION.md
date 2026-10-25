# V1.5 validation in progress

Baseline: the completed V1.4 source in this workspace, not the older repository ZIP.
Source tests: 58 passed in a clean Python 3.12 build environment on Linux.
All previous V1.4 behavior checks are retained; GUI checks wait for the newly
asynchronous operations. New tests cover offline refinement, all depth versions,
painting/undo/redo/reset, real brush events, responsive jobs and duplicate guards,
failure recovery, portable moved projects, all resolution/FPS settings, volumetric
identity/subtlety, subject-anchor projection, presets, UI wording and video quality.

Native build validation and the real resolution export matrix are in progress.
The build workflow does not publish a release or modify the main branch.
It freezes on Windows/macOS runners and archives a package only after the actual
bundled executable passes an offline render/startup smoke test.
