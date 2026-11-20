"""Regression guard: first Online opening never does profile I/O on render thread."""
from pathlib import Path

PATCH = (Path(__file__).resolve().parents[1] / "patches/multiplayer.patch").read_text(encoding="utf-8")
START = PATCH.index("diff --git a/runtime/ui/launcher/launcher_online.cpp")
END = PATCH.index("diff --git ", START + 10)
CODE = PATCH[START:END]


def test_profile_loaded_by_worker_not_first_open_or_periodic_ui_refresh():
    worker = CODE[CODE.index("+static int SDLCALL worker("):CODE.index("+static void start(")]
    opened = CODE[CODE.index("+void online_opened("):CODE.index("+static const ImVec4")]
    page = CODE[CODE.index("+void online_page("):]
    assert "net_profile_load(t->server, &profile, 1)" in worker
    assert "load_code();" not in opened
    assert "load_code();" not in page
    assert "if (!strcmp(O.server, t->server))" in worker


def test_patch_hunk_line_count_matches_generated_source():
    section = CODE.splitlines()
    import re
    hunk = next(line for line in section if line.startswith("@@"))
    wanted = int(re.search(r"\+1,(\d+)", hunk).group(1))
    actual = sum(line.startswith("+") and not line.startswith("+++") for line in section)
    assert wanted == actual
