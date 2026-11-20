"""Port and data-isolation preflight for a prospective blue/green deploy."""
from dataclasses import replace
import os

import pytest

from tools.rolling_generation_preflight import ServerGeneration, validate_generations


def config(root):
    old = ServerGeneration("old", root / "generations" / "old" / "server",
                           (19443, 19444), (13478, 13479, 11025, 11125, 13334))
    new = ServerGeneration("new", root / "generations" / "new" / "server",
                           (20443, 20444), (14478, 14479, 12025, 12125, 14334))
    return old, new


def test_isolated_generations_accepted_without_writing_anything(tmp_path):
    old, new = config(tmp_path)
    validate_generations(tmp_path, old, new)
    assert not old.data_dir.exists()
    assert not new.data_dir.exists()


@pytest.mark.parametrize("mutate", [
    lambda old, new: replace(new, name=old.name),
    lambda old, new: replace(new, data_dir=old.data_dir),
    lambda old, new: replace(new, data_dir=old.data_dir / "nested" / "server"),
    lambda old, new: replace(new, tcp_ports=(old.tcp_ports[0], 20444)),
    lambda old, new: replace(new, udp_ports=(old.udp_ports[0], 14479, 12025, 12125, 14334)),
    lambda old, new: replace(new, tcp_ports=(18443, 20444)),
    lambda old, new: replace(new, udp_ports=(3478, 14479, 12025, 12125, 14334)),
    lambda old, new: replace(new, udp_ports=(14478, 14478, 12025, 12125, 14334)),
    lambda old, new: replace(new, tcp_ports=(0, 20444)),
])
def test_rejects_unsafe_generations(tmp_path, mutate):
    old, new = config(tmp_path)
    with pytest.raises(ValueError):
        validate_generations(tmp_path, old, mutate(old, new))


def test_rejects_outside_project_and_symlink(tmp_path):
    old, new = config(tmp_path)
    with pytest.raises(ValueError):
        validate_generations(tmp_path, old, replace(new, data_dir=tmp_path.parent / "outside" / "server"))
    if os.name == "nt":
        return  # Creating directory symlinks requires privileges on some Windows runners.
    (tmp_path / "generations").mkdir()
    (tmp_path / "generations" / "linked").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        validate_generations(tmp_path, old, replace(new, data_dir=tmp_path / "generations" / "linked" / "server"))
