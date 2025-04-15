"""Permissions pointer.

Records the registration pointer of the data/use permission scope under which
a run is produced. No authorization document or secret is stored in this
repository; the pointer refers to the data owner's register.
"""

from __future__ import annotations

PERMISSIONS_POINTER = (
    "res://data_permissions_register/P2_TRACE_LAB/scope-v1/"
    "internal_research_use_only/registered-2025-01-10"
)


def permissions_pointer() -> str:
    return PERMISSIONS_POINTER
