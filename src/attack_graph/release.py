"""Download of the pinned MITRE ATT&CK Enterprise release."""

import hashlib
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Fetch = Callable[[str], bytes]


class ReleaseError(Exception):
    """The release could not be downloaded or failed its integrity check."""


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str

    @property
    def filename(self) -> str:
        return f"enterprise-attack-{self.version}.json"


# Pinned to one tagged release so results are reproducible. The checksum
# guards against a corrupted or tampered download.
PINNED = Release(
    version="20.1",
    url="https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
        "enterprise-attack/enterprise-attack-20.1.json",
    sha256="539a843a7b53ed9749740b2123dddae3726b1a4831841c32aca740b011b910b5",
)


def http_fetch(url: str) -> bytes:
    # callers pass the pinned https URL, so file: and custom schemes cannot reach here.
    with urllib.request.urlopen(url, timeout=60) as response:  # nosec B310
        return response.read()


def ensure_downloaded(release: Release, data_dir: Path, fetch: Fetch = http_fetch) -> Path:
    """Return the local copy of the release, downloading it only if missing."""
    target = data_dir / release.filename
    if target.exists():
        return target
    try:
        body = fetch(release.url)
    except OSError as exc:
        raise ReleaseError(f"Cannot download {release.url}: {exc}") from exc
    if hashlib.sha256(body).hexdigest() != release.sha256:
        raise ReleaseError(f"Checksum mismatch for {release.url}; refusing to use it")
    write_atomically(target, body)
    return target


def write_atomically(target: Path, content: bytes) -> None:
    # Write-then-rename so an interrupted run never leaves a half-written file.
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(content)
    os.replace(partial, target)
