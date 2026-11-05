"""Tests for the SWE-bench adapter. No network / no model calls."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from eval.swebench.manifest import Instance, select_instances
from eval.swebench.patch import extract_patch
from eval.swebench.report import bootstrap_ci, summarize


def _git(args, cwd):
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        subprocess.run(["git", *args], cwd=cwd, check=True, stdout=out, stderr=err)


class ManifestTests(unittest.TestCase):
    def test_select_is_stratified_and_deterministic(self):
        rows = [
            Instance(f"a{i}", "org/a", f"c{i}", "p") for i in range(3)
        ] + [Instance(f"b{i}", "org/b", f"c{i}", "p") for i in range(3)]
        first = select_instances(rows, count=4, seed=0)
        second = select_instances(rows, count=4, seed=0)
        self.assertEqual([x.instance_id for x in first], [x.instance_id for x in second])
        self.assertEqual({x.repo for x in first}, {"org/a", "org/b"})
        self.assertEqual(len(first), 4)


class PatchTests(unittest.TestCase):
    def test_extract_patch_includes_new_file_but_not_pi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(["init"], root)
            _git(["config", "user.email", "test@example.com"], root)
            _git(["config", "user.name", "test"], root)
            (root / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
            _git(["add", "."], root)
            _git(["commit", "-m", "base"], root)

            (root / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            (root / "new.py").write_text("print('new')\n", encoding="utf-8")
            (root / ".pi").mkdir()
            (root / ".pi" / "mcp.json").write_text("{}", encoding="utf-8")

            patch = extract_patch(root)
            self.assertIn("app.py", patch)
            self.assertIn("new.py", patch)
            self.assertNotIn(".pi/mcp.json", patch)


class ReportTests(unittest.TestCase):
    def test_summary_and_ci(self):
        predictions = [
            {"instance_id": "a", "model_patch": "x"},
            {"instance_id": "b", "model_patch": ""},
        ]
        results = {"resolved_instances": ["a"], "unresolved_instances": ["b"]}
        meta = [{"instance_id": "a", "summary": {"tokens": 10, "cost_usd": 0.1}}]
        summary = summarize(predictions, results, meta)
        self.assertEqual(summary["resolved"], 1)
        self.assertAlmostEqual(summary["resolved_rate"], 0.5)
        self.assertAlmostEqual(summary["apply_rate"], 1.0)
        self.assertEqual(summary["empty_patch"], 1)
        low, high = bootstrap_ci([1, 0])
        self.assertLessEqual(low, high)


if __name__ == "__main__":
    unittest.main()
