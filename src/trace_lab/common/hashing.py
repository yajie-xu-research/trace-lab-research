"""Deterministic hashing helpers.

All hashes are SHA-256 hex digests computed over stable, canonicalized
content. File hashing reads bytes in order; object hashing serializes with a
fixed key order so re-runs produce identical digests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

# Manifest fields that are excluded from the byte-exact result hash because
# they vary with execution context (wall clock, operator, invocation).
NON_DETERMINISTIC_FIELDS = ("utc", "operator", "command", "environment")

# Manifest fields that participate in the result hash.
STABLE_FIELDS = (
    "project",
    "status",
    "config_hash",
    "data_hash",
    "seed",
    "rule_version",
    "results_hash",
)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str | Path) -> str:
    """SHA-256 of the raw bytes of a file."""
    with open(path, "rb") as fh:
        return sha256_hex(fh.read())


def hash_text(text: str) -> str:
    return sha256_hex(text.encode("utf-8"))


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _canonicalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return value


def hash_object(value: Any) -> str:
    """Stable hash of a JSON-serializable object (key order independent)."""
    canonical = _canonicalize(value)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256_hex(payload.encode("utf-8"))


def hash_files(files: Iterable[str | Path]) -> str:
    """Ordered concatenation hash of a list of files.

    Only the file *name* (not its location) joins the digest, so a run
    reproduced in a different directory hashes identically.
    """
    digest = hashlib.sha256()
    for path in files:
        digest.update(Path(path).name.encode("utf-8"))
        digest.update(b"\x00")
        with open(path, "rb") as fh:
            digest.update(fh.read())
        digest.update(b"\x00")
    return digest.hexdigest()
