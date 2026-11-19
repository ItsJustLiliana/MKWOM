"""Build patches from official and patched runtime distributions: python -m mkwom.package BASE TARGET OUT."""
import argparse
import json
from pathlib import Path, PurePosixPath
import zipfile

from .delta import LIMIT, encode, sha


def safe_path(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or "\\" in name or ":" in name or path.is_absolute()
            or any(p in ("..", ".", "") for p in name.split("/"))):
        raise ValueError("unsafe archive path")
    reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
                *[f"LPT{i}" for i in range(1, 10)]}
    if any(p.endswith((".", " ")) or p.split(".", 1)[0].upper() in reserved or
           any(ord(c) < 32 or c in '<>"|?*~' for c in p) for p in path.parts):
        raise ValueError("unsafe Windows archive path")
    return name


def allowed(name: str) -> bool:
    safe_path(name)
    # Only runtime and preparation tools; never user data, game libraries or dumps.
    return name == "mkw.exe" or name.startswith("setup/src/") or name == "setup/lib/libmkw.dll.a"


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and allowed(p.relative_to(root).as_posix())}


def make(base: Path, target: Path, output: Path, version: str) -> dict:
    old, new = tree(base), tree(target)
    if "mkw.exe" not in old or "mkw.exe" not in new:
        raise ValueError("both distributions must contain mkw.exe")
    manifest = {"format": 1, "version": version, "upstream": "0.1.15", "platform": "windows-x64",
                "base_exe_sha256": sha(old["mkw.exe"]), "files": []}
    marker = b"MKW_RECOMP_" + b"GENERATED_FROM_GAME_CODE"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(old.keys() | new.keys()):
            a, b = old.get(name), new.get(name)
            if a == b:
                continue
            if b is not None and (len(b) > LIMIT or (marker in b and not name.endswith("/gen.py"))):
                raise ValueError(f"forbidden generated content: {name}")
            payload = None
            if b is not None:
                payload = f"payload/{len(manifest['files'])}.delta"
                archive.writestr(payload, encode(a or b"", b))
            manifest["files"].append({"path": name, "before": sha(a) if a is not None else None,
                                      "after": sha(b) if b is not None else None, "payload": payload})
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("base", type=Path)
    p.add_argument("target", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--version", required=True)
    a = p.parse_args()
    make(a.base, a.target, a.output, a.version)


if __name__ == "__main__":
    main()
