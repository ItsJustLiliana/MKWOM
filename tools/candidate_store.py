"""Private Actions artifacts backing pre-beta promotion; never public GitHub Releases.

The only public Releases are approved Beta and stable Release. The queue receipt
is uploaded separately *after* verified STRATO staging succeeds.
"""
import json
from pathlib import Path
import re
import subprocess

PATTERN = re.compile(r"pre-beta-([0-9]+)-([a-f0-9]{12})\Z")


def candidate_parts(tag: str) -> tuple[int, str]:
    match = PATTERN.fullmatch(tag)
    if not match:
        raise ValueError("Invalid pre-beta candidate identity")
    return int(match.group(1)), match.group(2)


def latest_queued_candidate() -> str:
    runs = json.loads(subprocess.check_output([
        "gh", "run", "list", "--workflow", "build.yml", "--branch", "main",
        "--event", "push", "--limit", "100",
        "--json", "databaseId,headSha,conclusion,createdAt",
    ], text=True))
    for run in sorted(runs, key=lambda r: r["createdAt"], reverse=True):
        if run.get("conclusion") == "success" and re.fullmatch(r"[a-f0-9]{40}", run.get("headSha", "")):
            return f"pre-beta-{run['databaseId']}-{run['headSha'][:12]}"
    raise ValueError("No successfully staged main-branch pre-beta build in the Actions retention period")


def download_queued_candidate(tag: str, destination: Path) -> None:
    """Verify full successful run and STRATO receipt before any promotion."""
    run_id, short_sha = candidate_parts(tag)
    run = json.loads(subprocess.check_output([
        "gh", "run", "view", str(run_id),
        "--json", "databaseId,headSha,headBranch,event,conclusion,jobs",
    ], text=True))
    if (run.get("databaseId") != run_id or run.get("headBranch") != "main" or
            run.get("event") != "push" or run.get("conclusion") != "success" or
            not re.fullmatch(r"[a-f0-9]{40}", run.get("headSha", "")) or
            run["headSha"][:12] != short_sha):
        raise ValueError("Candidate is not a completed successful main-branch build")
    if not any(job.get("name") == "Queue tested build on STRATO (no activation)" and
               job.get("conclusion") == "success" for job in run.get("jobs", [])):
        raise ValueError("Candidate STRATO staging did not complete successfully")
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gh", "run", "download", str(run_id), "--name", "candidate-bundle",
                    "--dir", str(destination)], check=True)
    receipt_dir = destination / ".queue-receipt"
    receipt_dir.mkdir(exist_ok=True)
    subprocess.run(["gh", "run", "download", str(run_id), "--name", "strato-queue-receipt",
                    "--dir", str(receipt_dir)], check=True)
    receipt = json.loads((receipt_dir / "queued-strato.json").read_text(encoding="utf-8"))
    if receipt != {"format": 1, "target": "strato", "candidate": tag}:
        raise ValueError("Candidate missing matching STRATO queue acceptance receipt")
    info = json.loads((destination / "build-info.json").read_text(encoding="utf-8"))
    if info.get("source_sha") != run["headSha"]:
        raise ValueError("Candidate build metadata does not match Actions commit")


def legacy_public_prebeta(releases: list[dict]) -> list[str]:
    """Never delete Beta/Release/drafts unrelated to internal build candidates."""
    return sorted({item["tagName"] for item in releases
                   if PATTERN.fullmatch(item.get("tagName", ""))})
