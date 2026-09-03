from __future__ import annotations

import argparse

from agingwire_intel.dashboard import build_dashboard
from agingwire_intel.digest import write_digest
from agingwire_intel.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AgingWire research intelligence")
    parser.add_argument("--config", default="config/monitors.yml")
    parser.add_argument("--output-dir", default="outputs")
    args = parser.parse_args()
    payload = run(args.config, args.output_dir)
    digest = write_digest(payload, args.output_dir)
    dashboard = build_dashboard()
    print(f"Collected {payload['evidence_count']} evidence candidates and {payload['coverage_count']} media items")
    print(f"Digest: {digest}")
    print(f"Dashboard: {dashboard}")


if __name__ == "__main__":
    main()
