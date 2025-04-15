"""Shared fixtures for the TRACE-LAB test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
CONFIGS = REPO_ROOT / "configs"
SCHEMAS = REPO_ROOT / "schemas"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def config_paths() -> dict[str, Path]:
    return {
        "categories": CONFIGS / "p2_categories.yaml",
        "policy": CONFIGS / "p2_lineage.yaml",
        "baselines": CONFIGS / "p2_baselines.yaml",
        "schema": SCHEMAS / "p2_tables.yaml",
    }


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def synthetic(tmp_path_factory) -> Path:
    from trace_lab.p2.generator import generate_synthetic

    out = tmp_path_factory.mktemp("synthetic")
    generate_synthetic(out, seed=20250110)
    return out


@pytest.fixture(scope="session")
def triage_run(tmp_path_factory, synthetic, config_paths) -> Path:
    from trace_lab.p2.triage import run_triage

    out = tmp_path_factory.mktemp("triage")
    run_triage(
        synthetic,
        out,
        config_paths["categories"],
        config_paths["policy"],
        seed=20250110,
    )
    return out


@pytest.fixture(scope="session")
def evaluation_run(tmp_path_factory, triage_run, config_paths) -> Path:
    from trace_lab.p2.evaluate import run_evaluation

    out = tmp_path_factory.mktemp("evaluation")
    run_evaluation(
        triage_run,
        out,
        policy_config=config_paths["policy"],
        baseline_config=config_paths["baselines"],
        seed="20250110",
    )
    return out


@pytest.fixture(scope="session")
def triage_results(triage_run) -> pd.DataFrame:
    return pd.read_csv(triage_run / "triage_results.csv", keep_default_na=False)


@pytest.fixture(scope="session")
def observation(synthetic) -> pd.DataFrame:
    return pd.read_csv(synthetic / "field_observations.csv", keep_default_na=False)


@pytest.fixture(scope="session")
def lineage_nodes(synthetic) -> pd.DataFrame:
    return pd.read_csv(synthetic / "lineage_nodes.csv", keep_default_na=False)


@pytest.fixture(scope="session")
def lineage_edges(synthetic) -> pd.DataFrame:
    return pd.read_csv(synthetic / "lineage_edges.csv", keep_default_na=False)


@pytest.fixture(scope="session")
def schema_changes(synthetic) -> pd.DataFrame:
    return pd.read_csv(synthetic / "schema_changes.csv", keep_default_na=False)
