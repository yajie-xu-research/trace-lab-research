"""Defect category dictionary: loading and rule application.

The dictionary is frozen in configs/p2_categories.yaml. This module exposes
lookups for symptom signatures, change-category matches, precedence, and
exclusivity. Precedence is applied between *candidates*, never between
tickets: a higher-precedence category wins only when its symptom score is
strictly higher; otherwise the anomaly stays ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .constants import CATEGORIES


@dataclass
class CategoryDict:
    rule_version: str
    frozen_at: str
    categories: dict[str, dict[str, Any]] = field(default_factory=dict)
    abstention_conditions: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "CategoryDict":
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        categories = {name: spec for name, spec in raw["categories"].items()}
        unknown = set(categories) - set(CATEGORIES)
        if unknown:
            raise ValueError(f"category dictionary contains unknown categories: {sorted(unknown)}")
        missing = set(CATEGORIES) - set(categories)
        if missing:
            raise ValueError(f"category dictionary missing categories: {sorted(missing)}")
        return cls(
            rule_version=raw["rule_version"],
            frozen_at=raw["frozen_at"],
            categories=categories,
            abstention_conditions=raw.get("abstention_conditions", []),
        )

    def symptom_weight(self, category: str, anomaly_rule: str) -> float:
        """Weight of an anomaly rule as evidence for a category (0 = no match)."""
        total = 0.0
        for signature in self.categories[category]["symptom_signatures"]:
            if signature["anomaly_rule"] == anomaly_rule:
                total += float(signature["weight"])
        return total

    def matches_change_category(self, category: str, change_category: str) -> bool:
        return change_category in self.categories[category]["matching_change_categories"]

    def precedence_over(self, category: str) -> tuple[str, ...]:
        return tuple(self.categories[category]["precedence_over"])

    def exclusive_with(self, category: str) -> tuple[str, ...]:
        return tuple(self.categories[category]["exclusive_with"])

    def exclusivity_conflict(self, a: str, b: str) -> bool:
        return b in self.exclusive_with(a) or a in self.exclusive_with(b)

    def apply_precedence(
        self, scored: list[tuple[str, float]], tie_epsilon: float
    ) -> tuple[list[tuple[str, float]], bool]:
        """Resolve precedence among scored (category, score) candidates.

        Returns (kept_candidates, ambiguous). If one category strictly beats
        every category it has precedence over, the beaten ones are dropped.
        If scores are within tie_epsilon and precedence does not separate
        them, ambiguity is reported by the caller.
        """
        kept = list(scored)
        ambiguous = False
        for name, score in scored:
            for beaten in self.precedence_over(name):
                for other_name, other_score in scored:
                    if other_name == beaten:
                        if score > other_score + tie_epsilon:
                            kept = [item for item in kept if item[0] != beaten]
                        else:
                            ambiguous = True
        return kept, ambiguous
