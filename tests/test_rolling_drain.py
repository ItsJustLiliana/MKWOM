"""Required race-safe drain policy invariants before enabling live rolling deploy."""
import pytest

from tools.rolling_drain import DRAIN_SECONDS, Drain


def test_no_new_races_are_admitted_to_old_generation():
    old = Drain(started_at=10, active_races={"race-1"})
    assert old.new_race_allowed() is False
    assert old.decision(12) == "wait"


def test_finishing_race_is_not_enough_until_result_is_durably_saved():
    old = Drain(started_at=10, active_races={"race-1", "race-2"})
    old.result_persisted("race-1")
    assert old.decision(200) == "wait"
    old.result_persisted("race-2")
    assert old.decision(200) == "retire"


def test_old_generation_forces_retirement_at_exact_one_hour():
    old = Drain(started_at=10, active_races={"afk-race"})
    assert old.decision(10 + DRAIN_SECONDS - 1) == "wait"
    assert old.decision(10 + DRAIN_SECONDS) == "force-retire"
    assert old.decision(10 + DRAIN_SECONDS + 5) == "force-retire"


def test_unknown_result_cannot_fake_drained_race():
    old = Drain(started_at=10, active_races={"race-1"})
    with pytest.raises(ValueError):
        old.result_persisted("race-unknown")
    assert old.decision(20) == "wait"


def test_initially_empty_generation_can_retire():
    assert Drain(started_at=0).decision(0) == "retire"
