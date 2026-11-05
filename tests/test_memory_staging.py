from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.memory import MemoryStore
from harness.memory_locomo import Case, score_retrieval
from harness.memory_recall import format_recall
from harness.memory_staging import candidates_from_diff


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.tmp.name) / "store.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_diff_becomes_quarantined_with_source_uri(self):
        diff = {
            "operations": {
                "adds": [
                    {
                        "uri": "viking://user/default/memories/test.md",
                        "memory_type": "preferences",
                        "after": "The project uses python3 -m unittest discover -q.",
                    }
                ],
                "updates": [],
            }
        }
        rows = candidates_from_diff(diff, "repo:demo", self.store)
        self.assertEqual(len(rows), 1)
        record = rows[0]["result"]["record"]
        self.assertEqual(record["status"], "quarantined")
        self.assertEqual(record["viking_source_uri"], "viking://user/default/memories/test.md")
        self.assertEqual(record["scope"], "repo:demo")
        self.assertEqual(record["kind"], "preferences")

    def test_duplicate_source_is_skipped(self):
        diff = {
            "operations": {
                "adds": [
                    {
                        "uri": "viking://user/default/memories/one.md",
                        "memory_type": "fact",
                        "after": "fact one",
                    }
                ]
            }
        }
        candidates_from_diff(diff, "default", self.store)
        rows = candidates_from_diff(diff, "default", self.store)
        self.assertEqual(rows, [])


class RecallTests(unittest.TestCase):
    def test_prefers_rendered_context(self):
        block = format_recall({"rendered": "A remembered fact", "items": []})
        self.assertIn("A remembered fact", block)

    def test_formats_items_when_rendered_empty(self):
        block = format_recall({"rendered": "", "items": [{"content": "hello"}]})
        self.assertIn("hello", block)
        self.assertIn("<long_term_memory>", block)


class LocomoTests(unittest.TestCase):
    def test_recall_at_k(self):
        cases = [
            Case("1", [], "What is the test command?", "", ["unittest discover"]),
            Case("2", [], "What is the port?", "", ["1933"]),
        ]

        def search(query):
            if "test" in query:
                return [{"content": "use unittest discover"}]
            return [{"content": "unrelated"}]

        result = score_retrieval(cases, search, top_k=1)
        self.assertEqual(result["cases"], 2)
        self.assertEqual(result["hits"], 1)
        self.assertAlmostEqual(result["recall_at_k"], 0.5)


if __name__ == "__main__":
    unittest.main()
