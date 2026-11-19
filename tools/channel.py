"""Create a channel manifest from immutable release artifacts. Usage: python tools/channel.py CHANNEL TAG ENDPOINT."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mkwom.cli import endpoint  # noqa: E402
from mkwom import __version__  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("channel", choices=["pre-beta", "beta", "release"])
    p.add_argument("tag")
    p.add_argument("--endpoint")
    a = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._+-]+", a.tag):
        p.error("invalid release tag")
    if a.endpoint:
        endpoint(a.endpoint)
    info = json.loads(Path("dist/build-info.json").read_text())
    patch = Path("dist/mkwom-patch-windows-x64.zip")
    result = {"format": 1, "channel": a.channel, "tag": a.tag, "version": info["version"], "installer_version": __version__,
              "patch_url": f"https://github.com/ItsJustLiliana/MKWOM/releases/download/{a.tag}/{patch.name}",
              "sha256": hashlib.sha256(patch.read_bytes()).hexdigest(), "endpoint": a.endpoint or None}
    Path("dist/channel.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
