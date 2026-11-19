# Multiplayer source changes

`multiplayer.patch` applies to the exact upstream commit in `../compatibility.json`. It contains the existing MIT
multiplayer runtime/server/UI and regression tests, integrated with v0.1.15, plus the opt-in managed friends-only
view. No complete upstream checkout, native executable, game files or game-generated content is stored here.

Build through `tools/prepare_source.py`; CI checks patch application and builds from official upstream source.
Maintain the patch from a prepared source tree and preserve the source credits in `../NOTICE.md`.
