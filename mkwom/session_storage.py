"""Protected per-installation MKWOM session bridge for direct Windows game launches.

The credential stays in Windows Credential Manager for the setup GUI. A copy
protected with the current Windows user's DPAPI key lets the native game restore
it without storing a plaintext bearer token or requiring the Python setup.
"""
import ctypes
import os
from pathlib import Path
import re

from .installer import atom

BLOB_NAME = "account-session.dpapi"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def session_path(game: Path) -> Path:
    return game / ".mkwom" / BLOB_NAME


def protect_for_game(game: Path, access_token: str, channel: str) -> None:
    if os.name != "nt":
        raise OSError("Windows DPAPI is required for saved game sessions")
    if channel != "pre-beta":
        raise ValueError("No native game authentication endpoint for this channel")
    if not re.fullmatch(r"[a-f0-9]{64}", access_token):
        raise ValueError("Invalid account session")
    raw = (channel + "\n" + access_token).encode("ascii")
    src_buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    src = DATA_BLOB(len(raw), src_buffer)
    encrypted = DATA_BLOB()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p, ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                                        ctypes.POINTER(DATA_BLOB)]
    crypt.CryptProtectData.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not crypt.CryptProtectData(ctypes.byref(src), "MKWOM game session", None, None,
                                  None, 0x1, ctypes.byref(encrypted)):
        raise OSError(ctypes.get_last_error(), "Windows could not protect the game session")
    try:
        protected = ctypes.string_at(encrypted.pbData, encrypted.cbData)
    finally:
        kernel.LocalFree(ctypes.cast(encrypted.pbData, ctypes.c_void_p))
    if not protected:
        raise ValueError("Windows returned an empty protected session")
    atom(session_path(game), protected)


def remove_game_session(game: Path) -> None:
    session_path(game).unlink(missing_ok=True)
