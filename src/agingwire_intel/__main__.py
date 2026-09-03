from __future__ import annotations

import argparse
import sys

from agingwire_intel.dashboard import build_dashboard
from agingwire_intel.digest import write_digest
from agingwire_intel.pipeline import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AgingWire research intelligence")
    parser.add_argument("--config", default="config/monitors.yml")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--state", default="state/seen.json")
    parser.add_argument(
        "--fail-on-source-errors",
        type=int,
        default=None,
        metavar="N",
        help="Exit non-zero when more than N evidence sources error out.",
    )
    args = parser.parse_args()

    payload = run(args.config, args.output_dir, docs_dir=args.docs_dir, state_path=args.state)
    digest = write_digest(payload, args.output_dir)
    dashboard = build_dashboard(f"{args.docs_dir}/index.html")

    errors = [x for x in payload["source_status"] if x["status"] == "error"]
    empties = [x for x in payload["source_status"] if x["status"] == "empty"]
    print(
        f"Collected {payload['evidence_count']} evidence candidates "
        f"({payload['new_evidence_count']} new) and {payload['coverage_count']} media items "
        f"from {payload['monitored_publisher_count']}/{payload['registry_publisher_count']} publisher feeds"
    )
    print(f"Evidence sources: {len(errors)} error, {len(empties)} empty")
    for entry in errors:
        print(f"  error  {entry['source']}: {entry.get('error', '')[:160]}")
    for entry in empties:
        print(f"  empty  {entry['source']} ({entry.get('method')})")
    print(f"Digest: {digest}")
    print(f"Dashboard: {dashboard}")

    if args.fail_on_source_errors is not None and len(errors) > args.fail_on_source_errors:
        print(f"FAIL: {len(errors)} source errors exceeds threshold {args.fail_on_source_errors}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
