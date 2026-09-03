import unittest

from agingwire_intel.collectors.federal_register import (
    AGING_SIGNAL,
    NOTICE_PREFIX,
    PEDIATRIC_ONLY,
    ROUTINE,
)


def kept(blob: str) -> bool:
    """Mirrors the collector's filters for title-level cases."""
    if ROUTINE.search(NOTICE_PREFIX.sub("", blob)):
        return False
    return not (PEDIATRIC_ONLY.search(blob) and not AGING_SIGNAL.search(blob))


class RoutineFilterTests(unittest.TestCase):
    def test_drops_paperwork_notices(self):
        for title in (
            "Agency Information Collection Activities: Submission for OMB Review",
            "30-Day Notice of Proposed Information Collection: Public Housing Reform",
            "60-Day Notice of Proposed Information Collection: Capital Advance Section 811",
            "Privacy Act of 1974; System of Records",
            "Sunshine Act Meetings",
        ):
            self.assertFalse(kept(title), title)

    def test_keeps_substantive_rules(self):
        for title in (
            "Medicare Program; Prospective Payment System for Skilled Nursing Facilities",
            "Fair Market Rents for the Housing Choice Voucher Program, Fiscal Year 2027",
            "Social Security Ruling, SSR 26-2p; Titles II and XVI",
        ):
            self.assertTrue(kept(title), title)


class PediatricGateTests(unittest.TestCase):
    def test_drops_a_medicaid_rule_that_is_only_about_children(self):
        """Medicaid tags as an aging topic, but CHIP pediatric rules are not our beat."""
        title = ("Medicaid Program; Prohibition on Federal Medicaid and Children's Health "
                 "Insurance Program Funding for Procedures Furnished to Children")
        self.assertFalse(kept(title))

    def test_keeps_a_rule_covering_both_children_and_older_adults(self):
        title = "Medicaid Home and Community-Based Services for children and older adults"
        self.assertTrue(kept(title))

    def test_keeps_an_age_neutral_housing_rule(self):
        """Requiring an explicit aging word discarded real senior-housing leads."""
        self.assertTrue(kept("Fair Market Rents for the Housing Choice Voucher Program"))

    def test_aging_signal_recognizes_the_common_forms(self):
        for phrase in ("older adults", "Medicare", "nursing facility", "long-term care",
                       "hospice", "assisted living", "Social Security", "caregivers", "dementia"):
            self.assertTrue(AGING_SIGNAL.search(phrase), phrase)


if __name__ == "__main__":
    unittest.main()
