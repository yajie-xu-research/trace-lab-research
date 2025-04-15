"""CLI end-to-end tests for the five trace-lab commands, plus hashing,
logical timestamps, run ids, and manifest integrity."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trace_lab.common.hashing import hash_object
from trace_lab.common.run_id import logical_utc, run_id_for
from trace_lab.common.manifest import result_hash, build_manifest

REPO = Path(__file__).resolve().parent.parent
CONFIGS = REPO / "configs"
SCHEMAS = REPO / "schemas"


def _cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    # All file arguments are absolute; the repo CWD makes the default config
    # paths resolvable.
    return subprocess.run(
        [sys.executable, "-m", "trace_lab.cli", *args],
        capture_output=True, text=True, cwd=str(REPO), env=env, timeout=900)


def test_cli_generate_synthetic(tmp_path):
    out = tmp_path / "data"
    res = _cli(tmp_path, "generate-synthetic", "--output", str(out), "--seed", "20250110")
    assert res.returncode == 0, res.stderr
    assert (out / "lineage_nodes.csv").is_file()


def test_cli_validate(tmp_path):
    out = tmp_path / "data"
    _cli(tmp_path, "generate-synthetic", "--output", str(out), "--seed", "20250110")
    res = _cli(tmp_path, "validate", "--input", str(out),
               "--out", str(tmp_path / "runs" / "validate"))
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "runs" / "validate" / "manifest.json").is_file()


def test_cli_p2_triage(tmp_path):
    out = tmp_path / "data"
    _cli(tmp_path, "generate-synthetic", "--output", str(out), "--seed", "20250110")
    res = _cli(tmp_path, "p2", "triage", "--input", str(out),
               "--out", str(tmp_path / "runs" / "triage"))
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "runs" / "triage" / "triage_results.csv").is_file()


def test_cli_p2_evaluate(tmp_path):
    out = tmp_path / "data"
    _cli(tmp_path, "generate-synthetic", "--output", str(out), "--seed", "20250110")
    _cli(tmp_path, "p2", "triage", "--input", str(out),
         "--out", str(tmp_path / "runs" / "triage"))
    res = _cli(tmp_path, "p2", "evaluate", "--run", str(tmp_path / "runs" / "triage"),
               "--out", str(tmp_path / "runs" / "evaluate"))
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "runs" / "evaluate" / "evaluation_summary.md").is_file()


def test_cli_manifest_inspect(tmp_path):
    out = tmp_path / "data"
    _cli(tmp_path, "generate-synthetic", "--output", str(out), "--seed", "20250110")
    _cli(tmp_path, "validate", "--input", str(out),
         "--out", str(tmp_path / "runs" / "validate"))
    res = _cli(tmp_path, "manifest", "inspect", "--run", str(tmp_path / "runs" / "validate"))
    assert res.returncode == 0, res.stderr
    assert "command" in res.stdout


def test_every_run_dir_has_manifest_and_log(tmp_path):
    out = tmp_path / "data"
    _cli(tmp_path, "generate-synthetic", "--output", str(out), "--seed", "20250110")
    _cli(tmp_path, "validate", "--input", str(out),
         "--out", str(tmp_path / "runs" / "validate"))
    _cli(tmp_path, "p2", "triage", "--input", str(out),
         "--out", str(tmp_path / "runs" / "triage"))
    for name in ("validate", "triage"):
        run_dir = tmp_path / "runs" / name
        assert (run_dir / "manifest.json").is_file(), name
        assert (run_dir / "run.log").is_file(), name
        assert (run_dir / "excluded_rows.csv").is_file(), name


def test_manifest_result_hash_matches_recomputation(tmp_path):
    out = tmp_path / "data"
    _cli(tmp_path, "generate-synthetic", "--output", str(out), "--seed", "20250110")
    _cli(tmp_path, "validate", "--input", str(out),
         "--out", str(tmp_path / "runs" / "validate"))
    manifest = json.loads((tmp_path / "runs" / "validate" / "manifest.json").read_text())
    recomputed = build_manifest(
        project="P2_TRACE_LAB",
        command="validate",
        status=manifest["status"],
        config_hash=manifest["config_hash"],
        data_hash=manifest["data_hash"],
        seed=manifest["seed"],
        rule_version=manifest["model_or_rule_version"],
        results_hash=manifest["results_hash"],
    )
    assert recomputed["result_hash"] == manifest["result_hash"]


def test_hash_object_is_key_order_independent():
    assert hash_object({"b": 1, "a": [2, 3]}) == hash_object({"a": [2, 3], "b": 1})
    assert hash_object({"a": 1}) != hash_object({"a": 2})


def test_logical_timestamps_and_run_ids():
    assert logical_utc("p2_triage") == "2026-06-28T09:00:00Z"
    rid = run_id_for("trace_lab_research", "p2_triage")
    assert rid.startswith("run-trace-lab-research-p2-triage-20260628T090000Z")
    with pytest.raises(ValueError):
        logical_utc("no-such-command")
