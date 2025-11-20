"""Validation contract tests: the five-table schema, exclusion accounting,
and the written excluded_rows.csv."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from trace_lab.p2.validate import validate_input, run_validation


def test_clean_synthetic_passes(synthetic, config_paths):
    report, excluded, total = validate_input(synthetic, config_paths["schema"])
    assert report["error_count"] == 0
    assert report["excluded_row_count"] == 0
    assert excluded.empty
    assert total > 1000


def test_bad_format_row_is_excluded(synthetic, config_paths, tmp_path):
    import shutil
    from trace_lab.common.io import read_csv_ordered, write_csv

    shutil.copytree(synthetic, tmp_path, dirs_exist_ok=True)
    nodes = read_csv_ordered(tmp_path / "lineage_nodes.csv")
    nodes.loc[nodes.index[0], "node_id"] = "bad id!"  # space + bang fail pattern
    write_csv(nodes, tmp_path / "lineage_nodes.csv")
    report, excluded, _ = validate_input(tmp_path, config_paths["schema"])
    assert report["error_count"] >= 1
    assert excluded["reason"].str.contains("pattern").any()


def test_duplicate_key_row_is_excluded(synthetic, config_paths, tmp_path):
    import shutil
    from trace_lab.common.io import read_csv_ordered, write_csv

    shutil.copytree(synthetic, tmp_path, dirs_exist_ok=True)
    nodes = read_csv_ordered(tmp_path / "lineage_nodes.csv")
    nodes.loc[nodes.index[1], "node_id"] = nodes.loc[nodes.index[0], "node_id"]
    write_csv(nodes, tmp_path / "lineage_nodes.csv")
    report, excluded, _ = validate_input(tmp_path, config_paths["schema"])
    assert report["error_count"] >= 1
    assert excluded["reason"].str.contains("duplicate").any()


def test_time_order_violation_is_excluded(synthetic, config_paths, tmp_path):
    import shutil
    from trace_lab.common.io import read_csv_ordered, write_csv

    shutil.copytree(synthetic, tmp_path, dirs_exist_ok=True)
    edges = read_csv_ordered(tmp_path / "lineage_edges.csv")
    row = edges.index[0]
    edges.loc[row, "valid_to"], edges.loc[row, "valid_from"] = (
        edges.loc[row, "valid_from"], edges.loc[row, "valid_to"])
    write_csv(edges, tmp_path / "lineage_edges.csv")
    report, excluded, _ = validate_input(tmp_path, config_paths["schema"])
    assert report["error_count"] >= 1
    assert excluded["reason"].str.contains("order").any()


def test_schema_versions_restricted(synthetic, config_paths, tmp_path):
    import shutil
    from trace_lab.common.io import read_csv_ordered, write_csv

    shutil.copytree(synthetic, tmp_path, dirs_exist_ok=True)
    nodes = read_csv_ordered(tmp_path / "lineage_nodes.csv")
    nodes.loc[nodes.index[0], "schema_version"] = "SCHEMA_V9"
    write_csv(nodes, tmp_path / "lineage_nodes.csv")
    report, excluded, _ = validate_input(tmp_path, config_paths["schema"])
    assert report["error_count"] >= 1
    assert excluded["reason"].str.contains("enum").any()


def test_validation_run_writes_receipt_and_manifest(synthetic, config_paths, tmp_path):
    out = tmp_path / "val"
    result = run_validation(
        synthetic, out, config_paths["categories"], config_paths["schema"],
        seed=20250110,
    )
    assert result["ok"]
    receipt = json.loads((out / "run_receipt.json").read_text())
    assert receipt["ok"] is True
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["command"] == "validate"
    assert manifest["status"] == "INTERNAL_RESEARCH"
    assert (out / "excluded_rows.csv").is_file()
