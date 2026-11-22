"""Mid-race joins remain game-authorized; server traces explain denials."""
from pathlib import Path

from tools.patch_join_admission_trace import apply, replace_once

ROOT = Path(__file__).resolve().parents[1]


def test_trace_is_wired_after_live_backfill():
    source = (ROOT / "tools/prepare_source.py").read_text(encoding="utf-8")
    assert source.index("apply_live_join_backfill(out)") < source.index("apply_join_admission_trace(out)")


def test_traces_game_state_without_exposing_tokens_or_bypassing_admission():
    patch = (ROOT / "tools/patch_join_admission_trace.py").read_text(encoding="utf-8")
    for item in ('"ebf"', '"cp"', '"bfmax"', "s->listeners", "s->nmembers", "s->channel"):
        assert item in patch
    assert "role=game-managed" in patch
    assert "if (!s->room && !session_accepting(s))" not in patch
    assert "return 1;" not in patch


def test_source_transform_refuses_unexpected_upstream(tmp_path):
    path = tmp_path / "runtime" / "srv"
    path.mkdir(parents=True)
    (path / "srv_session.c").write_text("unrelated game code", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="source drift"):
        apply(tmp_path)


def test_exact_source_replacement_requires_unique_match():
    import pytest
    with pytest.raises(ValueError):
        replace_once("x x", "x", "y")
