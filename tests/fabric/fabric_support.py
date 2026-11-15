"""Helpers shared by the Fabric tests: failure messages without secrets, exit checks, reports."""

from __future__ import annotations

import json
from subprocess import CompletedProcess

# A failure message may be read in a CI log: nothing that looks like a secret, a token or a URL.
_SECRET_MARKERS = ("password", "private key", "begin ", "x-agent-token", "://")


def redacted(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in _SECRET_MARKERS):
            kept.append("[redacted]")
        else:
            kept.append(line)
    return "\n".join(kept[-40:])


def assert_ok(result: CompletedProcess[str], step: str) -> None:
    assert result.returncode == 0, (
        f"{step} failed with exit {result.returncode}\n"
        f"{redacted(result.stdout)}\n{redacted(result.stderr)}"
    )


def report_line(result: CompletedProcess[str], marker: str) -> dict[str, object]:
    """The last stdout line that starts with `marker` followed by a space, as a JSON object."""
    prefix = f"{marker} "
    for line in reversed(result.stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith(prefix):
            payload = json.loads(stripped.removeprefix(prefix))
            if isinstance(payload, dict):
                return payload
    raise AssertionError(
        f"no {marker} line\n{redacted(result.stdout)}\n{redacted(result.stderr)}"
    )
