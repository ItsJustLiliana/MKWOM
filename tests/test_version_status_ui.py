"""Version labels show running installer identity and approved channel target."""
from pathlib import Path

from mkwom.version_status import build_id, describe_versions, setup_identity


def test_build_identifiers_are_distinct_from_patch_versions():
    sha = "a" * 40
    assert build_id(sha) == "a" * 12
    assert build_id("") == "local / unknown"
    assert setup_identity("0.1.0", sha) == "Setup v0.1.0\nBuild " + "a" * 12


def test_installed_and_available_patch_and_installer_build():
    current = {"version": "0.1.0-old"}
    latest = {"version": "0.1.0-new",
              "installer_version": "0.2.0",
              "installer_build_sha": "b" * 40}
    status = describe_versions(current, latest, "0.1.0", "a" * 40)
    assert "0.1.0-old → 0.1.0-new" in status
    assert "Setup v0.1.0 (" + "a" * 12 + ") → v0.2.0 (" + "b" * 12 + ")" in status


def test_matching_versions_are_identified_and_unverified_manifest_is_not_invented():
    current = {"version": "0.1.0-good"}
    latest = {"version": "0.1.0-good", "installer_version": "0.1.0",
              "installer_build_sha": "a" * 40}
    assert "Up to date" in describe_versions(current, latest, "0.1.0", "a" * 40)
    assert "Channel: not checked" in describe_versions(None, None, "0.1.0", "a" * 40)


def test_setup_has_no_race_report_export_buttons():
    src = (Path(__file__).resolve().parents[1] / "mkwom/wizard.py").read_text()
    assert "Export Race Connection Report" not in src
    assert "export_race_report" not in src


def test_launcher_update_message_shows_both_builds():
    from mkwom.gui import Launcher

    message = Launcher.describe_updates({
        "installed": "patch-old",
        "available": "patch-new",
        "patcher_installed_version": "0.1.0",
        "patcher_installed_build": "a" * 40,
        "patcher_available_version": "0.1.1",
        "patcher_available_build": "b" * 40,
        "patcher_update": True,
        "patch_update": True,
        "channel": "beta",
    })
    assert "patch-old → patch-new" in message
    assert "aaaa" in message and "bbbb" in message
    assert "Setup EXE is required" in message
