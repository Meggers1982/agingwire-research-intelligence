import unittest

from agingwire_intel.http import BROWSER_UA, UA_FALLBACK_STATUS, USER_AGENT, headers


class HeaderTests(unittest.TestCase):
    def test_identifies_itself_by_default(self):
        self.assertIn("AgingWireResearchIntelligence", headers()["User-Agent"])

    def test_browser_ua_carries_no_bot_identifier(self):
        """ftc.gov 403s the moment the identifier is appended."""
        self.assertNotIn("AgingWire", BROWSER_UA)
        self.assertTrue(USER_AGENT.startswith(BROWSER_UA))

    def test_fallback_covers_waf_signatures(self):
        self.assertEqual(UA_FALLBACK_STATUS, {403, 405})

    def test_accept_header_is_overridable(self):
        self.assertEqual(headers("application/json")["Accept"], "application/json")


if __name__ == "__main__":
    unittest.main()
