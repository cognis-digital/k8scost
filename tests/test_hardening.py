"""Hardening tests: bad input, edge cases, and CLI error paths.

These complement the existing smoke tests without modifying them.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from k8scost.core import CostError, parse_cpu, parse_mem, parse_workloads  # noqa: E402
from k8scost import cli  # noqa: E402


class TestParseQuantityErrors(unittest.TestCase):
    """parse_cpu / parse_mem should raise CostError on garbage, not ValueError."""

    def test_parse_cpu_garbage(self):
        with self.assertRaises(CostError):
            parse_cpu("abc")

    def test_parse_cpu_suffix_garbage(self):
        with self.assertRaises(CostError):
            parse_cpu("notanumberm")

    def test_parse_mem_garbage(self):
        with self.assertRaises(CostError):
            parse_mem("xyz")

    def test_parse_mem_suffix_garbage(self):
        with self.assertRaises(CostError):
            parse_mem("notanumberMi")


class TestParseWorkloadsEdgeCases(unittest.TestCase):
    """parse_workloads should raise CostError, not crash, on bad structure."""

    def test_workloads_key_is_null(self):
        with self.assertRaises(CostError):
            parse_workloads({"workloads": None})

    def test_items_key_is_not_list(self):
        with self.assertRaises(CostError):
            parse_workloads({"items": "not-a-list"})

    def test_replicas_non_integer(self):
        bad = {"workloads": [
            {"name": "x", "replicas": "bad", "containers": [{"name": "c", "cpu_request": "100m"}]}
        ]}
        with self.assertRaises(CostError):
            parse_workloads(bad)

    def test_empty_list(self):
        with self.assertRaises(CostError):
            parse_workloads([])

    def test_non_dict_item_in_list(self):
        with self.assertRaises(CostError):
            parse_workloads([42])

    def test_malformed_cpu_propagates_as_cost_error(self):
        """A bad cpu_request inside a workload must surface as CostError."""
        bad = {"workloads": [
            {"name": "x", "containers": [{"name": "c", "cpu_request": "!!bad!!"}]}
        ]}
        with self.assertRaises(CostError):
            parse_workloads(bad)


class TestCLIEdgeCases(unittest.TestCase):
    """CLI entry-point hardening."""

    def _write_json(self, obj) -> str:
        fh = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(obj, fh)
        fh.close()
        return fh.name

    def tearDown(self):
        # nothing to do — tmp files are OS-cleaned
        pass

    def test_missing_file_returns_2(self):
        rc = cli.main(["analyze", "/no/such/file.json"])
        self.assertEqual(rc, 2)

    def test_malformed_json_returns_2(self):
        fh = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        fh.write("{this is not json}")
        fh.close()
        rc = cli.main(["analyze", fh.name])
        self.assertEqual(rc, 2)
        os.unlink(fh.name)

    def test_negative_cpu_price_returns_2(self):
        demo = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "demos", "01-basic", "workloads.json",
        )
        rc = cli.main(["--cpu-price", "-0.01", "analyze", demo])
        self.assertEqual(rc, 2)

    def test_negative_mem_price_returns_2(self):
        demo = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "demos", "01-basic", "workloads.json",
        )
        rc = cli.main(["--mem-price", "-1", "analyze", demo])
        self.assertEqual(rc, 2)

    def test_empty_workloads_array_returns_1(self):
        path = self._write_json([])
        rc = cli.main(["analyze", path])
        self.assertEqual(rc, 1)
        os.unlink(path)

    def test_workloads_null_value_returns_1(self):
        path = self._write_json({"workloads": None})
        rc = cli.main(["analyze", path])
        self.assertEqual(rc, 1)
        os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
