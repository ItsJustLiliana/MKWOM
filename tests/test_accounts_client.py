"""Account client never transmits credentials to arbitrary addresses."""
import pytest

from mkwom import accounts_client


@pytest.mark.parametrize("url", ["http://example.com", "https://name:pass@example.com",
                                    "https://example.com/path", "https://example.com?token=a"])
def test_reject_unsafe_account_server(monkeypatch, url):
    monkeypatch.setenv("MKWOM_ACCOUNTS_URL", url)
    with pytest.raises(accounts_client.AuthError):
        accounts_client.api_base()


def test_prebeta_service_has_built_in_https_url(monkeypatch):
    monkeypatch.delenv("MKWOM_ACCOUNTS_URL", raising=False)
    assert accounts_client.api_base("pre-beta") == "https://mkwom-api.liliananuzohra.com"
    assert accounts_client.api_base("release") == "https://mkwom-api.liliananuzohra.com"
    assert accounts_client.api_base("beta") == "https://mkwom-api.liliananuzohra.com"


def test_custom_https_account_url_override(monkeypatch):
    monkeypatch.setenv("MKWOM_ACCOUNTS_URL", "https://accounts.example.com")
    assert accounts_client.api_base("pre-beta") == "https://accounts.example.com"


def test_tokens_stored_in_system_keyring(monkeypatch):
    monkeypatch.setenv("MKWOM_ACCOUNTS_URL", "https://accounts.example.com")
    values = {}
    monkeypatch.setattr(accounts_client.keyring, "set_password",
                        lambda service, name, value: values.update({(service, name): value}))
    monkeypatch.setattr(accounts_client.keyring, "get_password",
                        lambda service, name: values.get((service, name)))
    token = "a" * 64
    seen = []

    def fake_call(path, body=None, token=None, channel="pre-beta"):
        seen.append((path, token, channel))
        return {"access_token": "a" * 64} if path == "/login" else {"id": "1", "username": "tester"}

    monkeypatch.setattr(accounts_client, "call", fake_call)
    result = accounts_client.authenticate("tester", "long-password-123")
    assert result["username"] == "tester"
    assert accounts_client.token() == token
    assert seen == [("/login", None, "pre-beta"), ("/me", token, "pre-beta")]
