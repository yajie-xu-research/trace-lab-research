"""Five-table (+ observation stream) validation.

Reads the table structures from schemas/p2_tables.yaml and checks every
column rule: required, unique keys, enum membership, time ordering, and
cross-table references. Writes data_quality_report.json and excluded_rows.csv
(the rows that violate rules, with reasons). Exits non-zero on violations.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..common.hashing import hash_file
from ..common.io import read_csv_ordered, write_csv, write_json
from ..common.log import RunLog
from ..common.manifest import manifest_for_command
from ..common.run_id import logical_utc

UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _is_timestamp(value: Any) -> bool:
    return bool(UTC_PATTERN.match(str(value).strip()))


def _is_timestamp_or_empty(value: Any) -> bool:
    text = str(value).strip()
    return text == "" or bool(UTC_PATTERN.match(text))


def _parse_ts(value: Any) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def validate_input(input_dir: str | Path, schema_path: str | Path) -> dict[str, Any]:
    input_dir = Path(input_dir)
    with open(schema_path, "r", encoding="utf-8") as fh:
        schema = yaml.safe_load(fh)

    errors: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    per_table: dict[str, dict[str, Any]] = {}
    input_rows_total = 0

    for table_name, spec in schema["tables"].items():
        file_path = input_dir / spec["file"]
        info: dict[str, Any] = {"rows": 0, "errors": 0}
        if not file_path.exists():
            errors.append({"table": table_name, "file": spec["file"], "error": "file missing"})
            per_table[table_name] = info
            continue
        df = read_csv_ordered(file_path)
        info["rows"] = len(df)
        input_rows_total += len(df)

        column_names = [c["name"] for c in spec["columns"]]
        missing_cols = [c for c in column_names if c not in df.columns]
        if missing_cols:
            errors.append({"table": table_name, "file": spec["file"], "error": f"missing columns {missing_cols}"})
            per_table[table_name] = info
            continue

        # Required / pattern / enum checks.
        for col_spec in spec["columns"]:
            name = col_spec["name"]
            pattern = col_spec.get("pattern")
            enum = col_spec.get("enum")
            required = col_spec.get("required", False)
            if pattern:
                rx = re.compile(pattern)
                bad = df[~df[name].astype(str).str.match(rx)].index
                for i in bad:
                    excluded.append({
                        "table": table_name, "file": spec["file"], "row_index": int(i),
                        "column": name, "value": str(df.at[i, name]),
                        "reason": f"pattern mismatch ({pattern})",
                    })
            if enum:
                allowed = set(enum)
                bad = df[~df[name].astype(str).isin(allowed)].index
                for i in bad:
                    excluded.append({
                        "table": table_name, "file": spec["file"], "row_index": int(i),
                        "column": name, "value": str(df.at[i, name]),
                        "reason": f"value not in enum {sorted(allowed)}",
                    })
            if required:
                bad = df[df[name].astype(str).str.strip() == ""].index
                for i in bad:
                    excluded.append({
                        "table": table_name, "file": spec["file"], "row_index": int(i),
                        "column": name, "value": "", "reason": "required value missing",
                    })

        # Uniqueness.
        for col_spec in spec["columns"]:
            if col_spec.get("unique"):
                name = col_spec["name"]
                dup = df[df.duplicated(subset=[name], keep=False)]
                for i in dup.index:
                    excluded.append({
                        "table": table_name, "file": spec["file"], "row_index": int(i),
                        "column": name, "value": str(df.at[i, name]),
                        "reason": "duplicate key",
                    })
        key = spec.get("key")
        if key:
            dup = df[df.duplicated(subset=key, keep=False)]
            for i in dup.index:
                excluded.append({
                    "table": table_name, "file": spec["file"], "row_index": int(i),
                    "column": "|".join(key), "value": "|".join(str(df.at[i, c]) for c in key),
                    "reason": "duplicate composite key",
                })

        # Time ordering.
        for a, b in spec.get("time_order_rules", []):
            for i, row in df.iterrows():
                va, vb = str(row[a]).strip(), str(row[b]).strip()
                if va and vb and _is_timestamp(va) and _is_timestamp(vb):
                    if _parse_ts(va) > _parse_ts(vb):
                        excluded.append({
                            "table": table_name, "file": spec["file"], "row_index": int(i),
                            "column": f"{a} > {b}", "value": f"{va} > {vb}",
                            "reason": "time order violated",
                        })

        # Cross-table references.
        if table_name == "lineage_edges":
            node_ids = set(read_csv_ordered(input_dir / "lineage_nodes.csv")["node_id"].astype(str))
            for i, row in df.iterrows():
                for col in ("from_node", "to_node"):
                    if str(row[col]) not in node_ids:
                        excluded.append({
                            "table": table_name, "file": spec["file"], "row_index": int(i),
                            "column": col, "value": str(row[col]),
                            "reason": f"{col} not found in lineage_nodes",
                        })
                if str(row["from_node"]) == str(row["to_node"]):
                    excluded.append({
                        "table": table_name, "file": spec["file"], "row_index": int(i),
                        "column": "from_node==to_node", "value": str(row["from_node"]),
                        "reason": "self-loop edge",
                    })
        if table_name == "field_observations":
            node_map = read_csv_ordered(input_dir / "lineage_nodes.csv").set_index("node_id")
            for i, row in df.iterrows():
                nid = str(row["node_id"])
                if nid not in node_map.index:
                    excluded.append({
                        "table": table_name, "file": spec["file"], "row_index": int(i),
                        "column": "node_id", "value": nid,
                        "reason": "node_id not found in lineage_nodes",
                    })
                elif str(row["source_system"]) != str(node_map.at[nid, "system"]):
                    excluded.append({
                        "table": table_name, "file": spec["file"], "row_index": int(i),
                        "column": "source_system", "value": str(row["source_system"]),
                        "reason": "source_system does not match node system",
                    })

        info["errors"] = len(excluded)
        per_table[table_name] = info

    for e in excluded:
        e.setdefault("table", "")
    errors += [
        {"table": e["table"], "file": e["file"], "error": f"row {e['row_index']}: {e['reason']} ({e['column']}={e['value']})"}
        for e in excluded
    ]

    report = {
        "schema_version": schema["schema_version"],
        "per_table": per_table,
        "error_count": len(errors),
        "excluded_row_count": len(excluded),
        "errors": errors[:100],
    }
    return report, pd.DataFrame(excluded), input_rows_total


def run_validation(
    input_dir: str | Path,
    out_dir: str | Path,
    config_path: str | Path,
    schema_path: str | Path,
    *,
    seed: str = "20250110",
) -> dict[str, Any]:
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = RunLog(out_dir / "run.log", logical_utc("validate"))

    report, excluded_df, input_rows = validate_input(input_dir, schema_path)
    write_json(report, out_dir / "data_quality_report.json")
    if excluded_df.empty:
        pd.DataFrame(columns=["table", "file", "row_index", "column", "value", "reason"]).to_csv(
            out_dir / "excluded_rows.csv", index=False
        )
    else:
        write_csv(excluded_df, out_dir / "excluded_rows.csv")

    ok = report["error_count"] == 0
    manifest = manifest_for_command(
        "validate",
        config_hash=hash_file(config_path) if Path(config_path).exists() else "",
        data_hash=hash_file(input_dir / "lineage_nodes.csv"),
        seed=seed,
        rule_version=report["schema_version"],
        results_hash=hash_file(out_dir / "data_quality_report.json"),
        input_rows=input_rows,
        excluded_rows=report["excluded_row_count"],
        known_issues=[] if ok else ["validation errors present; see data_quality_report.json"],
    )
    write_json(manifest, out_dir / "manifest.json")
    write_json({"ok": ok, "error_count": report["error_count"]}, out_dir / "run_receipt.json")
    log.info(f"validated {input_rows} rows across tables; errors={report['error_count']}")
    log.close()
    return {"ok": ok, "report": report, "manifest": manifest}
