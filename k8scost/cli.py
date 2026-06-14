"""Command-line interface for k8scost."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import (
    CostError,
    PriceSheet,
    analyze,
    parse_workloads,
    summarize,
)


def _load(path: str):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _print_table(reports, summ) -> None:
    print(f"{'WORKLOAD':<28}{'NS':<14}{'REP':>4}{'COST/mo':>12}{'REC/mo':>12}{'SAVE/mo':>12}{'FLAGS':>7}")
    print("-" * 89)
    for r in reports:
        name = (r["name"][:27]) if len(r["name"]) > 27 else r["name"]
        ns = (r["namespace"][:13]) if len(r["namespace"]) > 13 else r["namespace"]
        print(f"{name:<28}{ns:<14}{r['replicas']:>4}"
              f"${r['monthly_cost']:>10.2f}${r['recommended_monthly_cost']:>10.2f}"
              f"${r['monthly_savings']:>10.2f}{r['findings_count']:>7}")
    print("-" * 89)
    print(f"TOTAL: ${summ['total_monthly_cost']:.2f}/mo  "
          f"recommended ${summ['recommended_monthly_cost']:.2f}/mo  "
          f"savings ${summ['potential_monthly_savings']:.2f}/mo "
          f"({summ['savings_pct']}%)  flags={summ['total_findings']}")


def _print_advise(reports) -> None:
    for r in reports:
        for c in r["containers"]:
            if not c["findings"]:
                continue
            print(f"\n{r['namespace']}/{r['name']} :: {c['name']}")
            cur = c["current"]
            rec = c["recommended"]
            print(f"  current  cpu={cur['cpu_request_m']}m mem={cur['mem_request_mi']}Mi")
            print(f"  suggest  cpu={rec['cpu_request_m']}m mem={rec['mem_request_mi']}Mi")
            for f in c["findings"]:
                print(f"  - {f}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Kubernetes cost & rightsizing advisor (no Prometheus required).",
    )
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("--format", choices=["table", "json"], default="table",
                   help="output format (default: table)")
    p.add_argument("--cpu-price", type=float, default=PriceSheet().cpu_core_hour,
                   help="$ per vCPU-hour")
    p.add_argument("--mem-price", type=float, default=PriceSheet().mem_gib_hour,
                   help="$ per GiB-hour")
    sub = p.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("analyze", help="cost + rightsizing report for workloads")
    pa.add_argument("input", help="workload JSON file, or '-' for stdin")
    pa.add_argument("--advise", action="store_true",
                    help="(table mode) print detailed per-container advice")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cpu_price < 0:
        print("error: --cpu-price must be >= 0", file=sys.stderr)
        return 2
    if args.mem_price < 0:
        print("error: --mem-price must be >= 0", file=sys.stderr)
        return 2

    prices = PriceSheet(cpu_core_hour=args.cpu_price, mem_gib_hour=args.mem_price)

    try:
        data = _load(args.input)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read input: {e}", file=sys.stderr)
        return 2

    try:
        workloads = parse_workloads(data)
        reports = analyze(workloads, prices)
        summ = summarize(reports)
    except CostError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"error: unexpected failure: {e}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps({"summary": summ, "workloads": reports}, indent=2))
    else:
        _print_table(reports, summ)
        if args.advise:
            _print_advise(reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
