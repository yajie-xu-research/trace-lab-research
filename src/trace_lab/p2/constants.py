"""Frozen constants for the TRACE-LAB method.

The category enum, decision codes, and reason codes are part of the frozen
data contract (rule_version 1.0, freeze 2025-01-28). Schema change categories
are the operational vocabulary of the change register and map onto defect
categories only inside the candidate scorer.
"""

from __future__ import annotations

CATEGORIES = (
    "UNIT_CHANGE",
    "INTERFACE_MAPPING_ERROR",
    "FIELD_SEMANTIC_CHANGE",
    "EXTRACTION_FAILURE",
    "TRUE_BUSINESS_CHANGE",
    "UNKNOWN",
)

CHANGE_CATEGORIES = (
    "UNIT_REDEFINITION",
    "INTERFACE_REMAP",
    "SEMANTIC_REDEFINITION",
    "EXTRACTION_PIPELINE_CHANGE",
    "BUSINESS_CHANGE",
    "NORMAL_CHANGE",
)

# Mapping from operational change category to the defect category a triage
# candidate would point at.
CHANGE_CATEGORY_TO_DEFECT_CATEGORY = {
    "UNIT_REDEFINITION": "UNIT_CHANGE",
    "INTERFACE_REMAP": "INTERFACE_MAPPING_ERROR",
    "SEMANTIC_REDEFINITION": "FIELD_SEMANTIC_CHANGE",
    "EXTRACTION_PIPELINE_CHANGE": "EXTRACTION_FAILURE",
    "BUSINESS_CHANGE": "TRUE_BUSINESS_CHANGE",
    "NORMAL_CHANGE": "TRUE_BUSINESS_CHANGE",
}

DECISION_TRIAGE = "TRIAGE"
DECISION_ABSTAIN = "ABSTAIN"
DECISIONS = (DECISION_TRIAGE, DECISION_ABSTAIN)

REASON_AMBIGUOUS_CANDIDATES = "AMBIGUOUS_CANDIDATES"
REASON_LINEAGE_UNRESOLVED = "LINEAGE_UNRESOLVED"
REASON_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
REASONS = (
    REASON_AMBIGUOUS_CANDIDATES,
    REASON_LINEAGE_UNRESOLVED,
    REASON_INSUFFICIENT_EVIDENCE,
)

SCHEMA_V1 = "SCHEMA_V1"
SCHEMA_V2 = "SCHEMA_V2"
SCHEMA_VERSIONS = (SCHEMA_V1, SCHEMA_V2)
SCHEMA_VERSION_BOUNDARY = "2025-06-01T05:00:00Z"

ANOMALY_RULES = (
    "FORMAT_VIOLATION",
    "RANGE_VIOLATION",
    "UNIT_DEVIATION",
    "MISSING_RATE_SHIFT",
    "CHANGE_POINT",
)

BASELINE_IDS = (
    "B0_SINGLE_FIELD_RULES",
    "B1_NO_LINEAGE_DETECTION",
    "B2_CHANGE_POINT_ONLY",
    "B3_SITE_MAPPING_TABLE",
)

# Data files the triage step is permitted to read. Ground-truth files
# (defect tickets, perturbation plan, normal controls) are NOT in this list;
# the leakage test verifies outputs are byte-identical without them.
TRIAGE_INPUT_FILES = (
    "lineage_nodes.csv",
    "lineage_edges.csv",
    "schema_changes.csv",
    "field_profiles.csv",
    "field_observations.csv",
)

GROUND_TRUTH_FILES = (
    "defect_tickets.csv",
    "perturbation_library.json",
    "normal_control_index.csv",
)
