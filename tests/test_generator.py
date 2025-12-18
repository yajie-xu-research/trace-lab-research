"""Generator and dataset contract tests: determinism, five-table shapes,
version validity, ticket distribution, and perturbation plan contents."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from trace_lab.p2.constants import CATEGORIES, SCHEMA_VERSION_BOUNDARY
from trace_lab.p2.generator import SEED, generate_synthetic


def _ts(value: str):
    from datetime import datetime, timezone

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def test_generation_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate_synthetic(a, seed=SEED)
    generate_synthetic(b, seed=SEED)
    files = sorted(p.name for p in a.iterdir())
    assert files == sorted(p.name for p in b.iterdir())
    for name in files:
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_lineage_table_shape(lineage_nodes, lineage_edges):
    assert len(lineage_nodes) == 32
    assert len(lineage_edges) == 40
    required = ["node_id", "system", "field_name", "semantic_definition", "unit",
                "datatype", "schema_version", "valid_from", "valid_to"]
    for col in required:
        assert col in lineage_nodes.columns
    for col in ["from_node", "to_node", "transform_id", "rule_version",
                "valid_from", "valid_to", "confirmed_by", "source_file"]:
        assert col in lineage_edges.columns
    assert lineage_nodes["node_id"].is_unique


def test_two_schema_versions_with_boundary(lineage_nodes):
    versions = set(lineage_nodes["schema_version"])
    assert versions == {"SCHEMA_V1", "SCHEMA_V2"}
    boundary = _ts(SCHEMA_VERSION_BOUNDARY)
    v1 = lineage_nodes[lineage_nodes.schema_version == "SCHEMA_V1"]
    v2 = lineage_nodes[lineage_nodes.schema_version == "SCHEMA_V2"]
    for _, row in v1.iterrows():
        assert _ts(row.valid_from) < boundary
    for _, row in v2.iterrows():
        assert _ts(row.valid_from) >= boundary


def test_nodes_and_edges_carry_validity_ranges(lineage_nodes, lineage_edges):
    assert (lineage_nodes["valid_from"] != "").all()
    assert (lineage_edges["valid_from"] != "").all()
    # V1 result chain closes at the boundary; V2 chain is open-ended.
    v1_closed = lineage_nodes[
        (lineage_nodes.schema_version == "SCHEMA_V1") & (lineage_nodes.valid_to != "")
    ]
    assert len(v1_closed) >= 8
    v2_open = lineage_nodes[
        (lineage_nodes.schema_version == "SCHEMA_V2") & (lineage_nodes.valid_to == "")
    ]
    assert len(v2_open) >= 5


def test_change_register_counts_and_categories(schema_changes):
    cats = set(schema_changes["change_category"])
    assert cats == {
        "UNIT_REDEFINITION", "INTERFACE_REMAP", "SEMANTIC_REDEFINITION",
        "EXTRACTION_PIPELINE_CHANGE", "BUSINESS_CHANGE", "NORMAL_CHANGE",
    }
    normal = schema_changes[schema_changes.change_category == "NORMAL_CHANGE"]
    defect = schema_changes[schema_changes.change_category != "NORMAL_CHANGE"]
    assert 50 <= len(normal) <= 75  # negative-control index
    assert len(defect) >= 45
    for col in ["change_id", "affected_nodes", "change_category",
                "submitted_at", "approved_at", "effective_at", "version"]:
        assert col in schema_changes.columns


def test_defect_ticket_total_and_distribution(synthetic):
    tickets = pd.read_csv(synthetic / "defect_tickets.csv", keep_default_na=False)
    assert len(tickets) == 180
    counts = tickets["confirmed_category"].value_counts().to_dict()
    assert set(counts) == set(CATEGORIES)
    for cat in CATEGORIES:
        assert counts[cat] >= 1, cat
    # UNKNOWN is a sizeable minority of the ticket population.
    assert counts["UNKNOWN"] >= 0.08 * len(tickets)
    assert tickets["defect_id"].is_unique


def test_six_category_enum_is_frozen():
    assert CATEGORIES == (
        "UNIT_CHANGE",
        "INTERFACE_MAPPING_ERROR",
        "FIELD_SEMANTIC_CHANGE",
        "EXTRACTION_FAILURE",
        "TRUE_BUSINESS_CHANGE",
        "UNKNOWN",
    )


def test_perturbation_plan_counts(synthetic):
    plan = json.loads((synthetic / "perturbation_library.json").read_text())
    perts = plan["perturbations"]
    assert plan["seed"] == SEED
    kinds = {}
    for p in perts:
        kinds[p["true_category"]] = kinds.get(p["true_category"], 0) + 1
    assert kinds == {
        "UNIT_CHANGE": 10,
        "INTERFACE_MAPPING_ERROR": 15,
        "EXTRACTION_FAILURE": 12,
        "FIELD_SEMANTIC_CHANGE": 7,
        "TRUE_BUSINESS_CHANGE": 4,
        "UNKNOWN": 18,
    }
    assert len(perts) == 66
    # Mechanism fields are consistent with the perturbation kind:
    # interface events garble raw values and/or push values out of range;
    # every other kind uses exactly one of shift / wrong unit / missing.
    for p in perts:
        major = sum(bool(v) for v in (
            float(p["shift_magnitude"]), p["wrong_unit"],
            float(p["missing_fraction"])))
        minor = float(p["garble_fraction"]) > 0 or float(p["out_of_range_fraction"]) > 0
        if p["true_category"] == "INTERFACE_MAPPING_ERROR":
            assert major == 0 and minor, p["perturbation_id"]
        elif p["true_category"] == "UNKNOWN":
            # UNKNOWN events are either a missing burst or a garble burst
            # with no change record; never both.
            assert (major == 1) ^ minor, p["perturbation_id"]
        else:
            assert major == 1 and not minor, p["perturbation_id"]


def test_ambiguous_pairs_and_lineage_breaks_flagged(synthetic):
    plan = json.loads((synthetic / "perturbation_library.json").read_text())
    perts = plan["perturbations"]
    ambiguous = [p for p in perts if p.get("ambiguous_pair")]
    broken = [p for p in perts if p.get("lineage_break")]
    assert len(ambiguous) == 4
    assert len(broken) == 5
    assert len({p["ambiguous_pair"] for p in ambiguous}) == 4


def test_normal_control_index(synthetic):
    controls = pd.read_csv(synthetic / "normal_control_index.csv", keep_default_na=False)
    assert 50 <= len(controls) <= 75
    assert (controls["category"] == "NORMAL_CHANGE").all()
    assert controls["control_id"].is_unique


def test_observation_stream_shape(synthetic, lineage_nodes):
    obs = pd.read_csv(synthetic / "field_observations.csv", keep_default_na=False)
    assert len(obs) == 2020
    assert obs["observation_id"].is_unique
    known = set(lineage_nodes.node_id)
    assert obs.node_id.isin(known).all()
    # Schema boundary respected: V1 report node observations end before the
    # boundary; V2 report node observations start at/after it.
    boundary = _ts(SCHEMA_VERSION_BOUNDARY)
    n005 = obs[obs.node_id == "N005"]
    assert _ts(n005.observed_at_utc.max()) < boundary
    n019 = obs[obs.node_id == "N019"]
    assert _ts(n019.observed_at_utc.min()) >= boundary


def test_field_profiles_cover_observable_fields(synthetic):
    profiles = pd.read_csv(synthetic / "field_profiles.csv", keep_default_na=False)
    assert len(profiles) == 19
    assert profiles["field_name"].is_unique
    for _, row in profiles.iterrows():
        assert 0.0 <= float(row["missing_rate"]) <= 1.0
