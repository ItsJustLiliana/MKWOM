"""Single-server score service generation is explicit and safe."""
import pytest

from tools.install_score_service import make_unit, safe_path


def test_score_service_template_keeps_channel_and_data_local(tmp_path):
    root = tmp_path / "mkwom"
    data = root / "server"
    (data / "pki").mkdir(parents=True)
    (data / "pki" / "ca.der").write_bytes(b"private-ca")
    (root / "tools").mkdir()
    (root / "tools" / "score_delivery.py").write_text("# worker\n")
    env = tmp_path / "beta.env"
    env.write_text("MKWOM_SCORE_BETA_KEY=" + "a" * 64)
    unit = make_unit(root, data, "beta", env)
    assert "mkwom-score" not in unit or "beta" in unit
    assert "--channel beta" in unit
    assert f"ReadWritePaths={data}" in unit
    assert f"EnvironmentFile={env}" in unit
    assert "--channel release" not in unit
    assert "rolling" not in unit.lower()


def test_score_service_requires_initialized_data(tmp_path):
    root = tmp_path / "mkwom"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "score_delivery.py").write_text("# worker\n")
    with pytest.raises(ValueError, match="initialized"):
        make_unit(root, root / "server", "release", tmp_path / "secret.env")


def test_safe_path_rejects_systemd_escaping(tmp_path):
    bad = tmp_path / "bad folder"
    bad.mkdir()
    with pytest.raises(ValueError, match="unsupported"):
        safe_path(bad)
