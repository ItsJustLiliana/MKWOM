"""Durable MKWOM account moderation shared by Beta and Release.

Only the private Lakitu admin gateway may mutate moderation records. Public
account routes consult the same tables before login/game-ticket issuance.
"""
from __future__ import annotations

import re
import sqlite3
import time

from fastapi import HTTPException


def ensure_schema(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS account_bans (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL,
        expires_at INTEGER,
        reason TEXT NOT NULL,
        CHECK(expires_at IS NULL OR expires_at > created_at))""")
    db.execute("""CREATE TABLE IF NOT EXISTS forbidden_names (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        term TEXT NOT NULL,
        match_mode TEXT NOT NULL CHECK(match_mode IN ('contains', 'word')),
        created_at INTEGER NOT NULL,
        UNIQUE(term, match_mode))""")
    db.execute("""CREATE TABLE IF NOT EXISTS moderation_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        target TEXT NOT NULL,
        detail TEXT NOT NULL,
        created_at INTEGER NOT NULL)""")


def ban_status(db: sqlite3.Connection, user_id: str, now: int | None = None) -> dict | None:
    now = int(time.time()) if now is None else now
    row = db.execute(
        "SELECT created_at,expires_at,reason FROM account_bans WHERE user_id=?",
        (user_id,)).fetchone()
    if not row:
        return None
    created, expiry, reason = row
    if expiry is not None and expiry <= now:
        return None
    return {"created_at": created, "expires_at": expiry, "reason": reason}


def require_not_banned(db: sqlite3.Connection, user_id: str) -> None:
    ban = ban_status(db, user_id)
    if ban:
        raise HTTPException(403, {
            "code": "account_banned",
            "reason": ban["reason"],
            "expires_at": ban["expires_at"],  # null means permanent
        })


def match_rule(username: str, term: str, mode: str) -> bool:
    username = username.casefold()
    term = term.casefold()
    if mode == "contains":
        return term in username
    if mode == "word":
        # Treat underscores as separators in MKWOM's alphanumeric usernames.
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) +
                              r"(?![a-z0-9])", username))
    raise ValueError("Invalid rule mode")


def assert_name_allowed(db: sqlite3.Connection, username: str) -> None:
    for term, mode in db.execute("SELECT term,match_mode FROM forbidden_names"):
        if match_rule(username, term, mode):
            raise HTTPException(422, "Username violates a configured name rule")


def validate_rule(term: str, mode: str) -> str:
    normalized = term.strip().casefold()
    if mode not in ("contains", "word") or not re.fullmatch(r"[a-z0-9_]{2,24}", normalized):
        raise HTTPException(422, "Name rule must be 2-24 letters, digits or underscores")
    return normalized


def record_action(db: sqlite3.Connection, action: str, target: str, detail: str) -> None:
    db.execute("INSERT INTO moderation_audit(action,target,detail,created_at) VALUES (?,?,?,?)",
               (action, target, detail, int(time.time())))


def connect_admin(db_path) -> sqlite3.Connection:
    """Do not create a fresh DB: admin must be bound to the actual account store."""
    if db_path.is_symlink() or not db_path.is_file():
        raise HTTPException(503, "Account database unavailable for moderation")
    try:
        uri = "file:" + str(db_path.resolve()) + "?mode=rw"
        db = sqlite3.connect(uri, uri=True, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        users = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if not users:
            db.close()
            raise HTTPException(503, "Account database schema unavailable")
        ensure_schema(db)
        return db
    except sqlite3.Error:
        raise HTTPException(503, "Account moderation storage unavailable") from None
