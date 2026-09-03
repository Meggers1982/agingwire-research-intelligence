"""The dashboard is plain JS reading JSON the Python writes.

Nothing but these tests connects the two, so a renamed field would fail silently
in the browser rather than in CI.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from agingwire_intel.dashboard import TEMPLATE, build_dashboard
from agingwire_intel.runs import build_run_document, index_entry
from tests.test_runs import PAYLOAD, SYNTHESIS


def dashboard_js() -> str:
    match = re.search(r"<script>(.*?)</script>", TEMPLATE.read_text(encoding="utf-8"), re.S)
    assert match, "dashboard template has no inline script"
    return match.group(1)


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = dashboard_js()
        cls.doc = build_run_document(PAYLOAD, SYNTHESIS)
        cls.entry = index_entry(cls.doc, PAYLOAD)

    def test_every_run_field_the_dashboard_reads_exists(self):
        used = set(re.findall(r"\brun\.([a-z_]+)", self.js))
        self.assertTrue(used, "no run fields found; the regex needs updating")
        self.assertEqual(sorted(f for f in used if f not in self.doc), [])

    def test_every_item_field_the_dashboard_reads_exists(self):
        used = set(re.findall(r"\bi(?:tem)?\.([a-z_0-9]+)", self.js))
        item = self.doc["items"][0]
        self.assertEqual(sorted(f for f in used if f not in item), [])

    def test_every_index_entry_field_the_dashboard_reads_exists(self):
        used = set(re.findall(r"\br\.([a-z_]+)", self.js))
        self.assertEqual(sorted(f for f in used if f not in self.entry), [])

    def test_run_document_is_json_serializable(self):
        json.dumps(self.doc, ensure_ascii=False)

    def test_dashboard_fetches_the_paths_the_pipeline_writes(self):
        self.assertIn('fetch("data/index.json")', self.js)
        self.assertIn("data/runs/", self.js)

    def test_export_and_jump_targets_are_wired(self):
        for anchor in ("feature-pitch", "story-ideas", "trends", "clusters",
                       "opportunities", "health"):
            self.assertIn(f'id="{anchor}"', TEMPLATE.read_text(encoding="utf-8"), anchor)
        self.assertIn("export-docx-btn", self.js)
        self.assertIn("export-csv-btn", self.js)

    def test_docx_library_is_lazy_loaded_from_vendor(self):
        self.assertIn('el.src = "vendor/docx-8.5.0.umd.js"', self.js)


class BuildDashboardTests(unittest.TestCase):
    def test_writes_the_template_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = build_dashboard(Path(tmp) / "index.html")
            self.assertEqual(out.read_text(encoding="utf-8"), TEMPLATE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
