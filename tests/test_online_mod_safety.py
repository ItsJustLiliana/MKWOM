"""Online disables runtime mods and refuses precompiled ExeFS changes."""
import json

import pytest

from mkwom.mod_safety import online_code_mods, require_unmodded_code_online


def test_romfs_only_mod_is_masked_at_runtime_not_edited(tmp_path):
    mod = tmp_path / "mods" / "textures"
    mod.mkdir(parents=True)
    (mod / "mod.json").write_text(json.dumps({"has_romfs": True, "has_exefs": False}))
    ini = tmp_path / "mkw.ini"
    ini.write_text("[launcher]\nMODS=textures\n")
    assert online_code_mods(tmp_path) == []
    require_unmodded_code_online(tmp_path)
    assert "MODS=textures" in ini.read_text()


def test_compiled_exefs_mod_prevents_online_without_touching_offline(tmp_path):
    mod = tmp_path / "mods" / "faster"
    mod.mkdir(parents=True)
    (mod / "mod.json").write_text(json.dumps({"has_exefs": True}))
    ini = tmp_path / "mkw.ini"
    ini.write_text("[launcher]\nMODS=faster\n")
    with pytest.raises(ValueError, match="ExeFS"):
        require_unmodded_code_online(tmp_path)
    assert ini.read_text() == "[launcher]\nMODS=faster\n"


@pytest.mark.parametrize("meta", [{"patches": [{"address": 1}]}, {"image": {"main": {}}}])
def test_other_code_mod_forms_also_block(tmp_path, meta):
    mod = tmp_path / "mods" / "code"
    mod.mkdir(parents=True)
    (mod / "mod.json").write_text(json.dumps(meta))
    (tmp_path / "mkw.ini").write_text("MODS=code\n")
    assert online_code_mods(tmp_path) == ["code"]


def test_pending_code_rebuild_blocks_online(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    (mods / ".rebuild").write_text("faster")
    assert "pending mod code rebuild" in online_code_mods(tmp_path)


def test_missing_mod_metadata_fails_closed(tmp_path):
    (tmp_path / "mkw.ini").write_text("MODS=unknown\n")
    assert online_code_mods(tmp_path) == ["unknown (mod metadata missing)"]


def test_online_native_masks_both_managed_and_legacy_mod_overlays():
    from pathlib import Path
    p = Path(__file__).parents[1] / "patches" / "online-cheat-guard.patch"
    patch = p.read_text()
    assert '"MODS", "ROMFS_MODS"' in patch
    assert 'MKW_ROMFS_MODS' in patch
    assert "mkwom_online_hacks_blocked()" in patch
