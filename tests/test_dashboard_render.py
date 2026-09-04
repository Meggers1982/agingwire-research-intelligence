"""Actually execute the dashboard script.

The rest of the dashboard tests read the template as text. That is how a
ReferenceError shipped to production under a green pipeline: nothing here had
ever run the code. This module renders a real run document through the real
script in Node and fails if anything throws or the page comes out empty.
"""
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


def render(template_text: str) -> str:
    """Run the template's inline script over a fixture run; return the page HTML."""
    script = re.search(r"<script>(.*?)</script>", template_text, re.S)
    assert script, "dashboard template has no inline script"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "script.js").write_text(script.group(1), encoding="utf-8")
        (root / "template.html").write_text(template_text, encoding="utf-8")
        # The real writer, so the fixture cannot drift from what the pipeline
        # actually publishes -- that drift is the failure this test exists for.
        write_run(PAYLOAD, SYNTHESIS, docs_dir=root)
        result = subprocess.run(
            # The script fetches "data/index.json", so the harness resolves
            # relative URLs against the root, not the data directory.
            [NODE, str(HARNESS), str(root / "script.js"), str(root / "template.html"), str(root)],
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

    def test_the_run_headline_numbers_render(self):
        self.assertIn("evidence candidates", self.html)
        self.assertIn("confirmed coverage gaps", self.html)


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
