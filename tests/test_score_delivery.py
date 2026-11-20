"""Exercise safe retries and per-channel delivery to the real SQLite account API."""
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from server import accounts
from tools import score_delivery


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "DB_PATH", tmp_path / "accounts.sqlite3")
    monkeypatch.setenv("MKWOM_SCORE_BETA_KEY", "ac" * 32)
    monkeypatch.setenv("MKWOM_SCORE_RELEASE_KEY", "bd" * 32)
    testclient = TestClient(accounts.app)
    payload = testclient.post("/register", json={
        "username": "ScoreDeliveryUser", "password": "strong-unique-password-123"
    }).json()
    uid = testclient.get("/me", headers={
        "Authorization": "Bearer " + payload["access_token"]
    }).json()["id"]
    outbox = tmp_path / "server" / "score-outbox"
    outbox.mkdir(parents=True)

    def request(request, timeout=None):
        from urllib.parse import urlsplit
        path = urlsplit(request.full_url).path
        result = testclient.post(path, content=request.data,
                                 headers=dict(request.header_items()))
        class FakeResponse:
            status = result.status_code
            def read(self, amount=1024):
                return result.content[:amount]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        return FakeResponse()
    monkeypatch.setattr(score_delivery.urllib.request, "urlopen", request)
    return testclient, uid, outbox, payload["access_token"]


def event(outbox, race, channel, uid, points):
    path = outbox / (race + ".json")
    path.write_text(json.dumps({"race_id": race, "channel": channel,
                                "players": [{"account_id": uid, "position": 1, "points": points}]}))
    return path


def test_delivery_only_deletes_after_ack_and_keeps_scores_per_channel(setup):
    client, uid, outbox, token = setup
    beta_path = event(outbox, "race-score-1001", "beta", uid, 20)
    assert score_delivery.deliver_one(beta_path, "beta", "http://127.0.0.1:9081", "ac" * 32)
    assert not beta_path.exists()
    release_path = event(outbox, "race-score-1002", "release", uid, 10)
    assert score_delivery.deliver_one(release_path, "release", "http://127.0.0.1:9081", "ac" * 32) is False
    assert release_path.exists()
    assert score_delivery.deliver_one(release_path, "release", "http://127.0.0.1:9081", "bd" * 32)
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/scores?channel=beta", headers=headers).json()["total_points"] == 20
    assert client.get("/scores?channel=release", headers=headers).json()["total_points"] == 10


def test_failed_delivery_is_retained_for_retry(setup, monkeypatch):
    client, uid, outbox, token = setup
    path = event(outbox, "race-score-1003", "beta", uid, 30)
    original = score_delivery.urllib.request.urlopen
    def offline(req, timeout=None):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(score_delivery.urllib.request, "urlopen", offline)
    assert not score_delivery.deliver_one(path, "beta", "http://127.0.0.1:9081", "ac" * 32)
    assert path.exists()
    monkeypatch.setattr(score_delivery.urllib.request, "urlopen", original)
    assert score_delivery.deliver_one(path, "beta", "http://127.0.0.1:9081", "ac" * 32)
    # An identical retry after successful ledger commit never double counts.
    event(outbox, "race-score-1003", "beta", uid, 30)
    assert score_delivery.deliver_pending(outbox, "beta", "http://127.0.0.1:9081", "ac" * 32) == (1, 0)
    assert client.get("/scores?channel=beta", headers={
        "Authorization": "Bearer " + token
    }).json()["total_points"] == 30


def test_channel_mismatch_and_symlink_fail_closed(setup, tmp_path):
    _, uid, outbox, _ = setup
    path = event(outbox, "race-score-1004", "release", uid, 10)
    with pytest.raises(ValueError):
        score_delivery.deliver_one(path, "beta", "http://127.0.0.1:9081", "ac" * 32)
    assert path.exists()
    link = outbox / "race-score-1005.json"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("Symlink privilege unavailable")
    with pytest.raises(ValueError):
        score_delivery.deliver_one(link, "beta", "http://127.0.0.1:9081", "ac" * 32)
