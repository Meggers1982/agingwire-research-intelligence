import unittest

from agingwire_intel import outlets


class MatchingTests(unittest.TestCase):
    """Outlets are matched on what each publication says it covers.

    The CSV export had dropped Core Coverage, so matching previously ran on
    hand-written category guesses.
    """

    def test_matches_on_stated_coverage(self):
        names = [r["publisher"] for r in outlets.suggest(["caregiving"], "b2c", limit=5)]
        self.assertTrue(names)
        for row in outlets.suggest(["caregiving"], "b2c", limit=5):
            blob = f"{row['coverage']} {row['category']}".lower()
            self.assertTrue("caregiv" in blob or "aging" in blob or "dementia" in blob, row)

    def test_consumer_and_trade_draw_from_different_registries(self):
        consumer = {r["publisher"] for r in outlets.suggest(["workforce"], "b2c", limit=5)}
        trade = {r["publisher"] for r in outlets.suggest(["workforce"], "b2b", limit=5)}
        self.assertTrue(trade)
        self.assertFalse(consumer & trade)

    def test_excluded_publishers_are_dropped(self):
        first = outlets.suggest(["caregiving"], "b2c", limit=1)[0]["publisher"]
        again = outlets.suggest(["caregiving"], "b2c", limit=1, exclude={first})
        self.assertNotEqual(again[0]["publisher"], first)

    def test_exclusion_is_case_insensitive(self):
        first = outlets.suggest(["housing"], "b2b", limit=1)[0]["publisher"]
        again = outlets.suggest(["housing"], "b2b", limit=1, exclude={first.upper()})
        self.assertNotEqual(again[0]["publisher"], first)

    def test_unknown_topic_still_returns_strong_titles(self):
        """No suggestion is worse than a strong general one."""
        rows = outlets.suggest(["not_a_real_topic"], "b2c", limit=3)
        self.assertTrue(rows)
        for r in rows:
            self.assertIn(r["tier"], {"Tier 1", "Tier 2"})

    def test_missing_registry_returns_nothing_rather_than_raising(self):
        self.assertEqual(outlets.suggest(["caregiving"], "b2c", b2c_path="/nope.csv"), [])


class DescribeTests(unittest.TestCase):
    def test_carries_the_written_rationale(self):
        row = outlets.suggest(["caregiving"], "b2c", limit=1)[0]
        text = outlets.describe(row)
        self.assertIn(row["publisher"], text)
        self.assertIn(row["tier"], text)
        if row["rationale"]:
            self.assertIn(row["rationale"][:20], text)

    def test_rationale_can_be_suppressed(self):
        row = outlets.suggest(["caregiving"], "b2c", limit=1)[0]
        self.assertNotIn(".", outlets.describe(row, with_reason=False).split("—")[-1][-2:])


class CoveredByTests(unittest.TestCase):
    def test_reads_the_web_coverage_outlets(self):
        item = {"raw_metadata": {"web_coverage": {"outlets": ["Modern Healthcare", ""]}}}
        self.assertEqual(outlets.covered_by(item), {"Modern Healthcare"})

    def test_absent_web_coverage_is_empty(self):
        self.assertEqual(outlets.covered_by({}), set())


if __name__ == "__main__":
    unittest.main()
