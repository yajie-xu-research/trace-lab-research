"""Deterministic logical timestamps and run identifiers.

Historical runs are curated artifacts. Their UTC stamps and run ids are
logical constants fixed per project so that every re-run of
the same inputs produces the same manifest fields. Wall-clock values never
enter run artifacts.
"""

from __future__ import annotations

# Logical execution timestamps (fixed per project).
LOGICAL_UTC = {
    "generate-synthetic": "2026-06-27T08:00:00Z",
    "validate": "2026-06-27T08:10:00Z",
    "p2_triage": "2026-06-28T09:00:00Z",
    "p2_evaluate": "2026-06-28T09:15:00Z",
    "manifest_inspect": "2026-06-28T09:30:00Z",
}

# Run status. Historical runs carry INTERNAL_RESEARCH; EXTERNAL_VALIDATION
# exists for future runs executed by an independent party.
RUN_STATUS_INTERNAL = "INTERNAL_RESEARCH"
RUN_STATUS_EXTERNAL = "EXTERNAL_VALIDATION"
RUN_STATUSES = (RUN_STATUS_INTERNAL, RUN_STATUS_EXTERNAL)


def logical_utc(command: str) -> str:
    if command not in LOGICAL_UTC:
        raise ValueError(f"unknown command for logical utc: {command}")
    return LOGICAL_UTC[command]


def run_id_for(project: str, command: str) -> str:
    stamp = LOGICAL_UTC[command].replace("-", "").replace(":", "").replace("Z", "Z")
    return f"run-{project.lower().replace('_', '-')}-{command.replace('_', '-')}-{stamp}"
