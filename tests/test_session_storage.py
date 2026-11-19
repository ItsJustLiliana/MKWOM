"""Windows game session must remain encrypted at rest and bound to the Windows user."""
import ctypes
import os

import pytest

from mkwom.session_storage import DATA_BLOB, protect_for_game, remove_game_session, session_path


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI only")
def test_dpapi_game_session_roundtrip(tmp_path):
    token = "a" * 64
    protect_for_game(tmp_path, token, "pre-beta")
    blob = session_path(tmp_path).read_bytes()
    assert token.encode() not in blob
    assert b"pre-beta" not in blob

    ciphertext = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    source = DATA_BLOB(len(blob), ciphertext)
    plaintext = DATA_BLOB()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(DATA_BLOB)
    ]
    crypt.CryptUnprotectData.restype = ctypes.c_int
    assert crypt.CryptUnprotectData(ctypes.byref(source), None, None, None,
                                    None, 0x1, ctypes.byref(plaintext))
    try:
        assert ctypes.string_at(plaintext.pbData, plaintext.cbData) == b"pre-beta\n" + token.encode()
    finally:
        ctypes.WinDLL("kernel32").LocalFree(ctypes.cast(plaintext.pbData, ctypes.c_void_p))
    remove_game_session(tmp_path)
    assert not session_path(tmp_path).exists()


def test_no_game_session_can_be_saved_without_windows(tmp_path):
    if os.name == "nt":
        pytest.skip("only relevant outside Windows")
    with pytest.raises(OSError, match="Windows DPAPI"):
        protect_for_game(tmp_path, "a" * 64, "pre-beta")
