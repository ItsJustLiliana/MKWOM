"""Pre-beta artifacts are private and promotion validates the STRATO queue receipt."""
import json
from pathlib import Path
import subprocess

import pytest

from tools import candidate_store


def test_prebeta_release_cleanup_never_includes_beta_or_release():
    releases = [{"tagName": x} for x in (
        "pre-beta-44914018122-aac6505faf32",
        "pre-beta-44911060811-68fd9005704e",
        "beta-v0.1.1-beta.1",
        "v0.1.1",
        "channel-beta",
        "channel-release",
        "pre-beta-manual",
    )]
    assert candidate_store.legacy_public_prebeta(releases) == [
        "pre-beta-44911060811-68fd9005704e",
        "pre-beta-44914018122-aac6505faf32",
    ]


def test_latest_queued_candidate_only_uses_successful_main_branch(monkeypatch):
    calls = []
    def check_output(args, text):
        calls.append(args)
        return json.dumps([
            {"databaseId": 12, "headSha": "f" * 40, "conclusion": "failure",
             "createdAt": "2026-11-21T15:00:00Z"},
            {"databaseId": 11, "headSha": "a" * 40, "conclusion": "success",
             "createdAt": "2026-11-21T14:00:00Z"},
        ])
    monkeypatch.setattr(candidate_store.subprocess, "check_output", check_output)
    assert candidate_store.latest_queued_candidate() == "pre-beta-11-aaaaaaaaaaaa"
    assert "--branch" in calls[0] and "main" in calls[0]


def test_private_candidate_is_verified_before_beta_promotion(monkeypatch, tmp_path):
    candidate = "pre-beta-42-" + "a" * 12
    run = {"databaseId": 42, "headSha": "a" * 40, "headBranch": "main",
           "event": "push", "conclusion": "success",
           "jobs": [{"name": "Queue tested build on STRATO (no activation)", "conclusion": "success"}]}
    downloads = []
    def check_output(args, text):
        return json.dumps(run)
    def run_artifacts(args, check):
        downloads.append(args)
        dest = Path(args[args.index("--dir") + 1])
        if "candidate-bundle" in args:
            (dest / "build-info.json").write_text(json.dumps({"source_sha": "a" * 40}))
        else:
            (dest / "queued-strato.json").write_text(json.dumps({
                "format": 1, "target": "strato", "candidate": candidate}))
    monkeypatch.setattr(candidate_store.subprocess, "check_output", check_output)
    monkeypatch.setattr(candidate_store.subprocess, "run", run_artifacts)
    candidate_store.download_queued_candidate(candidate, tmp_path)
    assert len(downloads) == 2
    assert "candidate-bundle" in downloads[0]
    assert "strato-queue-receipt" in downloads[1]


def test_invalid_strato_queue_receipt_fails_closed(monkeypatch, tmp_path):
    candidate = "pre-beta-42-" + "a" * 12
    run = {"databaseId": 42, "headSha": "a" * 40, "headBranch": "main",
           "event": "push", "conclusion": "success",
           "jobs": [{"name": "Queue tested build on STRATO (no activation)", "conclusion": "success"}]}
    monkeypatch.setattr(candidate_store.subprocess, "check_output",
                        lambda args, text: json.dumps(run))
    def download(args, check):
        dest = Path(args[args.index("--dir") + 1])
        if "candidate-bundle" in args:
            (dest / "build-info.json").write_text(json.dumps({"source_sha": "a" * 40}))
        else:
            (dest / "queued-strato.json").write_text(json.dumps({
                "format": 1, "target": "strato", "candidate": "pre-beta-999-" + "b" * 12}))
    monkeypatch.setattr(candidate_store.subprocess, "run", download)
    with pytest.raises(ValueError, match="STRATO queue acceptance"):
        candidate_store.download_queued_candidate(candidate, tmp_path)


def test_failed_run_cannot_be_promoted(monkeypatch, tmp_path):
    run = {"databaseId": 42, "headSha": "a" * 40, "headBranch": "main",
           "event": "push", "conclusion": "failure", "jobs": []}
    monkeypatch.setattr(candidate_store.subprocess, "check_output",
                        lambda args, text: json.dumps(run))
    with pytest.raises(ValueError, match="successful main-branch"):
        candidate_store.download_queued_candidate("pre-beta-42-" + "a" * 12, tmp_path)


def test_cleanup_cli_only_deletes_strictly_matching_legacy_release_tags(monkeypatch):
    from tools import cleanup_prebeta_releases
    releases = [{"tagName": x} for x in
                ("pre-beta-42-" + "a" * 12, "beta-v0.1.0-beta.1", "v0.1.0")]
    called = []
    monkeypatch.setattr(cleanup_prebeta_releases.subprocess, "check_output",
                        lambda args, text: json.dumps(releases))
    monkeypatch.setattr(cleanup_prebeta_releases.subprocess, "run",
                        lambda args, check: called.append(args))
    cleanup_prebeta_releases.main()
    assert called == [["gh", "release", "delete", "pre-beta-42-" + "a" * 12,
                       "--yes", "--cleanup-tag"]]
