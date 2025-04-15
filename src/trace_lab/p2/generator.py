"""Synthetic data generator for TRACE-LAB.

Seed 20250110. Deterministic: the same seed always reproduces byte-identical
tables. Generates the five metadata tables plus the observation stream, the
controlled perturbation plan, and the negative-control index.

Injection model (frozen, see research/decisions/0003):
- Each defect-causing schema change produces exactly one controlled
  perturbation: a 24-day window starting 4 days after the change's effective
  time. Defect tickets are paper records spread across that window.
- Each perturbation injects exactly one signature (unit switch, mapping
  garble, semantic shift, extraction gap) without touching other events.
- Anomaly detection windows anchor on the observation window start; candidate
  changes must be effective within (start - 25 days, start].

Ground truth (defect tickets, perturbation plan, normal controls) is written
as separate files; the triage pipeline never reads them.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .perturbations import Perturbation, apply_perturbation, apply_noise

SEED = 20250110
OBS_START = datetime(2025, 2, 1, tzinfo=timezone.utc)
OBS_END = datetime(2026, 6, 27, 8, 0, tzinfo=timezone.utc)
SCHEMA_BOUNDARY = datetime(2025, 6, 1, 5, 0, tzinfo=timezone.utc)
PLAN_GENERATED_AT = "2026-06-27T08:00:00Z"
PERT_ONSET_DAYS = 4.0
PERT_DAYS = 24.0
PERT_SHORT_DAYS = 10.0

NODE_SPECS = [
    # node_id, system, field_name, semantic_definition, unit, datatype,
    # schema_version, valid_from, valid_to ("" = open)
    ("N001", "ANALYZER", "analyzer_raw_result", "raw measured value from the analyzer", "mg/dL", "numeric", "SCHEMA_V1", "2025-01-10T00:00:00Z", ""),
    ("N002", "ETL", "etl_result", "parsed result value in the extraction layer", "mg/dL", "numeric", "SCHEMA_V1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N003", "LIS", "lis_result_value", "stored result value in the LIS", "mg/dL", "numeric", "SCHEMA_V1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N004", "INTERFACE", "iface_result_value", "result value on the outbound interface", "mg/dL", "numeric", "SCHEMA_V1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N005", "REPORT", "report_result_value", "result value rendered on the report", "mg/dL", "numeric", "SCHEMA_V1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N006", "ANALYZER", "analyzer_result_unit", "unit of the analyzer result", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", ""),
    ("N007", "ETL", "etl_unit", "unit label in the extraction layer", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N008", "LIS", "lis_result_unit", "unit label stored in the LIS", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N009", "REPORT", "report_result_unit", "unit label rendered on the report", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N010", "LIS", "lis_test_code", "test code in the LIS", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", ""),
    ("N011", "INTERFACE", "iface_test_code", "test code on the outbound interface", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N012", "REPORT", "report_test_code", "test code rendered on the report", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N013", "LIS", "lis_ref_range", "reference range text in the LIS", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", ""),
    ("N014", "REPORT", "report_ref_range", "reference range rendered on the report", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", ""),
    ("N015", "REPORT", "report_abnormal_flag", "abnormal flag computed for the report", "n/a", "enum", "SCHEMA_V1", "2025-01-10T00:00:00Z", ""),
    ("N016", "ETL", "etl_result_v2", "parsed result value in the extraction layer (v2 pipeline)", "mg/dL", "numeric", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N017", "LIS", "lis_result_value_v2", "stored result value in the LIS (v2)", "mg/dL", "numeric", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N018", "INTERFACE", "iface_result_value_v2", "result value on the outbound interface (v2)", "mg/dL", "numeric", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N019", "REPORT", "report_result_value_v2", "result value rendered on the report (v2)", "mg/dL", "numeric", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N020", "ETL", "etl_unit_v2", "unit label in the extraction layer (v2)", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N021", "LIS", "lis_result_unit_v2", "unit label stored in the LIS (v2)", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N022", "REPORT", "report_result_unit_v2", "unit label rendered on the report (v2)", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N023", "INTERFACE", "iface_test_code_v2", "test code on the outbound interface (v2)", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N024", "REPORT", "report_test_code_v2", "test code rendered on the report (v2)", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N025", "ETL", "etl_specimen_code", "specimen code in the extraction layer", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N026", "LIS", "lis_specimen_code", "specimen code stored in the LIS", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N027", "REPORT", "report_specimen_code", "specimen code rendered on the report", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N028", "REPORT", "report_reagent_lot", "reagent lot rendered on the report", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N029", "ETL", "etl_reagent_lot", "reagent lot in the extraction layer", "n/a", "string", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
    ("N030", "LIS", "lis_accession_code", "accession code in the LIS", "n/a", "string", "SCHEMA_V1", "2025-01-10T00:00:00Z", ""),
    ("N031", "LIS", "lis_collection_datetime", "collection timestamp in the LIS", "n/a", "datetime", "SCHEMA_V1", "2025-01-10T00:00:00Z", ""),
    ("N032", "REPORT", "report_collection_datetime", "collection timestamp rendered on the report", "n/a", "datetime", "SCHEMA_V2", "2025-06-01T05:00:00Z", ""),
]

EDGE_SPECS = [
    # from, to, transform_id, rule_version, valid_from, valid_to
    ("N001", "N002", "T_PARSE_RESULT", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N002", "N003", "T_STORE_RESULT", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N003", "N004", "T_IFACE_RESULT", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N004", "N005", "T_RENDER_RESULT", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N006", "N007", "T_PARSE_UNIT", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N007", "N008", "T_STORE_UNIT", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N008", "N009", "T_RENDER_UNIT", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N010", "N011", "T_IFACE_TESTCODE", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N011", "N012", "T_RENDER_TESTCODE", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N005", "N015", "T_FLAG_COMPUTE", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N014", "N015", "T_FLAG_REF", "r1", "2025-01-10T00:00:00Z", ""),
    ("N007", "N002", "T_RESULT_UNIT_CTX", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N008", "N003", "T_RESULT_UNIT_CTX", "r1", "2025-01-10T00:00:00Z", "2025-06-01T05:00:00Z"),
    ("N013", "N014", "T_REF_RANGE", "r1", "2025-01-10T00:00:00Z", ""),
    ("N030", "N031", "T_ACCESSION_DT", "r1", "2025-01-10T00:00:00Z", ""),
    ("N006", "N001", "T_RAW_UNIT_CTX", "r1", "2025-01-10T00:00:00Z", ""),
    ("N010", "N013", "T_REF_LOOKUP", "r1", "2025-01-10T00:00:00Z", ""),
    ("N001", "N016", "T_PARSE_RESULT", "r2", "2025-06-01T05:00:00Z", ""),
    ("N016", "N017", "T_STORE_RESULT", "r2", "2025-06-01T05:00:00Z", ""),
    ("N017", "N018", "T_IFACE_RESULT", "r2", "2025-06-01T05:00:00Z", ""),
    ("N018", "N019", "T_RENDER_RESULT", "r2", "2025-06-01T05:00:00Z", ""),
    ("N006", "N020", "T_PARSE_UNIT", "r2", "2025-06-01T05:00:00Z", ""),
    ("N020", "N021", "T_STORE_UNIT", "r2", "2025-06-01T05:00:00Z", ""),
    ("N021", "N022", "T_RENDER_UNIT", "r2", "2025-06-01T05:00:00Z", ""),
    ("N010", "N023", "T_IFACE_TESTCODE", "r2", "2025-06-01T05:00:00Z", ""),
    ("N023", "N024", "T_RENDER_TESTCODE", "r2", "2025-06-01T05:00:00Z", ""),
    ("N019", "N015", "T_FLAG_COMPUTE", "r2", "2025-06-01T05:00:00Z", ""),
    ("N030", "N025", "T_ACCESSION_SPECIMEN", "r1", "2025-06-01T05:00:00Z", ""),
    ("N025", "N026", "T_STORE_SPECIMEN", "r1", "2025-06-01T05:00:00Z", ""),
    ("N026", "N027", "T_RENDER_SPECIMEN", "r1", "2025-06-01T05:00:00Z", ""),
    ("N030", "N029", "T_ACCESSION_REAGENT", "r1", "2025-06-01T05:00:00Z", "2025-12-31T23:59:59Z"),
    ("N029", "N028", "T_RENDER_REAGENT", "r1", "2025-06-01T05:00:00Z", ""),
    ("N001", "N029", "T_ANALYZER_REAGENT", "r2", "2026-02-01T00:00:00Z", ""),
    ("N020", "N016", "T_RESULT_UNIT_CTX", "r2", "2025-06-01T05:00:00Z", ""),
    ("N021", "N017", "T_RESULT_UNIT_CTX", "r2", "2025-06-01T05:00:00Z", ""),
    ("N031", "N032", "T_RENDER_COLLECTION_DT", "r1", "2025-06-01T05:00:00Z", ""),
    ("N022", "N019", "T_REPORT_UNIT_CTX", "r1", "2025-06-01T05:00:00Z", ""),
    ("N029", "N017", "T_RESULT_LOT_CTX", "r1", "2025-06-01T05:00:00Z", ""),
    ("N023", "N018", "T_IFACE_CODE_CTX", "r1", "2025-06-01T05:00:00Z", ""),
    ("N024", "N027", "T_REPORT_CODE_CTX", "r1", "2025-06-01T05:00:00Z", ""),
]

# Observable nodes and their stream kinds.
OBSERVABLE = {
    "N002": "numeric",
    "N005": "numeric",
    "N009": "unit_label",
    "N010": "test_code",
    "N012": "test_code",
    "N013": "ref_range",
    "N014": "ref_range",
    "N015": "flag",
    "N016": "numeric",
    "N017": "numeric",
    "N019": "numeric",
    "N022": "unit_label",
    "N024": "test_code",
    "N027": "specimen",
    "N028": "reagent_lot",
    "N029": "reagent_lot",
    "N030": "accession",
    "N031": "datetime",
    "N032": "datetime",
}

TEST_CODES = ["TSH", "GLUC", "CREA", "ALT", "AST", "HGB", "WBC", "PLT"]
WRONG_UNITS = ["ug/dL", "ng/mL", "U/L", "x10E9/L"]

ADJUDICATORS = ["QUALITY_LEAD_01", "DATA_PLATFORM_LEAD_01", "QUALITY_LEAD_02"]
CONFIRMERS = ["SYSTEMS_ARCHITECT_01", "INTERFACE_OWNER_01", "ETL_OWNER_01", "SYSTEMS_ARCHITECT_02"]


def _stable_index(frm: str, to: str, width: int) -> int:
    """Deterministic index from stable identifiers.

    Python's built-in ``hash()`` is salted per process, so it must not be
    used to assign data values; a SHA-256 digest of the joined identifiers
    is stable across runs and machines.
    """
    digest = hashlib.sha256(f"{frm}|{to}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % width


def _ts(value: Any) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(dt: datetime, days: float) -> datetime:
    return dt + timedelta(days=days)


class _Build:
    def __init__(self, rng):
        self.rng = rng
        self.changes: list[dict[str, Any]] = []
        self.perturbations: list[Perturbation] = []
        self.tickets: list[dict[str, Any]] = []
        self.controls: list[dict[str, Any]] = []
        self.defect_seq = 0
        self.change_seq = 0
        self.pert_seq = 0
        self.control_seq = 0

    def add_change(self, effective: datetime, category: str, affected: list[str]) -> str:
        self.change_seq += 1
        change_id = f"C{self.change_seq:04d}"
        self.changes.append({
            "change_id": change_id,
            "affected_nodes": ";".join(affected),
            "change_category": category,
            "submitted_at": _fmt(_day(effective, -float(self.rng.randint(5, 10)))),
            "approved_at": _fmt(_day(effective, -float(self.rng.randint(1, 4)))),
            "effective_at": _fmt(effective),
            "version": "SCHEMA_V1" if effective < SCHEMA_BOUNDARY else "SCHEMA_V2",
            "ticket_index": "",
        })
        return change_id

    def add_tickets(self, change_id: str, effective: datetime, node: str,
                    true_category: str, symptom: str, n_tickets: int) -> None:
        """Paper tickets spread across the perturbation window."""
        if n_tickets <= 0:
            return
        basis_map = {
            "UNIT_CHANGE": "unit label differs from profile across the affected window",
            "INTERFACE_MAPPING_ERROR": "garbled and out-of-range values traced to interface remap",
            "FIELD_SEMANTIC_CHANGE": "distribution shift without format or unit change",
            "EXTRACTION_FAILURE": "missing burst aligned with extraction pipeline change",
            "TRUE_BUSINESS_CHANGE": "distribution shift confirmed as intended policy change",
            "UNKNOWN": "no change record and no confirmed mechanism found",
        }
        node_schema = "SCHEMA_V1" if effective < SCHEMA_BOUNDARY else "SCHEMA_V2"
        for k in range(n_tickets):
            self.defect_seq += 1
            defect_id = f"D{self.defect_seq:04d}"
            detected = _day(effective, PERT_ONSET_DAYS + 3.0 + 6.0 * k + float(self.rng.randint(0, 3)))
            confirmed = _day(detected, float(self.rng.randint(2, 6)))
            self.tickets.append({
                "defect_id": defect_id,
                "detected_at": _fmt(detected),
                "field_version": f"{node}@{node_schema}",
                "symptom": symptom,
                "detection_method": "ROUTINE_AUDIT",
                "confirmed_category": true_category,
                "confirmed_at": _fmt(confirmed),
                "basis": basis_map[true_category],
                "adjudicated_by": ADJUDICATORS[(self.defect_seq - 1) % len(ADJUDICATORS)],
            })

    def make_pert(self, change_id: str, effective: datetime, node: str,
                  true_category: str, kind: str, n_tickets: int,
                  *, wrong_unit: str = "", short: bool = False) -> None:
        start = _day(effective, PERT_ONSET_DAYS)
        days = PERT_SHORT_DAYS if short else PERT_DAYS
        if kind == "UNIT_CHANGE":
            p = Perturbation("", true_category, node, _fmt(start), _fmt(_day(start, days)),
                             change_id, "", true_category, "", False, wrong_unit=wrong_unit)
        elif kind == "INTERFACE":
            p = Perturbation("", true_category, node, _fmt(start), _fmt(_day(start, days)),
                             change_id, "", true_category, "", False,
                             garble_fraction=0.7, out_of_range_fraction=0.5)
        elif kind == "SHIFT":
            p = Perturbation("", true_category, node, _fmt(start), _fmt(_day(start, days)),
                             change_id, "", true_category, "", False, shift_magnitude=2.4)
        elif kind == "MISSING":
            p = Perturbation("", true_category, node, _fmt(start), _fmt(_day(start, days)),
                             change_id, "", true_category, "", False, missing_fraction=1.0)
        elif kind == "UNKNOWN_MISSING":
            p = Perturbation("", "UNKNOWN", node, _fmt(start), _fmt(_day(start, days)),
                             "", "", "UNKNOWN", "", False, missing_fraction=1.0)
        elif kind == "UNKNOWN_GARBLE":
            p = Perturbation("", "UNKNOWN", node, _fmt(start), _fmt(_day(start, days)),
                             "", "", "UNKNOWN", "", False, garble_fraction=0.7)
        else:
            raise ValueError(f"unknown perturbation kind {kind}")
        self.pert_seq += 1
        p.perturbation_id = f"P{self.pert_seq:04d}"
        self.perturbations.append(p)
        self.add_tickets(change_id, effective, node, true_category,
                         self._symptom(kind, true_category), n_tickets)

    @staticmethod
    def _symptom(kind: str, category: str) -> str:
        if kind == "UNIT_CHANGE":
            return "report unit label switched"
        if kind == "INTERFACE":
            return "garbled and out-of-range report values"
        if kind == "SHIFT" and category == "TRUE_BUSINESS_CHANGE":
            return "shifted result distribution with approved policy change"
        if kind == "SHIFT":
            return "shifted result distribution"
        if kind == "MISSING":
            return "burst of missing rows"
        if kind == "UNKNOWN_MISSING":
            return "unexplained missing burst"
        if kind == "UNKNOWN_GARBLE":
            return "unexplained garbled values"
        return "anomaly investigated"

    def add_normal(self, effective: datetime, node: str) -> None:
        self.control_seq += 1
        cid = self.add_change(effective, "NORMAL_CHANGE", [node])
        self.controls.append({
            "control_id": f"NC{self.control_seq:04d}",
            "change_id": cid,
            "node_id": node,
            "window_start": _fmt(effective),
            "window_end": _fmt(_day(effective, 14)),
            "category": "NORMAL_CHANGE",
        })


def generate_synthetic(output_dir: str | Path, seed: int = SEED) -> dict[str, int]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(seed)

    nodes = pd.DataFrame(NODE_SPECS, columns=[
        "node_id", "system", "field_name", "semantic_definition", "unit",
        "datatype", "schema_version", "valid_from", "valid_to",
    ])

    edge_rows = []
    for frm, to, tid, rv, vf, vt in EDGE_SPECS:
        edge_rows.append({
            "from_node": frm, "to_node": to, "transform_id": tid,
            "rule_version": rv, "valid_from": vf, "valid_to": vt,
            "confirmed_by": CONFIRMERS[_stable_index(frm, to, len(CONFIRMERS))],
            "source_file": f"registry/field_lineage_v{rv}.md",
        })
    edges = pd.DataFrame(edge_rows)

    b = _Build(rng)

    # ================= V1 era (2025-02 .. 2025-05) =================
    # 5 changes, 17 tickets. Interface garbles are kept on N005 only in V1 so
    # the V2 numeric result chain (N019) stays free of format pollution.
    t0 = datetime(2025, 2, 14, tzinfo=timezone.utc)
    eff = _day(t0, 0)
    cid = b.add_change(eff, "UNIT_REDEFINITION", ["N008"])
    b.make_pert(cid, eff, "N009", "UNIT_CHANGE", "UNIT_CHANGE", 4, wrong_unit="ug/dL")
    for i in range(3):
        eff = _day(t0, 4 + 24 * i)
        cid = b.add_change(eff, "INTERFACE_REMAP", ["N004"])
        b.make_pert(cid, eff, "N005", "INTERFACE_MAPPING_ERROR", "INTERFACE", 4, short=True)
    eff = _day(t0, 34)
    cid = b.add_change(eff, "EXTRACTION_PIPELINE_CHANGE", ["N002"])
    b.make_pert(cid, eff, "N002", "EXTRACTION_FAILURE", "MISSING", 1)
    # V1 normals after all changes.
    for i, node in enumerate(["N005", "N002", "N009", "N012"]):
        b.add_normal(_day(t0, 80 + 4 * i), node)

    # ================= unit_v2 (N022) =================
    cursor = datetime(2025, 7, 2, tzinfo=timezone.utc)
    for ci in range(9):
        eff = _day(cursor, 0)
        cid = b.add_change(eff, "UNIT_REDEFINITION", ["N021"] if ci % 2 == 0 else ["N022"])
        b.make_pert(cid, eff, "N022", "UNIT_CHANGE", "UNIT_CHANGE", 4,
                    wrong_unit=WRONG_UNITS[ci % len(WRONG_UNITS)])
        b.add_normal(_day(eff, 24), "N022")
        cursor = _day(eff, float(rng.randint(32, 39)))

    # ================= N017 chain (semantic/business on the LIS node) =================
    # 2 semantic + 4 business changes. Business shifts live on N017 so the
    # N019 chain stays semantic-only: adjacent cross-type shifts on one node
    # would otherwise compete in the same detection windows. Business changes
    # are spaced >= 35 days so consecutive 24-day shifts keep a clean baseline
    # gap (a near-zero gap makes the second shift invisible to the detector).
    n017_dates = [
        datetime(2025, 9, 5, tzinfo=timezone.utc),
        datetime(2025, 11, 5, tzinfo=timezone.utc),
        datetime(2026, 1, 20, tzinfo=timezone.utc),
        datetime(2026, 2, 27, tzinfo=timezone.utc),
        datetime(2026, 4, 5, tzinfo=timezone.utc),
        datetime(2026, 5, 12, tzinfo=timezone.utc),
    ]
    for i, eff in enumerate(n017_dates):
        if i < 2:
            cid = b.add_change(eff, "SEMANTIC_REDEFINITION", ["N017"])
            b.make_pert(cid, eff, "N017", "FIELD_SEMANTIC_CHANGE", "SHIFT", 4)
        else:
            cid = b.add_change(eff, "BUSINESS_CHANGE", ["N017"])
            n = 6 if i == len(n017_dates) - 1 else 4
            b.make_pert(cid, eff, "N017", "TRUE_BUSINESS_CHANGE", "SHIFT", n)

    # ================= result_v2a (N019) — semantic-only chain =================
    # 5 changes: SEMANTIC only. The chain carries no business changes and no
    # mapping garble, so every detection window maps to a single kind.
    cursor = datetime(2025, 6, 8, tzinfo=timezone.utc)
    sem_tickets = [4, 4, 4, 4, 2]
    for si in range(5):
        eff = _day(cursor, 0)
        cid = b.add_change(eff, "SEMANTIC_REDEFINITION", ["N019"])
        b.make_pert(cid, eff, "N019", "FIELD_SEMANTIC_CHANGE", "SHIFT", sem_tickets[si])
        cursor = _day(eff, float(rng.randint(32, 40)))

    # ================= result_v2b (N016, extraction) =================
    cursor = datetime(2025, 7, 15, tzinfo=timezone.utc)
    for ci in range(6):
        eff = _day(cursor, 0)
        cid = b.add_change(eff, "EXTRACTION_PIPELINE_CHANGE", ["N016"])
        b.make_pert(cid, eff, "N016", "EXTRACTION_FAILURE", "MISSING", 4)
        b.add_normal(_day(eff, 24), "N016")
        cursor = _day(eff, float(rng.randint(36, 45)))

    # ================= testcode_v2 (N024) — interface mapping =================
    # 4 ambiguous pairs first, then 8 clean changes.
    cursor = datetime(2025, 6, 20, tzinfo=timezone.utc)
    for pair_i in range(4):
        d0 = _day(cursor, 0)
        b.add_change(d0, "INTERFACE_REMAP", ["N023"])            # innocent partner
        c_b = b.add_change(_day(d0, 2), "INTERFACE_REMAP", ["N023"])  # true change
        start = _day(d0, 5)
        p = Perturbation("", "INTERFACE_MAPPING_ERROR", "N024", _fmt(start),
                         _fmt(_day(start, PERT_SHORT_DAYS)), c_b, "",
                         "INTERFACE_MAPPING_ERROR", f"PAIR-{pair_i + 1}", False,
                         garble_fraction=0.7, out_of_range_fraction=0.5)
        b.pert_seq += 1
        p.perturbation_id = f"P{b.pert_seq:04d}"
        b.perturbations.append(p)
        b.add_tickets(c_b, _day(d0, 2), "N024", "INTERFACE_MAPPING_ERROR",
                      "garbled test codes near two interface changes", 1)
        cursor = _day(d0, float(rng.randint(28, 33)))
    for ci in range(8):
        eff = _day(cursor, 0)
        cid = b.add_change(eff, "INTERFACE_REMAP", ["N023"])
        b.make_pert(cid, eff, "N024", "INTERFACE_MAPPING_ERROR", "INTERFACE", 4, short=True)
        b.add_normal(_day(eff, 20), "N024")
        cursor = _day(eff, float(rng.randint(26, 29)))

    # ================= reagent chain (N028) — lineage gap Jan 2026 =================
    # The upstream edge N030->N029 expires 2025-12-31, so these changes are
    # deliberately lineage-broken at detection time (see p2_lineage.yaml).
    for i in range(5):
        eff = _day(datetime(2026, 1, 2, tzinfo=timezone.utc), 5 * i)
        cid = b.add_change(eff, "EXTRACTION_PIPELINE_CHANGE", ["N029"])
        start = _day(eff, PERT_ONSET_DAYS)
        p = Perturbation("", "EXTRACTION_FAILURE", "N028", _fmt(start),
                         _fmt(_day(start, PERT_SHORT_DAYS)), cid, "",
                         "EXTRACTION_FAILURE", "", True, missing_fraction=1.0)
        b.pert_seq += 1
        p.perturbation_id = f"P{b.pert_seq:04d}"
        b.perturbations.append(p)
        b.add_tickets(cid, eff, "N028", "EXTRACTION_FAILURE",
                      "burst of missing rows", 1)

    # ================= quiet chains: UNKNOWN =================
    def quiet_chain(node: str, start: datetime, n: int, spacing: tuple[int, int], kind: str) -> None:
        cursor = _day(start, 0)
        for _ in range(n):
            b.make_pert("", _day(cursor, 0), node, "UNKNOWN", kind, 1, short=True)
            cursor = _day(cursor, float(rng.randint(*spacing)))

    quiet_chain("N027", datetime(2025, 9, 1, tzinfo=timezone.utc), 6, (35, 46), "UNKNOWN_MISSING")
    quiet_chain("N032", datetime(2025, 9, 20, tzinfo=timezone.utc), 6, (35, 46), "UNKNOWN_MISSING")
    quiet_chain("N014", datetime(2025, 10, 5, tzinfo=timezone.utc), 3, (40, 56), "UNKNOWN_GARBLE")
    quiet_chain("N015", datetime(2025, 10, 20, tzinfo=timezone.utc), 3, (40, 56), "UNKNOWN_GARBLE")

    # ================= normal changes on quiet chains =================
    def normal_chain(node: str, start: datetime, n: int, spacing: tuple[int, int]) -> None:
        cursor = _day(start, 0)
        for _ in range(n):
            b.add_normal(_day(cursor, 0), node)
            cursor = _day(cursor, float(rng.randint(*spacing)))

    normal_chain("N027", datetime(2025, 8, 6, tzinfo=timezone.utc), 12, (22, 27))
    normal_chain("N032", datetime(2025, 8, 20, tzinfo=timezone.utc), 10, (26, 33))
    normal_chain("N014", datetime(2025, 9, 5, tzinfo=timezone.utc), 8, (28, 35))
    normal_chain("N015", datetime(2025, 9, 18, tzinfo=timezone.utc), 8, (28, 35))

    changes = pd.DataFrame(b.changes).sort_values(["submitted_at", "change_id"]).reset_index(drop=True)
    tickets_df = pd.DataFrame(b.tickets)
    controls_df = pd.DataFrame(b.controls)

    # ================= observation streams =================
    obs_rows: list[dict[str, Any]] = []
    obs_seq = [0]
    profiles_rows: list[dict[str, Any]] = []
    spec_map = {row["node_id"]: row for _, row in nodes.iterrows()}
    for node_id, kind in sorted(OBSERVABLE.items()):
        spec = spec_map[node_id]
        valid_from = _ts(spec["valid_from"])
        valid_to = _ts(spec["valid_to"]) if spec["valid_to"] else OBS_END
        start = max(valid_from, OBS_START)
        end = min(valid_to, OBS_END)
        unit = "mg/dL" if kind in ("unit_label", "numeric") else "n/a"
        profiles_rows.append({
            "field_name": spec["field_name"],
            "unit": unit,
            "value_range": {"numeric": "0.5-9.5", "unit_label": "set:{mg/dL,ug/dL,ng/mL,U/L}",
                            "test_code": "set:{TSH,GLUC,CREA,ALT,AST,HGB,WBC,PLT}",
                            "ref_range": "freeform", "flag": "set:{N,H,L}",
                            "specimen": "set:{SER,PLA,WHL}", "reagent_lot": "pattern:LOT-\\d{5}",
                            "accession": "pattern:AC-\\d{6}", "datetime": "pattern:ISO-8601"}[kind],
            "missing_rate": 0.02 if kind == "numeric" else 0.01,
            "time_window": "28d",
        })
        base = 2.2
        t = start
        while t < end:
            if t.weekday() == 0:
                t = t.replace(hour=8, minute=0, second=0, microsecond=0)
            else:
                t = t.replace(hour=16, minute=0, second=0, microsecond=0)
            raw, parsed, rep_unit = "", "", ""
            if kind == "numeric":
                val = base + rng.normal(0, 0.25)
                raw = f"{val:.4f}"
                parsed = f"{val:.4f}"
            elif kind == "unit_label":
                raw = "mg/dL"
                rep_unit = "mg/dL"
            elif kind == "test_code":
                raw = TEST_CODES[int(rng.randint(0, len(TEST_CODES)))]
            elif kind == "ref_range":
                raw = "0.45-4.12"
            elif kind == "flag":
                raw = rng.choice(["N"] * 9 + ["H"] + ["L"])
            elif kind == "specimen":
                raw = rng.choice(["SER"] * 7 + ["PLA"] * 2 + ["WHL"])
            elif kind == "reagent_lot":
                raw = f"LOT-{int(rng.randint(10000, 99999)):05d}"
            elif kind == "accession":
                raw = f"AC-{int(rng.randint(100000, 999999)):06d}"
            elif kind == "datetime":
                raw = _fmt(t)
            obs_seq[0] += 1
            obs_rows.append({
                "observation_id": f"OBS{obs_seq[0]:06d}",
                "node_id": node_id,
                "observed_at_utc": _fmt(t),
                "raw_value": raw,
                "parsed_value": parsed,
                "reported_unit": rep_unit,
                "source_system": spec["system"],
                "record_version": f"rv-{int(rng.randint(1, 9))}",
            })
            if t.weekday() == 0:
                t = _day(t, 3.0)
            else:
                t = _day(t, 4.0)
    obs = pd.DataFrame(obs_rows)

    # Apply perturbations chronologically, then sparse background noise.
    for p in sorted(b.perturbations, key=lambda q: (q.window_start, q.perturbation_id)):
        obs = apply_perturbation(obs, p, rng)
    obs = apply_noise(obs, rng, 0.008)

    # ================= write files =================
    nodes.to_csv(out / "lineage_nodes.csv", index=False)
    edges.to_csv(out / "lineage_edges.csv", index=False)
    changes.to_csv(out / "schema_changes.csv", index=False)
    tickets_df.to_csv(out / "defect_tickets.csv", index=False)
    pd.DataFrame(profiles_rows).to_csv(out / "field_profiles.csv", index=False)
    obs.to_csv(out / "field_observations.csv", index=False)

    plan_doc = {
        "generated_at": PLAN_GENERATED_AT,
        "seed": seed,
        "note": (
            "Controlled perturbation plan for held-out evaluation. Each "
            "perturbation injects exactly one signature into the "
            "observation stream over a fixed 24-day window (10-day for "
            "short-lived events). This file is ground truth and is never "
            "read by the triage pipeline."
        ),
        "injection_rules": {
            "UNIT_CHANGE": "reported unit label switched to a wrong unit for 24 days",
            "INTERFACE_MAPPING_ERROR": "70% of raw values garbled and 50% of parsed values pushed out of range for 24 days",
            "FIELD_SEMANTIC_CHANGE": "value distribution shifted +2.4 for 24 days, no format or unit change",
            "EXTRACTION_FAILURE": "all rows dropped for 24 days",
            "TRUE_BUSINESS_CHANGE": "value distribution shifted +2.4 for 24 days with a business change record",
            "UNKNOWN": "missing burst or garbled values with no change record",
        },
        "perturbations": [p.to_dict() for p in sorted(b.perturbations, key=lambda q: (q.window_start, q.perturbation_id))],
    }
    with open(out / "perturbation_library.json", "w", encoding="utf-8") as fh:
        json.dump(plan_doc, fh, indent=2, ensure_ascii=True)
        fh.write("\n")
    controls_df.to_csv(out / "normal_control_index.csv", index=False)

    return {
        "lineage_nodes": len(nodes),
        "lineage_edges": len(edges),
        "schema_changes": len(changes),
        "defect_tickets": len(tickets_df),
        "field_profiles": len(profiles_rows),
        "field_observations": len(obs),
        "perturbations": len(b.perturbations),
        "normal_controls": len(controls_df),
    }
