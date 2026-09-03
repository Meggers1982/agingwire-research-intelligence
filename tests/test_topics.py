import unittest

from agingwire_intel.topics import tag_text


class TopicTaggingTests(unittest.TestCase):
    def test_synonyms_expand_caregiving(self):
        tags = tag_text("New survey measures unpaid care and caregiver burden among older adults")
        self.assertIn("caregiving", tags)

    def test_assisted_living_and_quality(self):
        tags = tag_text("Resident satisfaction and assisted living quality vary across communities")
        self.assertIn("assisted_living", tags)
        self.assertIn("senior_living_quality", tags)

    def test_clinical_topics_from_existing_digest(self):
        tags = tag_text("Fall prevention and polypharmacy among people with mild cognitive impairment")
        self.assertIn("falls", tags)
        self.assertIn("polypharmacy", tags)
        self.assertIn("cognitive_decline", tags)


if __name__ == "__main__":
    unittest.main()
