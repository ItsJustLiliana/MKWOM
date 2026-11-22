"""Expose trustworthy join admission details without bypassing the game's admission flag.

Applies strictly to the pinned native server after the regular MKWOM patches.
Avoids tokens, credentials and raw request payloads in diagnostic output.
"""
from pathlib import Path


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Native friend join source drift; refusing unsafe update")
    return source.replace(old, new, 1)


def apply(root: Path) -> None:
    path = root / "runtime/srv/srv_session.c"
    source = path.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '''            srv_log("friend join rejected: game lobby is not accepting backfill");''',
        '''            const SrvDoc *state = docs_find(&s->docs, "__gs/m");
            const SrvVal *cp = state ? map_get(&state->fields, "cp") : NULL;
            int cp_false = cp && (cp->kind == V_BOOL || cp->kind == V_INT) && !cp->u.i;
            const SrvVal *backfill = state ? map_get(&state->fields, "ebf") : NULL;
            int ebf = backfill && (backfill->kind == V_BOOL || backfill->kind == V_INT) && backfill->u.i;
            int64_t bfmax = state ? map_int(&state->fields, "bfmax", 0) : 0;
            int participant_docs = 0;
            for (int j = 0; j < s->docs.n; j++)
                if (!strncmp(s->docs.doc[j].path, "__pgn/", 6) &&
                    strstr(s->docs.doc[j].path, "/__pus/")) {
                    participant_docs = 1;
                    break;
                }
            srv_log("friend join rejected: session=%s channel=%s phase=%s docs=%d listeners=%d "
                    "ebf=%d cp_false=%d members=%d max=%d bfmax=%lld",
                    s->id, s->channel, participant_docs ? "playing" : "forming",
                    participant_docs, s->listeners, ebf, cp_false, s->nmembers,
                    s->max_players, (long long)bfmax);''',
    )
    source = replace_once(
        source,
        '''        srv_log("a player joined %s (%d in it, via %s)", s->id, s->nmembers, s->room ? "room" : "friend lobby");''',
        '''        srv_log("friend join accepted: session=%s channel=%s members=%d role=game-managed",
                s->id, s->channel, s->nmembers);''',
    )
    path.write_text(source, encoding="utf-8")
