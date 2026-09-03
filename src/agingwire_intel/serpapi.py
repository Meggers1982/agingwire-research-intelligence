from __future__ import annotations

import logging
import os
import time
from collections import Counter

import requests

log = logging.getLogger(__name__)

BASE = "https://serpapi.com/search"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 2

# One shared key serves trending-content, this repo and senior-research-digest.
# A per-run cap means a loop bug here cannot drain the month's quota for the
# other two; the run degrades instead of overspending.
DEFAULT_BUDGET = 40

FAILURES: Counter[str] = Counter()


class Budget:
    """Hard cap on SerpAPI calls for a single pipeline run."""

    def __init__(self, limit: int = DEFAULT_BUDGET) -> None:
        self.limit = limit
        self.used = 0

    def take(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def unavailable_reason() -> str | None:
    """Why SerpAPI cannot be used, or None if it can.

    A reason rather than a bare False, so "I set the key and nothing happened"
    is diagnosable from the run output — the same lesson as llm.py.
    """
    if not os.environ.get("SERPAPI_API_KEY", "").strip():
        return "SERPAPI_API_KEY is not set"
    return None


def available() -> bool:
    return unavailable_reason() is None


def search(params: dict, budget: Budget | None = None, timeout: int = DEFAULT_TIMEOUT,
           retries: int = DEFAULT_RETRIES) -> dict | None:
    """One SerpAPI call. Returns None on any failure rather than raising.

    Enrichment must never sink a run: the evidence is already collected by the
    time these are called.
    """
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        return None
    if budget is not None and not budget.take():
        FAILURES["budget exhausted"] += 1
        return None

    label = params.get("data_type") or params.get("engine") or "serpapi"
    payload = {**params, "api_key": key}
    for attempt in range(retries + 1):
        try:
            response = requests.get(BASE, params=payload, timeout=timeout)
            if response.status_code >= 500 and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            data = response.json()
        except requests.Timeout:
            if attempt < retries:
                continue
            FAILURES[f"{label} timeout"] += 1
            return None
        except Exception as exc:
            FAILURES[f"{label} error"] += 1
            log.warning("SerpAPI %s failed: %s", label, str(exc)[:160])
            return None

        # SerpAPI answers 200 with an {"error": ...} body for a bad query or a
        # spent quota, so status alone does not mean success.
        if isinstance(data, dict) and data.get("error"):
            FAILURES[f"{label}: {str(data['error'])[:60]}"] += 1
            log.warning("SerpAPI %s returned an error: %s", label, str(data["error"])[:160])
            return None
        return data
    return None


def failure_summary() -> list[dict]:
    return [{"reason": reason, "count": count} for reason, count in FAILURES.most_common(10)]


def reset_failures() -> None:
    FAILURES.clear()
