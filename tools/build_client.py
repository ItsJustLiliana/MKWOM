"""Build runtime-only changes and a verified binary delta. Usage: python tools/build_client.py --source DIR --version ID."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mkwom.package import allowed, make  # noqa: E402
from mkwom.installer import install, uninstall  # noqa: E402


def extract_base(archive: Path, base: Path):
    with zipfile.ZipFile(archive) as z:
        exe = [i.filename for i in z.infolist() if i.filename == "mkw.exe" or i.filename.endswith("/mkw.exe")]
        if len(exe) != 1:
            raise ValueError("ambiguous official runtime root")
        prefix = exe[0][:-len("mkw.exe")]
        for item in z.infolist():
            if item.is_dir() or not item.filename.startswith(prefix):
                continue
            name = item.filename[len(prefix):]
            if not allowed(name):
                continue
            dest = base / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(item))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--skip-build", action="store_true")
    a = p.parse_args()
    source = a.source.resolve()
    if not a.skip_build:
        subprocess.run([sys.executable, str(source / "tools/build/windeps.py")], cwd=source, check=True)
        subprocess.run([sys.executable, str(source / "tools/build/build.py"), "--target", "windows", "--dist",
                        "--runtime-only", "--jobs", "2"], cwd=source, check=True)
    spec = json.loads((ROOT / "compatibility.json").read_text())
    out = ROOT / "build/client"
    out.mkdir(parents=True, exist_ok=True)
    archive = out / "upstream.zip"
    if not archive.exists():
        urllib.request.urlretrieve(spec["upstream_windows_url"], archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != spec["upstream_windows_sha256"]:
        raise ValueError("official archive checksum mismatch")
    base, target = out / "base", out / "target"
    if base.exists() or target.exists():
        raise ValueError("use a clean build/client directory")
    extract_base(archive, base)
    shutil.copytree(base, target)
    sys.path.insert(0, str(source / "tools/build"))
    module = importlib.util.spec_from_file_location("mkwom_dist", source / "tools/build/dist.py")
    dist = importlib.util.module_from_spec(module)
    module.loader.exec_module(dist)
    dist.copy_sources(target / "setup/src")
    shutil.copy2(source / "build/dist/windows/mkw.exe", target / "mkw.exe")
    shutil.copy2(source / "build/obj-dist-win/libmkw.dll.a", target / "setup/lib/libmkw.dll.a")
    release = ROOT / "dist"
    release.mkdir(exist_ok=True)
    patch = release / "mkwom-patch-windows-x64.zip"
    manifest = make(base, target, patch, a.version)
    with zipfile.ZipFile(patch, "a", compression=zipfile.ZIP_DEFLATED) as z:
        for name in ("LICENSE", "NOTICE.md"):
            z.write(ROOT / name, "LICENSES/" + name)
        z.write(ROOT / "licenses/LICENSE.totk-pc-recomp", "LICENSES/LICENSE.totk-pc-recomp")
        z.write(source / "build/srv/src/nghttp2-1.71.0/COPYING", "LICENSES/LICENSE.nghttp2")
        z.write(source / "build/srv/src/mbedtls-4.1.1/LICENSE", "LICENSES/LICENSE.mbedtls")
    verify = out / "roundtrip"
    shutil.copytree(base, verify)
    install(verify, patch)
    for item in manifest["files"]:
        path = verify / item["path"]
        if item["after"] and hashlib.sha256(path.read_bytes()).hexdigest() != item["after"]:
            raise ValueError("real runtime installation verification failed")
    uninstall(verify)
    if (verify / "mkw.exe").read_bytes() != (base / "mkw.exe").read_bytes():
        raise ValueError("real runtime restoration verification failed")
    print("Official v0.1.15 -> MKWOM -> original: verified")


if __name__ == "__main__":
    main()
