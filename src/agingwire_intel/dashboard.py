from __future__ import annotations

from pathlib import Path

TEMPLATE = Path(__file__).with_name("templates") / "dashboard.html"


def build_dashboard(path: str | Path = "docs/index.html") -> Path:
    """Copy the dashboard template into the published docs directory.

    The markup used to live as a single minified string literal inside this
    module, which made any edit a one-line diff of 3,000 characters.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    return destination
