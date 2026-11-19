"""Write exact artifact checksums/build identity for Actions; run after all build jobs succeed."""
import hashlib
import json
import os
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
sha = os.environ["SOURCE_SHA"]
if os.environ["SOURCE_BRANCH"] not in ("main", "pre-beta"):
    raise ValueError("build candidates only from main/pre-beta; Beta and Release require manual promotion")
channel = "pre-beta"
tag = f"{channel}-{os.environ['RUN_ID']}-{sha[:12]}"
shutil.copy2(root / "tools/deploy_server.py", "dist/deploy_server.py")
for name in ("LICENSE", "NOTICE.md"):
    shutil.copy2(root / name, Path("dist") / name)
Path("dist/build-info.json").write_text(json.dumps({"format": 1, "source_sha": sha,
    "version": f"0.1.0-{sha}", "upstream": json.loads((root / "compatibility.json").read_text())}, indent=2))
assets = sorted(p for p in Path("dist").iterdir() if p.is_file() and p.name != "SHA256SUMS")
Path("dist/SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in assets))
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"tag={tag}\nchannel={channel}\n")
