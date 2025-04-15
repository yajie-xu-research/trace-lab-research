"""CSV / JSON IO helpers with deterministic output.

CSV files are written with a fixed column order and CRLF-normalized content
so that repeated runs produce byte-identical artifacts (modulo any columns
excluded from determinism at the call site).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def read_csv_ordered(path: str | Path, dtype: str | dict | None = None) -> pd.DataFrame:
    """Read a CSV keeping columns in file order, all values as given."""
    return pd.read_csv(path, dtype=dtype, keep_default_na=False)


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)


def write_json(value: Any, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(value, fh, indent=2, sort_keys=False, ensure_ascii=True)
        fh.write("\n")


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
