"""Package a tested standalone server; no production data. Usage: python tools/server_release.py SOURCE VERSION."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("version")
    a = p.parse_args()
    exe = a.source / "build/server/mkw-server"
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        metadata = Path(temp) / "release.json"
        metadata.write_text(json.dumps({"format": 1, "version": a.version,
                                       "sha256": hashlib.sha256(exe.read_bytes()).hexdigest()}))
        with tarfile.open(out / "mkwom-server-linux-x64.tar.gz", "w:gz") as archive:
            archive.add(exe, arcname="mkw-server")
            archive.add(ROOT / "tools/score_delivery.py", arcname="score_delivery.py")
            archive.add(metadata, arcname="release.json")
            for name in ("LICENSE", "NOTICE.md"):
                archive.add(ROOT / name, arcname=name)
            archive.add(a.source / "build/srv/src/nghttp2-1.71.0/COPYING", arcname="LICENSE.nghttp2")
            archive.add(a.source / "build/srv/src/mbedtls-4.1.1/LICENSE", arcname="LICENSE.mbedtls")


if __name__ == "__main__":
    main()
