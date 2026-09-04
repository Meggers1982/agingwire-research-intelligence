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

    def test_every_story_idea_field_the_dashboard_reads_exists(self):
        used = set(re.findall(r"\bidea\.([a-z_0-9]+)", self.js))
        idea = self.doc["story_ideas"][0]
        self.assertTrue(used, "no idea fields found; the regex needs updating")
        self.assertEqual(sorted(f for f in used if f not in idea), [])

    def test_every_index_entry_field_the_dashboard_reads_exists(self):
        used = set(re.findall(r"\br\.([a-z_]+)", self.js))
        self.assertEqual(sorted(f for f in used if f not in self.entry), [])

    def test_run_document_is_json_serializable(self):
        json.dumps(self.doc, ensure_ascii=False)

    def test_dashboard_fetches_the_paths_the_pipeline_writes(self):
        self.assertIn('fetch("data/index.json")', self.js)
        self.assertIn("data/runs/", self.js)

    def test_export_and_jump_targets_are_wired(self):
        for anchor in ("feature-pitch", "pitch-draft", "story-ideas", "trends",
                       "clusters", "opportunities", "outlets", "health"):
            self.assertIn(f'sectionBlock("{anchor}"', self.js, anchor)
            self.assertIn(f'href="#{anchor}"', self.js, anchor)
        self.assertIn("export-docx-btn", self.js)
        self.assertIn("export-csv-btn", self.js)

    def test_every_section_is_collapsible(self):
        """Sections are built by one helper; a hand-rolled block would skip
        the toggle, the persistence and the jump-link expand."""
        self.assertNotIn('<div class="section-block', self.js)
        self.assertIn("wireSectionToggles(main)", self.js)

    def test_collapsed_state_is_persisted(self):
        self.assertIn("COLLAPSE_KEY", self.js)
        self.assertIn("localStorage.setItem(COLLAPSE_KEY", self.js)

    def test_jump_links_expand_a_collapsed_target(self):
        """Jumping to a collapsed section must open it or the link looks broken."""
        self.assertIn("expandSection(target.closest", self.js)

    def test_toggle_is_a_real_button_with_aria(self):
        self.assertIn('type="button" class="section-toggle"', self.js)
        self.assertIn('aria-expanded=', self.js)
        self.assertIn('aria-controls=', self.js)

    def test_the_pitch_ships_with_the_analysis(self):
        """"Give me a good pitch idea, headlines, and the actual pitch" — the
        first two were there, the third had no field to arrive in."""
        self.assertIn("pitch_draft_raw", self.doc)
        self.assertIn("run.pitch_draft_raw", self.js)

    def test_ideas_can_lead_with_a_headline(self):
        idea = self.doc["story_ideas"][0]
        for field in ("headline", "angle", "outlets"):
            self.assertIn(field, idea)
        self.assertIn("idea.headline || idea.title", self.js)

    def test_items_carry_matched_outlets(self):
        """outlets.py has always had the prospecting data; the card never used it."""
        self.assertIn("outlets", self.doc["items"][0])
        self.assertIn("outlet_index", self.doc)

    def test_docx_library_is_lazy_loaded_from_vendor(self):
        self.assertIn('el.src = "vendor/docx-8.5.0.umd.js"', self.js)


