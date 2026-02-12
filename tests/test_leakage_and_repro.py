"""Ground-truth isolation (leakage) and reproducibility tests.

The leakage test deletes every ground-truth input (defect tickets, the
perturbation plan, and the normal-control index) before re-running triage.
Triage must never read those files: outputs must be byte-identical.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from trace_lab.p2.triage import run_triage
from trace_lab.common.hashing import hash_file
from trace_lab.p2.constants import GROUND_TRUTH_FILES


def _hash_dir(directory: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(directory))] = hash_file(path)
    return hashes


def test_triage_outputs_identical_without_ground_truth(
        tmp_path, synthetic, config_paths, triage_run):
    stripped = tmp_path / "stripped_input"
    shutil.copytree(synthetic, stripped)
    for name in GROUND_TRUTH_FILES:
        (stripped / name).unlink(missing_ok=True)
    out = tmp_path / "stripped_triage"
    run_triage(stripped, out, config_paths["categories"], config_paths["policy"],
               seed=20250110)

    for name in ("triage_results.csv", "anomalies.csv", "excluded_rows.csv"):
        with (out / name).open("rb") as fh:
            stripped_bytes = fh.read()
        with (triage_run / name).open("rb") as fh:
            full_bytes = fh.read()
        assert stripped_bytes == full_bytes, f"{name} differs after ground-truth removal"


def test_triage_writes_labels_only_under_ground_truth_dir(triage_run):
    data = triage_run / "data"
    gt = data / "_ground_truth"
    assert gt.is_dir()
    labels = gt / "true_defect_labels.csv"
    assert labels.is_file()
    # The ground-truth label file lives only under _ground_truth.
    others = [p for p in data.rglob("true_defect_labels.csv") if p != labels]
    assert others == []


def test_run_artifact_hashes_reproducible(tmp_path, synthetic, config_paths):
    from trace_lab.p2.validate import run_validation
    from trace_lab.p2.evaluate import run_evaluation

    def pipeline(root: Path) -> dict[str, str]:
        val = root / "validate"
        run_validation(synthetic, val, config_paths["categories"],
                       config_paths["schema"], seed=20250110)
        tri = root / "triage"
        run_triage(synthetic, tri, config_paths["categories"],
                   config_paths["policy"], seed=20250110)
        ev = root / "evaluation"
        run_evaluation(tri, ev, policy_config=config_paths["policy"],
                       baseline_config=config_paths["baselines"], seed="20250110")
        hashes = {}
        for directory in (val, tri, ev):
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    hashes[f"{directory.name}/{path.relative_to(directory)}"] = hash_file(path)
        return hashes

    first = pipeline(tmp_path / "run1")
    second = pipeline(tmp_path / "run2")
    assert first == second
    assert len(first) > 15
