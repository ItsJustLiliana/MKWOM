"""Regression guards for automatic STRATO queue + manual Beta and Release promotions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def contents(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_push_queues_on_strato_but_never_activates_live_channels():
    workflow = contents(".github/workflows/build.yml")
    assert "branches: [main, pre-beta]" in workflow
    assert "queue-strato:" in workflow
    assert "tools/queue_strato.py" in workflow
    assert "needs: [publish]" in workflow
    assert "uses: ./.github/workflows/deploy.yml" not in workflow
    assert "uses: ./.github/workflows/channel.yml" not in workflow


def test_prebeta_has_no_manual_activation_or_public_channel():
    assert not (ROOT / ".github/workflows/prebeta.yml").exists()
    assert 'channel: pre-beta' not in contents(".github/workflows/promote.yml")
    assert 'if channel not in ("beta", "release")' in contents("tools/activate_channel.py")


def test_beta_and_release_each_have_a_manual_promotion_button():
    workflow = contents(".github/workflows/promote.yml")
    assert "workflow_dispatch:" in workflow
    assert "options: [beta, release]" in workflow
    assert "uses: ./.github/workflows/deploy.yml" in workflow
    assert "channel: beta" in workflow
    assert "channel: release" in workflow
    assert "needs: promote" in workflow


def test_release_only_publishes_approved_beta_without_second_deployment():
    workflow = contents(".github/workflows/release.yml")
    assert "workflow_dispatch:" in workflow
    assert "uses: ./.github/workflows/deploy.yml" not in workflow
    assert "release:\n    types: [published]" not in workflow


def test_deploy_has_no_bypass_button_and_fails_without_configuration():
    workflow = contents(".github/workflows/deploy.yml")
    assert "workflow_dispatch:" not in workflow
    assert "AUTO_DEPLOY" in workflow
    assert "Missing required stage setting" in workflow
    assert "exit 1" in workflow


def test_beta_requires_queued_receipt_and_release_requires_active_beta():
    script = contents("tools/promote.py")
    assert 'required_source = "pre-beta"' in script
    assert 'required_source = "beta"' in script
    assert "download_queued_candidate(candidate, Path(\"dist\"))" in script
    assert "queued-strato.json" in contents("tools/candidate_store.py")
    assert "strato-queue-receipt" in contents(".github/workflows/build.yml")
    assert 'approved.get("tag") != candidate' in script


def test_channel_pointer_carries_immutable_tag():
    script = contents("tools/channel.py")
    assert '"tag": a.tag' in script


def test_only_main_or_prebeta_builds_new_candidates():
    script = contents("tools/release_metadata.py")
    assert '("main", "pre-beta")' in script
    assert 'channel = "pre-beta"' in script


def test_release_deploys_approved_beta_instead_of_unpublished_draft():
    workflow = contents(".github/workflows/promote.yml")
    assert "tag: ${{ needs.promote.outputs.candidate }}" in workflow
    assert "restart_if_unchanged: false" in workflow
    assert "publish-stable:" in workflow
    assert "needs: [promote, deploy-release]" in workflow
    assert "needs: [promote, publish-stable]" in workflow
    assert "needs: [promote, activate-release]" in workflow
    assert "gh release edit \"$RELEASE_TAG\" --latest" in workflow


def test_failed_release_promotion_can_resume_existing_draft_without_duplicate_tag():
    script = contents("tools/promote.py")
    assert 'f.write(f"candidate={candidate}\\n")' in script
    assert '"isDraft,isPrerelease,targetCommitish,body,assets"' in script
    assert "Reusing existing draft or published Release" in script
    assert "refusing overwrite" in script


def test_beta_and_release_do_not_restart_unchanged_server():
    workflow = contents(".github/workflows/promote.yml")
    assert "restart_if_unchanged: true" not in workflow
    assert "restart_if_unchanged: false" in workflow
    deploy = contents("tools/deploy_server.py")
    assert 'if hashlib.sha256(exe.read_bytes()).hexdigest() == metadata["sha256"]:' in deploy
    assert 'print("Server binary unchanged; no restart required.")' in deploy


def test_stable_release_shows_only_player_downloads():
    script = contents("tools/promote.py")
    assert 'release_assets = [Path("dist") / n for n in names if n != raw_exe] if destination == "beta" else []' in script
    assert 'MKWOM-{tag}.exe' in script
    assert 'MKWOM-Patcher-{tag}.exe' not in script
    assert 'MKWOM-Patch-{tag}-windows-x64.zip' in script


def test_release_channel_verifies_public_patch_from_approved_beta():
    workflow = contents(".github/workflows/promote.yml")
    assert "source_tag: ${{ needs.promote.outputs.candidate }}" in workflow
    assert "source_tag:" in contents(".github/workflows/channel.yml")
    activation = contents("tools/activate_channel.py")
    assert 'source_tag = os.environ.get("SOURCE_TAG", "").strip() if channel == "release" else tag' in activation
    assert "stable ZIP differs from approved Beta artifact" in activation
    assert 'args.extend(["--patch-asset", public_asset])' in activation
    channel = contents("tools/channel.py")
    assert "a.patch_asset" in channel


def test_strato_ssh_secrets_have_real_line_endings_in_queue_workflow():
    workflow = contents(".github/workflows/build.yml")
    # printf must interpret a single backslash-n, not print literal \\n bytes into
    # the private key / known_hosts files. Strict host verification stays enabled.
    assert "printf '%s\\n'" in workflow
    assert "printf '%s\\\\n'" not in workflow
    assert "DEPLOY_SSH_KNOWN_HOSTS" in workflow
    assert "tools/queue_strato.py" in workflow
