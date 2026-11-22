"""Checked, reproducible native MKWOM launcher changes after pinned source patches.

Never rewrite the upstream binary directly. Every replacement is expected exactly
once so an upstream change fails closed rather than silently breaking UI.
"""
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise ValueError(f"native UI source drift in {path}: expected exactly one match")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def apply(root: Path) -> None:
    profile = root / "runtime/sdk/ov/net_online.c"
    # This file is named according to the actual pinned integration.
    if not profile.exists():
        candidates = [p for p in (root / "runtime").rglob("*.c")
                      if "void net_format_code(const char *code" in p.read_text(encoding="utf-8", errors="replace")]
        if len(candidates) != 1:
            raise ValueError("Could not uniquely locate the MKWOM friend-code formatter")
        profile = candidates[0]
    replace_once(profile, 'snprintf(out, 18, "SW-%.4s-%.4s-%.4s", code, code + 4, code + 8);',
                 'snprintf(out, 18, "%.4s-%.4s-%.4s", code, code + 4, code + 8);')
    # A native profile (friend code + secret) must belong to one MKWOM
    # account, not just the server hostname; otherwise switching users makes
    # the second account claim a friend code already bound to the first.
    replace_once(profile, '''static int profile_path(const char *server, const char *ext, char *out, size_t cap) {
    char dir[1100], key[200];
    if (!online_dir(dir, sizeof dir)) return 0;
    profile_key(server, key, sizeof key);
    snprintf(out, cap, "%s/%s%s", dir, key, ext);
    return 1;
}''', '''static int active_mkwom_account(char out[33]) {
    out[0] = 0;
    char exe[1024];
    if (!plat_exe_path(exe, sizeof exe)) return 0;
    char *slash = strrchr(exe, '/'), *bs = strrchr(exe, '\\\\');
    if (bs > slash) slash = bs;
    if (!slash) return 0;
    *slash = 0;
    char path[1200];
    snprintf(path, sizeof path, "%s/.mkwom/active-account-id.txt", exe);
    uint64_t size = 0;
    unsigned char *data = plat_file_read(path, &size);
    if (!data) return 0;
    int ok = size >= 32 && size <= 34;
    if (ok) for (int i = 0; i < 32; i++)
        if (!((data[i] >= '0' && data[i] <= '9') ||
              (data[i] >= 'a' && data[i] <= 'f'))) ok = 0;
    if (ok) {
        memcpy(out, data, 32);
        out[32] = 0;
    }
    free(data);
    return ok;
}

static int profile_path(const char *server, const char *ext, char *out, size_t cap) {
    char dir[1100], key[200], account[33];
    if (!online_dir(dir, sizeof dir)) return 0;
    profile_key(server, key, sizeof key);
    if (active_mkwom_account(account))
        snprintf(out, cap, "%s/%s_account_%s%s", dir, key, account, ext);
    else
        snprintf(out, cap, "%s/%s%s", dir, key, ext);
    return 1;
}''')
    replace_once(profile, '''    if (!server || !*server || !profile_path(server, ".txt", path, sizeof path)) return 0;
    if (profile_read(path, p)) {''',
                 '''    if (!server || !*server || !profile_path(server, ".txt", path, sizeof path)) return 0;
    // One-time ownership migration for a pre-account-scoped profile: move it,
    // never copy it, so the next account does not inherit the same friend code.
    char account_id[33];
    if (active_mkwom_account(account_id) && !plat_file_exists(path) &&
        online_dir(dir, sizeof dir)) {
        char legacy[1400], key[200];
        profile_key(server, key, sizeof key);
        snprintf(legacy, sizeof legacy, "%s/%s.txt", dir, key);
        if (plat_file_exists(legacy)) plat_file_replace(legacy, path);
    }
    if (profile_read(path, p)) {''')
    # Existing parser already accepts plain, hyphenated and legacy SW-prefixed
    # codes while keeping the wire value as exactly twelve digits.
    launcher_online = root / "runtime/ui/launcher/launcher_online.cpp"
    replace_once(launcher_online, '"SW-1234-5678-9012"', '"1234-5678-9012"')
    # English fallback and all generated UI catalogues.
    for path in (root / "i18n/ui").glob("*.po"):
        source = path.read_text(encoding="utf-8")
        source = source.replace('msgid "Online play with friends"', 'msgid "Friends"')
        source = source.replace('msgid "Online play"', 'msgid "Friends"')
        # Avoid showing stale non-English labels for repurposed navigation keys.
        path.write_text(source, encoding="utf-8")
    launcher = root / "runtime/ui/launcher/launcher.cpp"
    replace_once(launcher, 'float col_h = mark + 48 * s + play_h + gap + pad_h + gap + items * 4 + 28 * s + items;',
                 'float col_h = mark + 48 * s + play_h + gap + pad_h + gap + items * 5 + 28 * s + items;')
    replace_once(launcher, '''    if (files && (!shortcut_asked() || steam_card)) {
        shortcut_card(cw);
    } else if (L.shortcut_note[0]) {
        ImGui::PushTextWrapPos(ImGui::GetCursorPosX() + cw);
        ImGui::TextColored(col4(LOOK_DIM), "%s", L.shortcut_note);
        ImGui::PopTextWrapPos();
    }''',
                 '''    // The Desktop shortcut action already exists in the sidebar.
    // Do not draw its second card below Quit: it overlaps the status/footer
    // in shorter Windows launcher windows, especially at high DPI.
    (void)steam_card;''')
    replace_once(launcher, 'menu_text(UI_LAUNCH_ONLINE), cw, true', '"Friends", cw, true')
    replace_once(launcher, '''    fg->AddText(ImVec2(right - ImGui::CalcTextSize(foot).x, y - lh - 6 * s), LOOK_DIM, foot);''',
                 '''    fg->AddText(ImVec2(right - ImGui::CalcTextSize(foot).x, y - lh - 6 * s), LOOK_DIM, foot);
    // Cache the installed patch identity once; do not hit the disk every frame.
    static char patch_version[96] = {};
    static bool checked_mkwom_version = false;
    if (!checked_mkwom_version) {
        checked_mkwom_version = true;
        char version_path[4096];
        snprintf(version_path, sizeof version_path, "%s/.mkwom/installed.json", L.exe_dir);
        uint64_t version_len = 0;
        uint8_t *bytes = plat_file_read(version_path, &version_len);
        if (bytes && version_len && version_len < 262144) {
            char *json = (char *)malloc((size_t)version_len + 1);
            if (json) {
                memcpy(json, bytes, (size_t)version_len);
                json[version_len] = 0;
                const char *v = strstr(json, "\\"version\\"");
                if (v) {
                    v = strchr(v, ':');
                    if (v) {
                        ++v;
                        while (*v == ' ' || *v == '\\t') ++v;
                        if (*v == '"') {
                            ++v;
                            size_t n = 0;
                            while (n + 1 < sizeof patch_version && *v && *v != '"' &&
                                   *v != '\\\\')
                                patch_version[n++] = *v++;
                        }
                    }
                }
                free(json);
            }
        }
        free(bytes);
    }
    if (patch_version[0]) {
        char info[150];
        snprintf(info, sizeof info, "MKWOM patch %s", patch_version);
        fg->AddText(ImVec2(right - ImGui::CalcTextSize(info).x,
                           y - 2 * (lh + 6 * s)), LOOK_DIM, info);
    }''')
