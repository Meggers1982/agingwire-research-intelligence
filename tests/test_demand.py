import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from agingwire_intel import demand


def timeline(values, partial_tail=0):
    points = [{"values": [{"extracted_value": v}]} for v in values]
    for _ in range(partial_tail):
        points.append({"values": [{"extracted_value": 0}], "partial_data": True})
    return points


class TrendMathTests(unittest.TestCase):
    def test_rising_series_reports_positive_change(self):
        t = demand._trend_from_timeline(timeline([10] * 8 + [20] * 8), 0)
        self.assertEqual(t["change_pct"], 100.0)

    def test_falling_series_reports_negative_change(self):
        t = demand._trend_from_timeline(timeline([40] * 8 + [20] * 8), 0)
        self.assertEqual(t["change_pct"], -50.0)

    def test_partial_points_are_dropped(self):
        """A partial period is an incomplete count and reads as a crash."""
        with_partial = demand._trend_from_timeline(timeline([10] * 8 + [20] * 8, partial_tail=3), 0)
        without = demand._trend_from_timeline(timeline([10] * 8 + [20] * 8), 0)
        self.assertEqual(with_partial, without)

    def test_too_few_points_returns_nothing(self):
        self.assertIsNone(demand._trend_from_timeline(timeline([5] * 6), 0))

    def test_noise_floor_rejects_a_flat_near_zero_series(self):
        self.assertIsNone(demand._trend_from_timeline(timeline([1] * 8 + [2] * 8), 0))

    def test_zero_prior_does_not_produce_an_infinite_rise(self):
        t = demand._trend_from_timeline(timeline([0] * 8 + [30] * 8), 0)
        self.assertEqual(t["change_pct"], 0.0)

    def test_reads_the_right_series_for_a_batched_query(self):
        points = [{"values": [{"extracted_value": 10}, {"extracted_value": 50}]} for _ in range(16)]
        self.assertEqual(demand._trend_from_timeline(points, 1)["recent_mean"], 50.0)


class DemandScoreTests(unittest.TestCase):
    SNAPSHOT = {
        "caregiving": {"change_pct": 40.0},
        "housing": {"change_pct": 10.0},
        "falls": {"change_pct": 0.0},
        "sleep": {"change_pct": -40.0},
    }

    def test_unknown_topic_scores_neutral(self):
        """A missing snapshot must not reshape the ranking."""
        self.assertEqual(demand.demand_score(["nothing_known"], self.SNAPSHOT), 3)
        self.assertEqual(demand.demand_score([], {}), 3)

    def test_bands(self):
        self.assertEqual(demand.demand_score(["caregiving"], self.SNAPSHOT), 5)
        self.assertEqual(demand.demand_score(["housing"], self.SNAPSHOT), 4)
        self.assertEqual(demand.demand_score(["falls"], self.SNAPSHOT), 3)
        self.assertEqual(demand.demand_score(["sleep"], self.SNAPSHOT), 1)

    def test_takes_the_strongest_topic(self):
        self.assertEqual(demand.demand_score(["sleep", "caregiving"], self.SNAPSHOT), 5)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "demand.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        demand.save_cache({"caregiving": {"change_pct": 5.0}}, self.path)
        self.assertEqual(demand.load_cached(self.path)["topics"]["caregiving"]["change_pct"], 5.0)

    def test_expired_cache_is_ignored(self):
        demand.save_cache({"a": {}}, self.path)
        payload = json.loads(self.path.read_text())
        payload["fetched_at"] = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        self.path.write_text(json.dumps(payload))
        self.assertIsNone(demand.load_cached(self.path))

    def test_corrupt_cache_is_ignored(self):
        self.path.write_text("{not json")
        self.assertIsNone(demand.load_cached(self.path))

    def test_fresh_cache_avoids_a_fetch(self):
        demand.save_cache({"caregiving": {"change_pct": 5.0}}, self.path)
        with mock.patch.object(demand, "fetch_demand", side_effect=AssertionError("must not fetch")):
            topics, source = demand.get_demand(self.path)
        self.assertEqual(source, "cache")
        self.assertIn("caregiving", topics)

    def test_stale_cache_is_used_when_the_key_is_missing(self):
        """A month-old reading still separates rising from falling."""
        demand.save_cache({"caregiving": {"change_pct": 5.0}}, self.path)
        payload = json.loads(self.path.read_text())
        payload["fetched_at"] = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        self.path.write_text(json.dumps(payload))
        with mock.patch.dict("os.environ", {"SERPAPI_API_KEY": ""}, clear=False):
            topics, source = demand.get_demand(self.path)
        self.assertIn("caregiving", topics)
        self.assertIn("SERPAPI_API_KEY", source)

    def test_no_key_and_no_cache_is_empty_not_an_error(self):
        with mock.patch.dict("os.environ", {"SERPAPI_API_KEY": ""}, clear=False):
            topics, source = demand.get_demand(self.path)
        self.assertEqual(topics, {})
        self.assertIn("unavailable", source)


class FetchTests(unittest.TestCase):
    def test_batches_five_terms_per_call(self):
        taxonomy = {"topics": {f"t{i}": {"terms": [f"term {i}"]} for i in range(12)}}
        with mock.patch.object(demand.serpapi, "search", return_value=None) as search:
            demand.fetch_demand(taxonomy)
        self.assertEqual(search.call_count, 3)
        for call in search.call_args_list:
            self.assertLessEqual(len(call.args[0]["q"].split(",")), 5)

    def test_pins_geo_and_window_so_runs_are_comparable(self):
        taxonomy = {"topics": {"a": {"terms": ["aging"]}}}
        with mock.patch.object(demand.serpapi, "search", return_value=None) as search:
            demand.fetch_demand(taxonomy)
        params = search.call_args.args[0]
        self.assertEqual(params["geo"], "US")
        self.assertEqual(params["data_type"], "TIMESERIES")
        self.assertEqual(params["date"], demand.DATE_WINDOW)


if __name__ == "__main__":
    unittest.main()
