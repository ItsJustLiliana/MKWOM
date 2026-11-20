"""HTTPS account client for the graphical launcher. Secrets live in OS credential storage."""
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import keyring

SERVICE = "MKWOM Online Account"
USERNAME_KEY = "access-token"
ACCOUNTS_URL = "https://mkwom-api.liliananuzohra.com"


class AuthError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AuthError("Account server redirects are disabled")


def api_base(channel: str = "pre-beta") -> str:
    configured = os.environ.get("MKWOM_ACCOUNTS_URL", "").strip()
    base = (configured or ACCOUNTS_URL).rstrip("/")
    if not base:
        raise AuthError("Accounts will be available after the secure community server is configured.")
    address = urlsplit(base)
    if address.scheme != "https" or not address.hostname or address.username or address.password or address.query or address.fragment:
        raise AuthError("MKWOM account API requires a dedicated HTTPS address")
    if address.path not in ("", "/"):
        raise AuthError("Account API URL cannot contain a path")
    return base


def call(path: str, body: dict | None = None, token: str | None = None,
         channel: str = "pre-beta") -> dict:
    if path not in ("/register", "/login", "/logout", "/me"):
        raise AuthError("Unsupported API endpoint")
    headers = {"Accept": "application/json", "User-Agent": "MKWOM/0.1"}
    if token:
        if not re.fullmatch(r"[a-f0-9]{64}", token):
            raise AuthError("Invalid stored account token")
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(api_base(channel) + path,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method="POST" if body is not None or path == "/logout" else "GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
            if response.status != 200:
                raise AuthError("Unexpected account server response")
            payload = response.read(16 * 1024 + 1)
            if len(payload) > 16 * 1024:
                raise AuthError("Account response too large")
            return json.loads(payload)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise AuthError("Incorrect login or expired session") from None
        if exc.code == 409:
            raise AuthError("Username already registered") from None
        if exc.code == 429:
            raise AuthError("Too many attempts; try again later") from None
        raise AuthError("Account server error (" + str(exc.code) + ")") from None
    except urllib.error.URLError:
        raise AuthError("Could not reach the account server securely") from None


def token() -> str | None:
    return keyring.get_password(SERVICE, USERNAME_KEY)


def authenticate(username: str, password: str, register: bool = False,
                 channel: str = "pre-beta") -> dict:
    if not username.strip() or not password:
        raise AuthError("Username and password are required")
    response = call("/register" if register else "/login",
                    {"username": username.strip(), "password": password}, channel=channel)
    access_token = response.get("access_token")
    if not isinstance(access_token, str) or not re.fullmatch(r"[a-f0-9]{64}", access_token):
        raise AuthError("Server did not return a valid session")
    keyring.set_password(SERVICE, USERNAME_KEY, access_token)
    return call("/me", token=access_token, channel=channel)


def current_user(channel: str = "pre-beta") -> dict | None:
    saved = token()
    return call("/me", token=saved, channel=channel) if saved else None


def channel_scores(channel: str) -> dict:
    """Authenticated score history for exactly the selected online channel."""
    if channel not in ("beta", "release"):
        raise AuthError("Scores are available separately for Beta and Release")
    saved = token()
    if not saved:
        raise AuthError("Log in to MKWOM to view your scores")
    if not re.fullmatch(r"[a-f0-9]{64}", saved):
        raise AuthError("Invalid stored account token")
    request = urllib.request.Request(
        api_base(channel) + "/scores?channel=" + channel,
        headers={"Accept": "application/json", "Authorization": "Bearer " + saved,
                 "User-Agent": "MKWOM/0.1"},
        method="GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
            if response.status != 200:
                raise AuthError("Score server returned an unexpected response")
            data = response.read(16 * 1024 + 1)
            if len(data) > 16 * 1024:
                raise AuthError("Score history response too large")
            payload = json.loads(data)
            if payload.get("channel") != channel:
                raise AuthError("Score history channel mismatch")
            return payload
    except urllib.error.HTTPError as exc:
        raise AuthError("Could not read channel scores (" + str(exc.code) + ")") from None
    except urllib.error.URLError:
        raise AuthError("Could not reach the score server securely") from None


def logout(channel: str = "pre-beta") -> None:
    saved = token()
    if saved:
        try:
            call("/logout", token=saved, channel=channel)
        finally:
            keyring.delete_password(SERVICE, USERNAME_KEY)
