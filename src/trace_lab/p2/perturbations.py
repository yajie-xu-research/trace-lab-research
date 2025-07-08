"""Controlled perturbation library.

Each perturbation kind injects one signature into the observation stream
over a fixed 14-day window:

- UNIT_CHANGE: reported unit labels switch to a wrong unit;
- INTERFACE_MAPPING_ERROR: raw values garbled (format violations) and some
  parsed values pushed out of range;
- FIELD_SEMANTIC_CHANGE / TRUE_BUSINESS_CHANGE: value distribution shifts
  (change point) with no format or unit change;
- EXTRACTION_FAILURE: a burst of missing rows (missing-rate shift);
- UNKNOWN: a burst of missing rows or format garbling with no change record.

Injections are deterministic given the plan. The perturbation plan itself is
ground truth and is never read by the triage pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd


def _ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Perturbation:
    perturbation_id: str
    kind: str
    node_id: str
    window_start: str
    window_end: str
    change_id: str
    defect_id: str
    true_category: str
    ambiguous_pair: str
    lineage_break: bool
    shift_magnitude: float = 0.0
    wrong_unit: str = ""
    missing_fraction: float = 0.0
    garble_fraction: float = 0.0
    out_of_range_fraction: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "perturbation_id": self.perturbation_id,
            "kind": self.kind,
            "node_id": self.node_id,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "change_id": self.change_id,
            "defect_id": self.defect_id,
            "true_category": self.true_category,
            "ambiguous_pair": self.ambiguous_pair,
            "lineage_break": self.lineage_break,
            "shift_magnitude": self.shift_magnitude,
            "wrong_unit": self.wrong_unit,
            "missing_fraction": self.missing_fraction,
            "garble_fraction": self.garble_fraction,
            "out_of_range_fraction": self.out_of_range_fraction,
        }


def apply_perturbation(obs: pd.DataFrame, p: Perturbation, rng) -> pd.DataFrame:
    """Apply one perturbation in place (rows matched by node and window)."""
    start = _ts(p.window_start)
    end = _ts(p.window_end)
    mask = obs["node_id"] == p.node_id
    time_mask = obs["observed_at_utc"].apply(lambda t: start <= _ts(t) < end)
    idx = obs.index[mask & time_mask]
    if len(idx) == 0:
        return obs

    if p.shift_magnitude > 0:
        shift = p.shift_magnitude
        for i in idx:
            num = float(obs.at[i, "parsed_value"]) if str(obs.at[i, "parsed_value"]) else 0.0
            new_num = round(num + shift, 4)
            obs.at[i, "parsed_value"] = f"{new_num:.4f}"
            obs.at[i, "raw_value"] = f"{new_num:.4f}"

    elif p.wrong_unit:
        for i in idx:
            obs.at[i, "raw_value"] = p.wrong_unit
            obs.at[i, "reported_unit"] = p.wrong_unit

    elif p.garble_fraction > 0:
        listed = list(idx)
        garble_n = max(1, int(len(listed) * p.garble_fraction))
        garble_idx = rng.choice(listed, size=min(garble_n, len(listed)), replace=False)
        for i in garble_idx:
            # Every token in the pool must FAIL the field format pattern:
            # the string pattern allows [A-Za-z0-9_. -], so tokens carry
            # '?', '!', '#', or commas (a bare hex token or dots would pass).
            obs.at[i, "raw_value"] = rng.choice(["??", "1,23", "#!", "#ERR"])
        if p.out_of_range_fraction > 0:
            oor_n = max(1, int(len(listed) * p.out_of_range_fraction))
            candidates = [i for i in listed if i not in set(garble_idx)]
            pool = candidates if candidates else listed
            oor_idx = rng.choice(pool, size=min(oor_n, len(pool)), replace=False)
            for i in oor_idx:
                if str(obs.at[i, "parsed_value"]):
                    obs.at[i, "parsed_value"] = "88.0"
                    obs.at[i, "raw_value"] = "88.0"

    elif p.missing_fraction > 0:
        listed = list(idx)
        drop_n = max(1, int(len(listed) * p.missing_fraction))
        drop_idx = rng.choice(listed, size=min(drop_n, len(listed)), replace=False)
        for i in drop_idx:
            obs.at[i, "raw_value"] = ""
            obs.at[i, "parsed_value"] = ""
            obs.at[i, "reported_unit"] = ""

    return obs


def apply_noise(obs: pd.DataFrame, rng, rate: float) -> pd.DataFrame:
    """Sparse background format noise across all rows (not tied to any change)."""
    if rate <= 0:
        return obs
    n = max(1, int(len(obs) * rate))
    idx = rng.choice(list(obs.index), size=n, replace=False)
    for i in idx:
        if str(obs.at[i, "raw_value"]).strip():
            obs.at[i, "raw_value"] = rng.choice(["##", "9,9", "?8"])
    return obs
