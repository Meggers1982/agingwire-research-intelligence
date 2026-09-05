from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from agingwire_intel import llm, runs
from agingwire_intel.dashboard import build_dashboard
from agingwire_intel.digest import write_digest
from agingwire_intel.pipeline import run
from agingwire_intel.synthesis import synthesize


def _generated_at(payload: dict) -> datetime | None:
    raw = str(payload.get("generated_at") or "")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AgingWire research intelligence")
    parser.add_argument("--config", default="config/monitors.yml")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--state", default="state/seen.json")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip the optional LLM synthesis even when ANTHROPIC_API_KEY is set.",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip the SerpAPI demand and open-web coverage lookups.",
    )
    parser.add_argument(
        "--replay",
        metavar="YYYY-MM-DD",
        help="Re-synthesise a stored day instead of collecting a new one. The "
             "collectors read live APIs and cannot be asked for a past date, "
             "but outputs/<date>.json keeps that day's evidence, so the "
             "editorial layer can be rewritten over it after a prompt change.",
    )
    parser.add_argument(
        "--fail-on-source-errors",
        type=int,
        default=None,
        metavar="N",
        help="Exit non-zero when more than N evidence sources error out.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    replay = bool(args.replay)
    if replay:
        archive = Path(args.output_dir) / f"{args.replay}.json"
        if not archive.exists():
            print(f"FAIL: no stored run at {archive}", file=sys.stderr)
            return 1
        payload = json.loads(archive.read_text(encoding="utf-8"))
        print(f"Replaying {args.replay} from {archive} (no collection)")
    else:
        payload = run(args.config, args.output_dir, docs_dir=args.docs_dir,
                      state_path=args.state, enrich=not args.no_enrich)

    current_id = runs.run_id(payload.get("generated_at", ""))
    previous = runs.load_previous_payload(args.output_dir, current_id)
    # Cluster recency is measured against the clock. Replaying with today's
    # would age that day's evidence by however long ago it ran, so the rerun
    # would not be the same report with a new editorial layer -- it would be a
    # different report.
    now = _generated_at(payload) if replay else None
    synthesis = synthesize(payload, previous, now=now)
    if not args.no_llm:
        synthesis = llm.upgrade_synthesis(payload, synthesis, previous, now=now)

    run_path = runs.write_run(payload, synthesis, docs_dir=args.docs_dir)
    digest = write_digest(payload, args.output_dir, synthesis, latest=not replay)
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
    web = payload.get("web_coverage_status") or {}
    print(
        f"SerpAPI: {payload.get('serpapi_calls', 0)} calls · "
        f"demand {payload.get('demand_source')} "
        f"({len(payload.get('demand_topics') or {})} topics) · "
        f"web coverage checked {web.get('checked', 0)}"
        + (f" · skipped: {web['skipped_reason']}" if web.get("skipped_reason") else "")
    )
    for failure in payload.get("serpapi_failures") or []:
        print(f"  serpapi  {failure['reason']} x{failure['count']}")
    print(f"Synthesis: {synthesis.get('synthesis_mode')}" + (
        f" ({synthesis['synthesis_note']})" if synthesis.get("synthesis_note") else ""
    ))
    print(f"Run: {run_path}")
    print(f"Digest: {digest}")
    print(f"Dashboard: {dashboard}")

    if args.fail_on_source_errors is not None and len(errors) > args.fail_on_source_errors:
        print(f"FAIL: {len(errors)} source errors exceeds threshold {args.fail_on_source_errors}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
