"""Semantic Versioning for immutable MKWOM Beta and stable GitHub releases."""
import re

STABLE = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
BETA = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-beta\.([1-9][0-9]*)")
LEGACY_BETA = re.compile(r"beta-[0-9]+-[a-f0-9]{12}")


def parsed_stable(tag: str):
    m = STABLE.fullmatch(tag)
    return tuple(map(int, m.groups())) if m else None


def parsed_beta(tag: str):
    m = BETA.fullmatch(tag)
    return tuple(map(int, m.groups())) if m else None


def next_stable(releases: list[dict]) -> str:
    """A new train starts only after the previous stable version is published."""
    versions = [v for r in releases
                if not r.get("isDraft") and not r.get("isPrerelease")
                if (v := parsed_stable(r.get("tagName", ""))) is not None]
    major, minor, patch = max(versions, default=(0, 1, 0))
    return f"v{major}.{minor}.{patch + 1}"


def next_beta(releases: list[dict]) -> str:
    base = next_stable(releases)
    numbers = [parsed_beta(r.get("tagName", ""))[3] for r in releases
               if parsed_beta(r.get("tagName", "")) is not None
               and r.get("tagName", "").startswith(base + "-beta.")]
    return f"{base}-beta.{max(numbers, default=0) + 1}"


def stable_for_beta(tag: str) -> str | None:
    beta = parsed_beta(tag)
    if beta is None:
        return None
    return f"v{beta[0]}.{beta[1]}.{beta[2]}"
