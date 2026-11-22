import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "diagnose_beta_ice.py"
spec = importlib.util.spec_from_file_location("diagnose_beta_ice", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_classification_and_report():
    lines = [
        "2026-11-22 15:27:05 ens6 In IP 86.89.38.216.60966 > 31.70.192.231.13334: UDP, length 16",
        "2026-11-22 15:27:05 ens6 In IP 86.89.38.216.60966 > 31.70.192.231.11025: UDP, length 16",
        "2026-11-22 15:27:05 ens6 Out IP 31.70.192.231.11025 > 86.89.38.216.60966: UDP, length 16",
        "2026-11-22 15:27:06 ens6 In IP 86.89.38.216.60503 > 31.70.192.231.13479: UDP, length 120",
        "2026-11-22 15:27:07 ens6 Out IP 31.70.192.231.49500 > 86.89.38.216.60503: UDP, length 80",
    ]
    counts, samples = mod.summarize(lines)
    assert counts["beta_nat_3", "to_server"] == 1
    assert counts["beta_nat_1", "to_server"] == 1
    assert counts["beta_nat_1", "from_server"] == 1
    assert counts["beta_turn", "to_server"] == 1
    assert counts["beta_relay", "from_server"] == 1
    assert "TURN control/relay-range traffic observed" in mod.report(counts, samples)


def test_no_turn_does_not_claim_failure():
    counts, samples = mod.summarize([
        "ens6 In IP 86.89.38.216.60503 > 31.70.192.231.11025: UDP, length 16",
    ])
    message = mod.report(counts, samples)
    assert "No TURN control packets observed" in message
    assert "does NOT prove" in message
