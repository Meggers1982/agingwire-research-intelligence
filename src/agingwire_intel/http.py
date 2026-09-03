from __future__ import annotations

import time

import requests

# Several federal sites (ftc.gov behind Akamai in particular) reject the
# "Mozilla/5.0 (compatible; Bot/1.0)" form outright. One realistic browser
# UA is used for every collector so a fix in one place fixes all of them.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
# Preferred: say who we are and where to complain. Measured 2026-09-03, ftc.gov
# returns 200 for BROWSER_UA and 403 the moment this suffix is appended, so a
# 403 or 405 falls back to the bare browser string rather than losing the source.
# These are public feeds the publishers intend to be read. Note that some hosts
# (nia.nih.gov, seen from GitHub Actions) block by IP range, which no user agent
# can fix -- those surface as source errors in the health report.
USER_AGENT = (
    f"{BROWSER_UA} AgingWireResearchIntelligence/0.2 "
    "(+https://github.com/Meggers1982/agingwire-research-intelligence)"
)
HTML_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
FEED_ACCEPT = "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8"
JSON_ACCEPT = "application/json, */*;q=0.8"

RETRY_STATUS = {429, 500, 502, 503, 504}
# WAF signatures rather than honest answers: a GET on a public RSS feed does not
# legitimately return 405. Both are retried once with the bare browser UA.
UA_FALLBACK_STATUS = {403, 405}


def headers(accept: str = HTML_ACCEPT, user_agent: str = USER_AGENT) -> dict[str, str]:
    return {"User-Agent": user_agent, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"}


def get(
    url: str,
    *,
    accept: str = HTML_ACCEPT,
    params: dict | None = None,
    timeout: int = 30,
    retries: int = 2,
    backoff: float = 2.0,
    ua_fallback: bool = True,
) -> requests.Response:
    """GET with a browser UA and bounded retries on transient failures.

    Retries only 429/5xx and connection errors. A 403 or 404 is a real answer --
    retrying it just burns the workflow's time budget.
    """
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, headers=headers(accept), params=params, timeout=timeout)
            if response.status_code in RETRY_STATUS and attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            if response.status_code in UA_FALLBACK_STATUS and ua_fallback:
                retry = requests.get(
                    url, headers=headers(accept, BROWSER_UA), params=params, timeout=timeout
                )
                if retry.ok:
                    return retry
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status not in RETRY_STATUS:
                raise
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            raise
    raise last if last else RuntimeError(f"GET failed: {url}")


def get_json(url: str, *, params: dict | None = None, timeout: int = 45, retries: int = 2) -> dict | list:
    """GET JSON, raising a useful error when a site answers 200 with an HTML page.

    api.census.gov redirects keyless requests to an HTML "Missing Key" page and
    serves it with status 200, so raise_for_status() alone is not enough.
    """
    response = get(url, accept=JSON_ACCEPT, params=params, timeout=timeout, retries=retries)
    content_type = (response.headers.get("content-type") or "").lower()
    if "json" not in content_type and response.text.lstrip()[:1] in {"<", ""}:
        raise RuntimeError(
            f"Expected JSON from {response.url} but received {content_type or 'an empty body'} "
            f"(HTTP {response.status_code}). First 120 chars: {response.text[:120]!r}"
        )
    return response.json()


def post_json(url: str, payload: dict, *, timeout: int = 45) -> dict:
    response = requests.post(url, json=payload, headers={**headers(JSON_ACCEPT), "Content-Type": "application/json"}, timeout=timeout)
    response.raise_for_status()
    return response.json()
