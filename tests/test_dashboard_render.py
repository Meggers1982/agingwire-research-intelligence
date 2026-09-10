"""Actually execute the dashboard script.

The rest of the dashboard tests read the template as text. That is how a
ReferenceError shipped to production under a green pipeline: nothing here had
ever run the code. This module renders a real run document through the real
script in Node and fails if anything throws or the page comes out empty.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from agingwire_intel.dashboard import TEMPLATE
from agingwire_intel.runs import write_run
from tests.test_runs import PAYLOAD, SYNTHESIS

HARNESS = Path(__file__).with_name("dashboard_harness.mjs")
NODE = shutil.which("node")


def render(template_text: str, storage: dict | None = None) -> str:
    """Run the template's inline script over a fixture run; return the page HTML.

    ``storage`` seeds localStorage first; the harness appends the final store
    as a trailing ``<!--storage {...}-->`` comment.
    """
    script = re.search(r'<script id="app">(.*?)</script>', template_text, re.S)
    assert script, "dashboard template has no inline script"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "script.js").write_text(script.group(1), encoding="utf-8")
        (root / "template.html").write_text(template_text, encoding="utf-8")
        # The real writer, so the fixture cannot drift from what the pipeline
        # actually publishes -- that drift is the failure this test exists for.
        write_run(PAYLOAD, SYNTHESIS, docs_dir=root)
        args = [NODE, str(HARNESS), str(root / "script.js"), str(root / "template.html"), str(root)]
        if storage is not None:
            (root / "storage.json").write_text(json.dumps(storage), encoding="utf-8")
            args.append(str(root / "storage.json"))
        result = subprocess.run(
            # The script fetches "data/index.json", so the harness resolves
            # relative URLs against the root, not the data directory.
            args,
            capture_output=True, text=True, timeout=60,
        )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or "harness failed with no output")
    return result.stdout


@unittest.skipIf(NODE is None, "node is not installed")
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render(TEMPLATE.read_text(encoding="utf-8"))

    def test_the_page_renders_without_throwing(self):
        self.assertGreater(len(self.html), 2000, "page rendered but is suspiciously small")

    def test_the_sections_a_reader_comes_for_are_present(self):
        for heading in ("Story Opportunities", "Outlets", "What This Run Does Not Tell You",
                        "Pipeline Health"):
            self.assertIn(heading, self.html, heading)

    def test_the_limits_panel_reports_how_publishers_are_watched(self):
        # The block whose const ordering took the whole dashboard down.
        self.assertIn("registry publishers", self.html)

    def test_a_story_idea_shows_what_is_at_stake(self):
        # The pitch said what changed and when to file it, never who it lands on.
        self.assertIn("Why it matters", self.html)
        self.assertIn("inspect one option", self.html)

    def test_the_run_headline_numbers_render(self):
        self.assertIn("evidence candidates", self.html)
        self.assertIn("confirmed coverage gaps", self.html)


def picked_status(html: str, url: str) -> str:
    """The option selected in one item's status picker."""
    start = html.index(f'data-status-for="{url}"')
    picker = html[start:html.index("</select>", start)]
    found = re.search(r'<option value="(\w*)" selected>', picker)
    return found.group(1) if found else ""


def final_storage(html: str) -> dict:
    return json.loads(re.search(r"<!--storage (.*)-->\s*$", html, re.S).group(1))


@unittest.skipIf(NODE is None, "node is not installed")
class StatusKeyTests(unittest.TestCase):
    """Editorial status is the one thing on this page a reader wrote. The v1 to
    v2 move must not orphan any of it, and must not destroy the original."""

    V1 = "agingwire:status:v1"
    V2 = "agingwire:status:v2"

    def render(self, storage):
        return render(TEMPLATE.read_text(encoding="utf-8"), storage)

    def test_a_v1_status_follows_its_item_through_url_drift(self):
        drifted = "http://www.example.org/a/?utm_source=newsletter&utm_medium=email#top"
        html = self.render({self.V1: json.dumps({drifted: "drafting"})})
        self.assertEqual(picked_status(html, "https://example.org/a"), "drafting")

    def test_migration_writes_v2_and_leaves_v1_untouched(self):
        v1 = json.dumps({"https://example.org/a": "pitched", "https://gone.example/x": "killed"})
        store = final_storage(self.render({self.V1: v1}))
        self.assertEqual(store[self.V1], v1, "v1 is the undo path and must survive")
        # An item no loaded run carries still migrates: nothing is dropped.
        self.assertEqual(json.loads(store[self.V2]),
                         {"example.org/a": "pitched", "gone.example/x": "killed"})

    def test_an_existing_v2_store_is_not_overwritten_by_v1(self):
        html = self.render({
            self.V1: json.dumps({"https://example.org/a": "drafting"}),
            self.V2: json.dumps({"example.org/a": "published"}),
        })
        self.assertEqual(picked_status(html, "https://example.org/a"), "published")

    def test_a_meaningful_query_parameter_still_separates_items(self):
        html = self.render({self.V1: json.dumps({"https://example.org/b?page=2": "killed"})})
        self.assertEqual(picked_status(html, "https://example.org/b"), "")


@unittest.skipIf(NODE is None, "node is not installed")
class HarnessFidelityTests(unittest.TestCase):
    """A smoke test that cannot fail is not a smoke test."""

    @staticmethod
    def _reintroduce_the_bug(template: str) -> str:
        """Put KIND_LABELS and kindSummary back inside renderMain, below the call.

        This is the original defect, not an approximation of it: both were
        declared beside the limits panel that reads them, while the
        pipeline-health block called kindSummary twenty-five lines earlier.
        """
        block_start = template.index("/* Naming the route")
        block_end = template.index("function renderItem(item, index) {")
        block = template[block_start:block_end]
        moved = template[:block_start] + template[block_end:]
        anchor = "  const loose = (media.kinds || {}).sitemap || 0;"
        assert anchor in moved, "the limits panel moved; this mutation needs updating"
        return moved.replace(anchor, "  " + block.strip() + "\n" + anchor, 1)

    def test_a_temporal_dead_zone_error_fails_the_render(self):
        broken = self._reintroduce_the_bug(TEMPLATE.read_text(encoding="utf-8"))
        with self.assertRaises(AssertionError) as caught:
            render(broken)
        # The exact browser error that shipped, rather than any error at all.
        self.assertIn("before initialization", str(caught.exception))
        self.assertIn("KIND_LABELS", str(caught.exception))

    def test_a_missing_element_fails_the_render(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        broken = template.replace('<main id="main">', '<main id="not-main">', 1)
        with self.assertRaises(AssertionError):
            render(broken)
