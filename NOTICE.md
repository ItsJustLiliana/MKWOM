# Sources and licenses

MKWOM distribution tooling is MIT licensed. The multiplayer source patch is derived from these MIT-compatible
sources; original inline notices remain in the patch. No implementation was copied from GPL MKWMP.

| Source | Version/commit | Use |
|---|---|---|
| [adriadam10/mkw-recomp](https://github.com/adriadam10/mkw-recomp) | `96677b6cec85ed05fb4667e03dac5c4d4c2a0bda` / v0.1.15 | Upstream runtime and preparation tools, fetched at build time; MIT |
| [ItsJustLiliana/mkw-recomp](https://github.com/ItsJustLiliana/mkw-recomp) | `7ff13d579d13ff3e5e6320fda5d8ff7982399338` | Existing multiplayer changes including PRs #17 and #18; MIT |
| [Gael50/mkw-recomp](https://github.com/Gael50/mkw-recomp) | `ca1567904cfabca413fa0b73ffe030ba69d109b7`, `918bbd6523729cd18636c051a1e6e62101fd155f` | Original MIT server/client work integrated by the fork; existing inline credits preserved |
| [totk-pc-recomp](https://github.com/valentderah/totk-pc-recomp) | `eccf4dd` Linux-port lineage | Upstream runtime/platform lineage; original MIT notice in `licenses/LICENSE.totk-pc-recomp` |
| [nghttp2](https://github.com/nghttp2/nghttp2) | 1.71.0, archive hash pinned by patched `tools/build/srvdeps.py` | HTTP/2, MIT; full notice bundled with built artifacts |
| [Mbed TLS](https://github.com/Mbed-TLS/mbedtls) | 4.1.1, archive hash pinned by patched `tools/build/srvdeps.py` | TLS, Apache-2.0; full license bundled with built artifacts |

The official recomp distribution retains its bundled third-party licenses. MKWOM does not distribute game code,
game assets, generated game C/SPIR-V or console keys. Installation patches only the native runtime/preparation
tools; local game preparation remains the user's own recomp setup. Binary delta releases require the exact
official supported original and do not contain a prebuilt game library.
