"""Frozen category dictionary tests: enum, precedence rules, exclusivity,
and the normal-change negative-control mapping."""

from __future__ import annotations

from trace_lab.p2.categories import CategoryDict
from trace_lab.p2.constants import (
    CATEGORIES,
    CHANGE_CATEGORIES,
    CHANGE_CATEGORY_TO_DEFECT_CATEGORY,
)


def _load(config_paths) -> CategoryDict:
    return CategoryDict.load(config_paths["categories"])


def test_dictionary_loads_six_categories(config_paths):
    d = _load(config_paths)
    assert list(d.categories.keys()) == list(CATEGORIES)


def test_change_categories_all_mapped(config_paths):
    d = _load(config_paths)
    for cc in CHANGE_CATEGORIES:
        target = CHANGE_CATEGORY_TO_DEFECT_CATEGORY[cc]
        if cc == "NORMAL_CHANGE":
            # Negative controls resolve to the non-defect verdict but are not
            # explanatory evidence (handled in the scorer).
            continue
        assert d.matches_change_category(target, cc)


def test_unit_change_precedes_interface_mapping(config_paths):
    d = _load(config_paths)
    assert d.precedence_over("UNIT_CHANGE") == ("INTERFACE_MAPPING_ERROR",)


def test_extraction_failure_precedes_interface_mapping(config_paths):
    d = _load(config_paths)
    assert "INTERFACE_MAPPING_ERROR" in d.precedence_over("EXTRACTION_FAILURE")


def test_extraction_failure_has_only_missing_signature(config_paths):
    d = _load(config_paths)
    rules = {sig["anomaly_rule"] for sig in d.categories["EXTRACTION_FAILURE"]["symptom_signatures"]}
    assert rules == {"MISSING_RATE_SHIFT"}
    assert d.matches_change_category("EXTRACTION_FAILURE", "EXTRACTION_PIPELINE_CHANGE")


def test_normal_change_maps_to_business_verdict(config_paths):
    # NORMAL_CHANGE is a negative control: it resolves to the non-defect
    # verdict TRUE_BUSINESS_CHANGE and is never listed as explanatory
    # evidence for a defect category.
    d = _load(config_paths)
    assert CHANGE_CATEGORY_TO_DEFECT_CATEGORY["NORMAL_CHANGE"] == "TRUE_BUSINESS_CHANGE"
    for cat in CATEGORIES:
        if cat == "TRUE_BUSINESS_CHANGE":
            continue
        assert not d.matches_change_category(cat, "NORMAL_CHANGE")


def test_true_business_change_excludes_all_defect_categories(config_paths):
    d = _load(config_paths)
    excl = set(d.exclusive_with("TRUE_BUSINESS_CHANGE"))
    assert excl == {"UNIT_CHANGE", "INTERFACE_MAPPING_ERROR",
                    "FIELD_SEMANTIC_CHANGE", "EXTRACTION_FAILURE"}
    assert d.exclusivity_conflict("TRUE_BUSINESS_CHANGE", "UNIT_CHANGE")
    assert not d.exclusivity_conflict("UNIT_CHANGE", "EXTRACTION_FAILURE")


def test_unknown_excludes_everything(config_paths):
    d = _load(config_paths)
    excl = set(d.exclusive_with("UNKNOWN"))
    assert len(excl) == 5
    assert "TRUE_BUSINESS_CHANGE" in excl


def test_precedence_resolution_drops_beaten_candidate(config_paths):
    d = _load(config_paths)
    kept, ambiguous = d.apply_precedence(
        [("UNIT_CHANGE", 9.0), ("INTERFACE_MAPPING_ERROR", 5.0)], tie_epsilon=0.5)
    assert kept == [("UNIT_CHANGE", 9.0)]
    assert not ambiguous


def test_precedence_within_tie_stays_ambiguous(config_paths):
    d = _load(config_paths)
    kept, ambiguous = d.apply_precedence(
        [("UNIT_CHANGE", 5.2), ("INTERFACE_MAPPING_ERROR", 5.0)], tie_epsilon=0.5)
    assert ambiguous
    assert len(kept) == 2


def test_symptom_signature_weights_bounded(config_paths):
    d = _load(config_paths)
    for cat in CATEGORIES:
        for sig in d.categories[cat]["symptom_signatures"]:
            assert 0 <= int(sig["weight"]) <= 3
            assert sig["anomaly_rule"] in (
                "FORMAT_VIOLATION", "RANGE_VIOLATION", "UNIT_DEVIATION",
                "MISSING_RATE_SHIFT", "CHANGE_POINT")


def test_symptom_weight_lookup(config_paths):
    d = _load(config_paths)
    assert d.symptom_weight("UNIT_CHANGE", "UNIT_DEVIATION") == 3.0
    assert d.symptom_weight("UNIT_CHANGE", "CHANGE_POINT") == 0.0
    assert d.symptom_weight("FIELD_SEMANTIC_CHANGE", "CHANGE_POINT") == 3.0


def test_dictionary_frozen_metadata(config_paths):
    d = _load(config_paths)
    assert d.rule_version == "1.0"
    assert d.frozen_at == "2025-01-28"
    assert len(d.abstention_conditions) == 3
