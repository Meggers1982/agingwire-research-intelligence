import unittest

from agingwire_intel.collectors.rss import clean_summary


class CleanSummaryTests(unittest.TestCase):
    def test_strips_html_tags(self):
        self.assertEqual(clean_summary("<p>Older adults <b>gain</b> coverage</p>"),
                         "Older adults gain coverage")

    def test_decodes_common_entities(self):
        self.assertEqual(clean_summary("Medicare &amp; Medicaid &quot;rules&quot;"),
                         'Medicare & Medicaid "rules"')

    def test_collapses_whitespace(self):
        self.assertEqual(clean_summary("a\n\n  b\t c"), "a b c")

    def test_handles_empty_and_none(self):
        self.assertEqual(clean_summary(""), "")
        self.assertEqual(clean_summary(None), "")

    def test_leaves_plain_text_alone(self):
        self.assertEqual(clean_summary("Plain summary text."), "Plain summary text.")


if __name__ == "__main__":
    unittest.main()


class WebContextTests(unittest.TestCase):
    """Scraped link context becomes the story hook, so it must read as prose."""

    def setUp(self):
        from agingwire_intel.collectors.web import _clean_context
        self.clean = _clean_context

    def test_strips_the_repeated_headline(self):
        self.assertEqual(
            self.clean("Report Title — Older adults face rising costs", "Report Title"),
            "Older adults face rising costs",
        )

    def test_strips_a_leading_byline(self):
        self.assertEqual(
            self.clean("By Alicia H. Munnell September 2, 2026 Retirees rely on benefits", "T"),
            "Retirees rely on benefits",
        )

    def test_strips_a_bare_dateline(self):
        self.assertEqual(self.clean("September 2, 2026 Costs rose again", "T"), "Costs rose again")

    def test_returns_none_when_only_the_headline_remains(self):
        self.assertIsNone(self.clean("Report Title", "Report Title"))

    def test_keeps_prose_that_merely_starts_with_a_capital(self):
        self.assertEqual(self.clean("Older adults gained coverage", "T"), "Older adults gained coverage")
