"""Transactional install, update and uninstall; only verified runtime files are writable.

Used by mkwom.cli. Originals and journals remain in .mkwom, outside game saves/profiles.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
import zipfile

from .delta import LIMIT, decode, sha
from .package import allowed, safe_path


def atom(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".mkwom-new")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def json_write(path: Path, data):
    atom(path, json.dumps(data, indent=2).encode())


def target(root: Path, name: str) -> Path:
    safe_path(name)
    if not allowed(name):
        raise ValueError(f"not a patch-managed file: {name}")
    path = root / name
    # Reject all links/junctions in the path, even ones resolving back into this installation.
    for item in (path, *path.parents):
        if item == root.parent:
            break
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise ValueError(f"linked installation path: {name}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("path leaves installation")
    return path


@contextmanager
def locked(root: Path):
    root = root.resolve()
    state = root / ".mkwom"
    if state.is_symlink() or (hasattr(state, "is_junction") and state.is_junction()):
        raise ValueError("linked patch state directory")
    state.mkdir(exist_ok=True)
    with (state / "lock").open("a+b") as f:
        f.seek(0)
        if not f.read(1):
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise ValueError("another patch operation is running") from e
        try:
            recover(root)
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)


def game_closed():
    if os.name == "nt":
        out = subprocess.check_output(["tasklist", "/FI", "IMAGENAME eq mkw.exe", "/FO", "CSV", "/NH"],
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        if b'"mkw.exe"' in out.lower():
            raise ValueError("close mkw.exe before changing the patch")


def recover(root: Path):
    state = root / ".mkwom"
    journal = read_json(state / "pending.json")
    if journal is None:
        return
    if not re.fullmatch(r"[a-f0-9]{32}", journal["id"]):
        raise ValueError("invalid recovery transaction ID")
    tx = state / "transactions" / journal["id"]
    if not tx.resolve().is_relative_to((state / "transactions").resolve()):
        raise ValueError("invalid recovery journal")
    for name, existed in journal["files"].items():
        path = target(root, name)
        if existed:
            atom(path, (tx / name).read_bytes())
        else:
            path.unlink(missing_ok=True)
    if journal["previous"] is None:
        (state / "installed.json").unlink(missing_ok=True)
    else:
        json_write(state / "installed.json", journal["previous"])
    (state / "pending.json").unlink()


def commit(root: Path, changes: dict[str, bytes | None], previous, installed):
    state = root / ".mkwom"
    txid = uuid.uuid4().hex
    tx = state / "transactions" / txid
    existed = {}
    for name in changes:
        path = target(root, name)
        existed[name] = path.exists()
        if path.exists():
            atom(tx / name, path.read_bytes())
    json_write(state / "pending.json", {"id": txid, "files": existed, "previous": previous})
    try:
        for name, data in changes.items():
            path = target(root, name)
            if data is None:
                path.unlink(missing_ok=True)
            else:
                atom(path, data)
        if installed is None:
            (state / "installed.json").unlink(missing_ok=True)
        else:
            json_write(state / "installed.json", installed)
        (state / "pending.json").unlink()
    except BaseException:
        recover(root)
        raise
    # Retain transaction snapshots for manual recovery; never delete user files recursively.


def install(root: Path, package: Path):
    root = root.resolve()
    if not (root / "mkw.exe").is_file():
        raise ValueError("select the runtime folder containing mkw.exe")
    game_closed()
    with locked(root), zipfile.ZipFile(package) as archive:
        if sum(i.file_size for i in archive.infolist()) > 512 * 1024 * 1024:
            raise ValueError("patch archive too large")
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("duplicate archive entries")
        info = archive.getinfo("manifest.json")
        if info.file_size > 2 * 1024 * 1024:
            raise ValueError("manifest too large")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["format"] != 1 or manifest["platform"] != "windows-x64":
            raise ValueError("unsupported patch format/platform")
        state = root / ".mkwom"
        old = read_json(state / "installed.json")
        prior = {f["path"]: f for f in old["files"]} if old else {}
        files = manifest["files"]
        if not isinstance(files, list) or len(files) > 4000:
            raise ValueError("patch inventory too large")
        names = [f["path"] for f in files]
        if len(names) != len(set(names)) or "mkw.exe" not in names:
            raise ValueError("invalid patch inventory")
        changes = {}
        output_size = 0
        all_names = set(names) | prior.keys()
        base_exe = state / "original/mkw.exe" if old else root / "mkw.exe"
        if sha(base_exe.read_bytes()) != manifest["base_exe_sha256"]:
            raise ValueError("unsupported recomp build: install the official supported version first")
        for name in sorted(all_names):
            path = target(root, name)
            current = path.read_bytes() if path.exists() else None
            saved = state / "original" / name
            if name in prior:
                if (sha(current) if current is not None else None) != prior[name]["after"]:
                    raise ValueError(f"modified patched file; refusing to overwrite: {name}")
                base = saved.read_bytes() if prior[name]["before"] is not None else None
            else:
                base = current
            item = next((f for f in files if f["path"] == name), None)
            if item is None:
                changes[name] = base
                continue
            if (sha(base) if base is not None else None) != item["before"]:
                raise ValueError(f"unsupported or modified original file: {name}")
            if item["after"] is None:
                result = None
            else:
                payload = safe_path(item["payload"])
                if not payload.startswith("payload/") or archive.getinfo(payload).file_size > LIMIT:
                    raise ValueError("invalid payload")
                result = decode(base or b"", archive.read(payload))
                if sha(result) != item["after"]:
                    raise ValueError(f"patch checksum mismatch: {name}")
                output_size += len(result)
                if output_size > 512 * 1024 * 1024:
                    raise ValueError("expanded patch exceeds size budget")
            if name not in prior and base is not None:
                atom(saved, base)
            changes[name] = result
        commit(root, changes, old, manifest)
        return manifest


def uninstall(root: Path):
    root = root.resolve()
    game_closed()
    with locked(root):
        state = root / ".mkwom"
        installed = read_json(state / "installed.json")
        if not installed:
            return
        changes = {}
        for item in installed["files"]:
            name = item["path"]
            path = target(root, name)
            data = path.read_bytes() if path.exists() else None
            if (sha(data) if data is not None else None) != item["after"]:
                raise ValueError(f"modified patched file; preserve it before uninstalling: {name}")
            original = (state / "original" / name).read_bytes() if item["before"] else None
            if original is not None and sha(original) != item["before"]:
                raise ValueError("original backup checksum mismatch")
            changes[name] = original
        commit(root, changes, installed, None)
