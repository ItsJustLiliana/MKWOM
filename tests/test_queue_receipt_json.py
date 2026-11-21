import json

import pytest

from tools.candidate_store import parse_queue_receipt


def test_current_queue_receipt():
    raw = '{"format":1,"target":"strato","candidate":"pre-beta-123-abcdef123456"}\n'
    assert parse_queue_receipt(raw)["candidate"] == "pre-beta-123-abcdef123456"


def test_legacy_queue_receipt_with_literal_backslash_n():
    raw = '{"format":1,"target":"strato","candidate":"pre-beta-123-abcdef123456"}' + r"\n"
    assert parse_queue_receipt(raw)["target"] == "strato"


def test_reject_unexpected_trailing_data():
    with pytest.raises(json.JSONDecodeError):
        parse_queue_receipt('{"format":1}garbage')
