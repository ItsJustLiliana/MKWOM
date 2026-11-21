# Lakitu account moderation API — MKWOM backend

This feature lives in the **MKWOM** server repository, not in the separate **Lakitu** Windows client repository. No Lakitu desktop UI or tabs have been changed here.

## Authoritative identity and access

- Ban records use the immutable **32-character account ID**, not the display name or friend code, so renaming cannot evade a ban.
- Shared SQLite account storage applies to **both Beta and Release**.
- The existing private Lakitu gateway on loopback port 9082 requires the same separate admin bearer token and protected Cloudflare Access configuration as existing lobby controls. Public account endpoints have **no** moderator mutation methods.
- Set `MKWOM_ADMIN_ACCOUNTS_DB=/home/mkwom/.local/share/mkwom-accounts/accounts.sqlite3` for the Lakitu gateway and verify it is exactly the file used by `mkwom-accounts.service`. The moderation gateway refuses missing/uninitialized databases and never creates a separate user store.
- Never expose the admin token or SQLite DB in logs, screenshots, the client binary or public endpoints.

## Admin endpoints (existing bearer authentication required)

| Method and path | Purpose |
| --- | --- |
| `GET /v1/moderation/accounts?search=...&limit=50` | Search account IDs/names |
| `GET /v1/moderation/bans?search=...&status=active|all` | Live list of current or historical bans |
| `PUT /v1/moderation/bans/{account_id}` | Set timed or permanent ban |
| `DELETE /v1/moderation/bans/{account_id}` | Unban |
| `PATCH /v1/moderation/accounts/{account_id}/name` | Rename account, preserving identity, friends and scores |
| `GET /v1/moderation/name-rules?search=...&match_mode=all|contains|word` | Live forbidden-name rule list |
| `POST /v1/moderation/name-rules` | Add a forbidden term |
| `DELETE /v1/moderation/name-rules/{rule_id}` | Remove a rule |
| `GET /v1/moderation/name-rule-violations` | Existing accounts that match current rules |

Set a ban with JSON body `{"duration_seconds":3600,"reason":"Cheating"}` (one hour), or `{"duration_seconds":null,"reason":"Repeated abuse"}` (permanent). Durations are limited to 60 seconds–10 years. The name rule API accepts `{"term":"example","match_mode":"contains"}` or `{"term":"example","match_mode":"word"}`. Whole-word matching treats underscores as separators, not letters; names are case-insensitive. The API returns `Cache-Control: no-store` on live list responses.

## Runtime enforcement

- Registration and administrative rename check currently active forbidden-name rules.
- Login, account profile verification and new game-ticket issuance reject any currently banned account with a 403 response. Expired timed bans stop blocking automatically; no service restart needed.
- Renaming preserves the original account ID, sessions, friends and historical scores. Players must use their new account name at their next password login.
- Existing sessions already admitted to an online match **are not immediately disconnected by an account ban**. The native lobby currently has a session-based kick command, not a reliable account-ID kick operation; instant enforcement requires a separate reviewed native-server extension. Signed tickets expire after their short existing lifetime.
- A code-mod ban is distinct from a player account ban: online mod checks remain in the launcher/native runtime.

## Lakitu UI follow-up (not changed here)

Create **Bans**, **Player names** and **Forbidden names** sections/tabs in the Lakitu desktop app:

1. Search a player and select their account ID; choose timed/permanent ban or Unban.
2. Rename an account with collision and forbidden-rule validation.
3. Add/edit/delete forbidden-name terms and switch between **contains** and **whole word**.
4. Show current bans, expiry countdowns, search and filters; poll the private endpoints for live changes. Highlight accounts violating a newly added name rule.
5. Keep all controls disabled when administrator authentication fails. Never leak tokens into logs.

Backend endpoint and account tests should be green before deploying, and the gateway must be updated on STRATO separately from the native game binary. Actual desktop UI and live session disconnect are *not* finished by this backend PR.
