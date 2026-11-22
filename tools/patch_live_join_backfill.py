"""Native lobby backfill: trust the game's ebf flag plus a live GameSync stream.

Older matching logic also required a participation document (__pgn/..__pus),
which can lag behind or have been pruned while the Gamesync listener is
active. That false-negative sends compatible waiting players into a new lobby.

Never force admission if the game says ebf=false; spectator mode needs an
actual game-side state transition and cannot be faked in GameSync.
"""
from pathlib import Path


def apply(root: Path) -> None:
    path = root / "runtime/srv/srv_session.c"
    source = path.read_text(encoding="utf-8")
    old = "return forming || (there && truthy(map_get(&m->fields, \"ebf\")));"
    new = ("// A live Gamesync listener also proves a session is active; __pgn "
           "writes may lag behind the stream.\n"
           "    // Still require the game's explicit enable-backfill flag.\n"
           "    return forming || ((there || s->listeners > 0) && "
           "truthy(map_get(&m->fields, \"ebf\")));")
    if source.count(old) != 1:
        raise ValueError("Pinned native backfill admission source changed")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")
