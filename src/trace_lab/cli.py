"""Command-line entry point for trace-lab.

Commands:
  generate-synthetic   write the synthetic dataset (seed 20250110)
  validate             validate the input tables against the frozen schema
  p2 triage            run anomaly detection -> lineage -> triage
  p2 evaluate          held-out perturbation evaluation of a triage run
  manifest inspect     print a run manifest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common.hashing import hash_file
from .common.manifest import manifest_for_command
from .common.run_id import logical_utc


def _cmd_generate(args: argparse.Namespace) -> int:
    from .p2.generator import generate_synthetic

    counts = generate_synthetic(args.output, seed=args.seed)
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    from .p2.validate import run_validation

    result = run_validation(
        args.input,
        args.out,
        args.config,
        args.schema,
        seed=args.seed,
    )
    print(json.dumps({"ok": result["ok"], "error_count": result["report"]["error_count"]}, indent=2))
    return 0 if result["ok"] else 1


def _cmd_triage(args: argparse.Namespace) -> int:
    from .p2.triage import run_triage

    result = run_triage(
        args.input,
        args.out,
        args.categories,
        args.policy,
        seed=args.seed,
    )
    receipt = result["receipt"]
    print(
        json.dumps(
            {
                "anomalies_detected": receipt["anomalies_detected"],
                "triage": receipt["triage"],
                "abstain": receipt["abstain"],
                "result_hash": result["manifest"]["result_hash"],
            },
            indent=2,
        )
    )
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from .p2.evaluate import run_evaluation

    result = run_evaluation(
        args.run,
        args.out,
        policy_config=args.policy,
        baseline_config=args.baselines,
        seed=args.seed,
    )
    main = result["metrics"]["TRACE_LAB_MAIN"]
    print(
        json.dumps(
            {
                "abstain_rate": main["abstain_rate"],
                "false_positive_rate_on_controls": main["false_positive_rate_on_controls"],
                "per_category_precision": main["per_category_precision"],
                "per_category_recall": main["per_category_recall"],
            },
            indent=2,
        )
    )
    return 0


def _cmd_manifest_inspect(args: argparse.Namespace) -> int:
    from .common.io import read_json

    manifest_path = Path(args.run) / "manifest.json"
    if not manifest_path.exists():
        print(f"error: manifest not found at {manifest_path}", file=sys.stderr)
        return 1
    manifest = read_json(manifest_path)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trace-lab", description="TRACE-LAB research tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("generate-synthetic", help="generate the synthetic dataset")
    p.add_argument("--output", default="synthetic_data/")
    p.add_argument("--seed", type=int, default=20250110)
    p.set_defaults(func=_cmd_generate)

    p = sub.add_parser("validate", help="validate input tables against the schema")
    p.add_argument("--input", required=True)
    p.add_argument("--config", default="configs/p2_categories.yaml")
    p.add_argument("--schema", default="schemas/p2_tables.yaml")
    p.add_argument("--out", default="outputs/runs/p2_validate/")
    p.add_argument("--seed", type=int, default=20250110)
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("p2", help="P2 subcommands")
    p2 = p.add_subparsers(dest="p2_command", required=True)

    t = p2.add_parser("triage", help="run anomaly detection and lineage triage")
    t.add_argument("--input", required=True)
    t.add_argument("--out", default="outputs/runs/p2_triage/")
    t.add_argument("--categories", default="configs/p2_categories.yaml")
    t.add_argument("--policy", default="configs/p2_lineage.yaml")
    t.add_argument("--seed", type=int, default=20250110)
    t.set_defaults(func=_cmd_triage)

    e = p2.add_parser("evaluate", help="held-out perturbation evaluation of a triage run")
    e.add_argument("--run", required=True)
    e.add_argument("--out", default="outputs/runs/p2_evaluation/")
    e.add_argument("--policy", default="configs/p2_lineage.yaml")
    e.add_argument("--baselines", default="configs/p2_baselines.yaml")
    e.add_argument("--seed", type=int, default=20250110)
    e.set_defaults(func=_cmd_evaluate)

    m = sub.add_parser("manifest", help="manifest subcommands")
    mm = m.add_subparsers(dest="manifest_command", required=True)
    i = mm.add_parser("inspect", help="print a run manifest")
    i.add_argument("--run", required=True)
    i.set_defaults(func=_cmd_manifest_inspect)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