class BuildDashboardTests(unittest.TestCase):
    def test_writes_the_template_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = build_dashboard(Path(tmp) / "index.html")
            self.assertEqual(out.read_text(encoding="utf-8"), TEMPLATE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


class DateFormatTests(unittest.TestCase):
    """US format for display; ISO stays internal for sorting and file lookup."""

    @classmethod
    def setUpClass(cls):
        cls.js = dashboard_js()

    def test_formatter_exists(self):
        self.assertIn("function fmtDate(", self.js)

    def test_no_raw_iso_slicing_remains_in_display(self):
        self.assertNotIn('(item.published_at || "").slice(0, 10)', self.js)
        self.assertNotIn('(idea.published_at || "").slice(0, 10)', self.js)

    def test_sidebar_run_cards_are_formatted(self):
        self.assertIn("fmtDate(r.run_date)", self.js)

    def test_csv_export_uses_us_format(self):
        """The standing rule covers spreadsheets, not just the page."""
        self.assertIn("fmtDate(i.published_at)", self.js)

    def test_docx_export_uses_us_format(self):
        self.assertIn("fmtDate(run.run_date)", self.js)

    def test_run_file_lookup_still_uses_the_iso_id(self):
        """Formatting the id would break the data/runs/<id>.json fetch."""
        self.assertIn("data/runs/${encodeURIComponent(id)}.json", self.js)


def _bodies(js: str, pattern: str = r"function\s+([\w$]*)\s*\([^)]*\)\s*\{"):
    """Yield (name, decl_start, body_start, body_end) for each function in js."""
    for match in re.finditer(pattern, js):
        depth, i = 0, match.end() - 1
        while i < len(js):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    yield match.group(1), match.start(), match.end(), i
                    break
            i += 1


def tdz_offenders(js: str) -> list[str]:
    """Find a hoisted helper called before a const it closes over is initialized.

    `function` declarations hoist and `const` bindings do not. A helper defined
    beside the code it serves can still be *called* from higher up the same
    function, and then reads a binding that has not been initialized yet. The
    read is indirect, so identifier order alone never shows it -- the call site
    is what has to be compared against the declaration.
    """
    offenders = []
    for _, _, outer_start, outer_end in _bodies(js):
        outer = js[outer_start:outer_end]
        nested = list(_bodies(outer))
        for name, _decl_start, body_start, body_end in nested:
            if not name:
                continue
            reads = set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", outer[body_start:body_end]))
            for const in re.finditer(r"(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=", outer):
                if const.group(1) not in reads:
                    continue
                for call in re.finditer(rf"\b{re.escape(name)}\s*\(", outer):
                    inside_own_body = body_start <= call.start() <= body_end
                    if inside_own_body or call.start() >= const.start():
                        continue
                    line = js[: outer_start + call.start()].count("\n") + 1
                    declared = js[: outer_start + const.start()].count("\n") + 1
                    offenders.append(
                        f"{name}() called on line {line} reads {const.group(1)}, "
                        f"declared on line {declared}"
                    )
    return sorted(set(offenders))


class TemporalDeadZoneTests(unittest.TestCase):
    """A blank page in the browser and a green pipeline in CI, without this."""

    def test_the_check_catches_the_shape_that_broke_the_dashboard(self):
        broken = """
        function renderMain() {
          const html = kindSummary(media);
          const KIND_LABELS = { rss: "a feed" };
          function kindSummary(m) { return KIND_LABELS.rss; }
        }
        """
        self.assertTrue(
            any("KIND_LABELS" in o for o in tdz_offenders(broken)),
            "the check would not have caught the original bug",
        )

    def test_a_helper_declared_after_its_reader_is_still_fine_at_module_scope(self):
        # COVERAGE_LABEL is read inside a function and declared at module scope
        # further down. That runs after the module is evaluated, so it is safe
        # and must not be reported.
        ok = """
        function facetsHtml() { return COVERAGE_LABEL.gap; }
        const COVERAGE_LABEL = { gap: "Gap" };
        """
        self.assertEqual(tdz_offenders(ok), [])

    def test_the_dashboard_has_none(self):
        self.assertEqual(tdz_offenders(dashboard_js()), [])


class MediaSummaryContractTests(unittest.TestCase):
    """The limits panel reports how each publisher is watched, not just how many."""

    def setUp(self):
        self.js = dashboard_js()
        self.summary = build_run_document(PAYLOAD, SYNTHESIS)["media_status_summary"]

    def test_every_media_field_the_dashboard_reads_exists(self):
        used = set(re.findall(r"\bmedia\.([a-z_]+)", self.js))
        self.assertTrue(used, "no media fields found; the regex needs updating")
        self.assertEqual(sorted(f for f in used if f not in self.summary), [])

    def test_every_route_the_pipeline_can_record_has_a_label(self):
        from agingwire_intel.media import KINDS
        labels = re.search(r"const KIND_LABELS = \{(.*?)\};", self.js, re.S).group(1)
        missing = [k for k in KINDS if f"{k}:" not in labels]
        self.assertEqual(missing, [], "a monitoring route would render as its raw key")
