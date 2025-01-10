"""Run manifest construction and the deterministic result hash.

The result hash covers only deterministic fields: project, status, config
hash, data hash, seed, rule version, and the results file hash. utc,
operator, command, and environment are recorded but excluded from the hash,
so re-running the same command with the same inputs yields the same result
hash regardless of when or by whom it was run.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .hashing import hash_object, hash_file
from .run_id import (
    RUN_STATUS_INTERNAL,
    RUN_STATUSES,
    logical_utc,
    run_id_for,
)
from .permissions import permissions_pointer


def current_commit() -> str:
    """Return the repository HEAD hash, or "unknown" outside a git tree."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    return "unknown"


def result_hash(manifest_values: dict[str, Any]) -> str:
    """Deterministic hash over the stable manifest fields."""
    rule_version = manifest_values.get("rule_version") or manifest_values.get(
        "model_or_rule_version")
    subset = {
        "project": manifest_values.get("project"),
        "status": manifest_values.get("status"),
        "config_hash": manifest_values.get("config_hash"),
        "data_hash": manifest_values.get("data_hash"),
        "seed": manifest_values.get("seed"),
        "rule_version": rule_version,
        "results_hash": manifest_values.get("results_hash"),
    }
    return hash_object(subset)


def build_manifest(
    *,
    project: str,
    command: str,
    status: str = RUN_STATUS_INTERNAL,
    config_hash: str = "",
    data_hash: str = "",
    seed: str = "",
    rule_version: str = "",
    results_hash: str = "",
    operator: str = "trace-lab-maintainer",
    commit: str = "",
    environment: str = "",
    input_rows: int = 0,
    excluded_rows: int = 0,
    known_issues: list[str] | None = None,
    permissions: str | None = None,
) -> dict[str, Any]:
    if status not in RUN_STATUSES:
        raise ValueError(f"invalid run status: {status}")
    if not commit:
        commit = current_commit()
    manifest: dict[str, Any] = {
        "run_id": run_id_for(project, command),
        "utc": logical_utc(command),
        "project": project,
        "status": status,
        "commit": commit,
        "config_hash": config_hash,
        "data_hash": data_hash,
        "permissions": permissions or permissions_pointer(),
        "operator": operator,
        "input_rows": input_rows,
        "excluded_rows": excluded_rows,
        "model_or_rule_version": rule_version,
        "command": command,
        "environment": environment,
        "seed": seed,
        "known_issues": known_issues or [],
        "results_hash": results_hash,
    }
    manifest["result_hash"] = result_hash(manifest)
    return manifest


def manifest_for_command(
    command: str,
    *,
    config_hash: str = "",
    data_hash: str = "",
    seed: str = "",
    rule_version: str = "",
    results_hash: str = "",
    input_rows: int = 0,
    excluded_rows: int = 0,
    known_issues: list[str] | None = None,
) -> dict[str, Any]:
    from .. import PROJECT_ID

    return build_manifest(
        project=PROJECT_ID,
        command=command,
        config_hash=config_hash,
        data_hash=data_hash,
        seed=seed,
        rule_version=rule_version,
        results_hash=results_hash,
        input_rows=input_rows,
        excluded_rows=excluded_rows,
        known_issues=known_issues,
    )


def hash_results_files(files: list[str | Path]) -> str:
    """Ordered hash over a list of result files."""
    from .hashing import hash_files

    return hash_files(files)
