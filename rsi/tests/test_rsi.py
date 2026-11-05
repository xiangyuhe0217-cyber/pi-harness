"""RSI adapter tests. No model calls."""

from __future__ import annotations

import json
import unittest

from rsi.gepa_optimizer import score_results


class RsiScoreTests(unittest.TestCase):
    def test_pass_and_cost_penalty(self):
        results = [
            {"task_id": "a", "status": "pass", "summary": {"tokens": 100, "cost_usd": 0.0, "blocked": 0}},
            {"task_id": "b", "status": "fail", "summary": {"tokens": 100, "cost_usd": 0.0, "blocked": 0}},
        ]
        summary = score_results(results)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["total"], 2)
        self.assertAlmostEqual(summary["pass_rate"], 0.5)
        self.assertGreaterEqual(summary["score"], 0.0)
        self.assertLessEqual(summary["score"], 0.5)

    def test_feedback_contains_status(self):
        results = [{"task_id": "a", "status": "pass", "summary": {}}]
        self.assertIn("a: status=pass", score_results(results)["feedback"])

    def test_dataset_paths_exist(self):
        with open("rsi/dataset.json", encoding="utf-8") as handle:
            data = json.load(handle)
        for path in data["dev"] + data["holdout"]:
            with open(path, encoding="utf-8") as handle:
                self.assertTrue(handle.read())


if __name__ == "__main__":
    unittest.main()
