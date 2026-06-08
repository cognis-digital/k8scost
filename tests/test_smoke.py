"""Smoke tests for k8scost. No network. Run: python -m pytest tests/ -q
or: python tests/test_smoke.py
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from k8scost import (  # noqa: E402
    TOOL_NAME,
    TOOL_VERSION,
    PriceSheet,
    analyze,
    parse_workloads,
    summarize,
)
from k8scost.core import parse_cpu, parse_mem, CostError  # noqa: E402
from k8scost import cli  # noqa: E402

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "demos", "01-basic", "workloads.json")


class TestQuantities(unittest.TestCase):
    def test_cpu(self):
        self.assertEqual(parse_cpu("500m"), 500.0)
        self.assertEqual(parse_cpu("1"), 1000.0)
        self.assertEqual(parse_cpu(2), 2000.0)
        self.assertEqual(parse_cpu(None), 0.0)
        self.assertAlmostEqual(parse_cpu("1000000n"), 1.0)

    def test_mem(self):
        self.assertEqual(parse_mem("512Mi"), 512.0)
        self.assertEqual(parse_mem("1Gi"), 1024.0)
        self.assertEqual(parse_mem(None), 0.0)
        self.assertAlmostEqual(parse_mem("1024Ki"), 1.0)


class TestEngine(unittest.TestCase):
    def test_overprovision_detected(self):
        wls = parse_workloads(json.load(open(DEMO, encoding="utf-8")))
        self.assertEqual(len(wls), 3)
        reports = analyze(wls)
        api = next(r for r in reports if r["name"] == "api")
        # over-provisioned -> recommended cost lower than current
        self.assertGreater(api["monthly_savings"], 0)
        flags = api["containers"][0]["findings"]
        self.assertTrue(any("over-provisioned" in f for f in flags))
        # scaled by 3 replicas
        self.assertEqual(api["replicas"], 3)

    def test_underprovision_detected(self):
        wls = parse_workloads(json.load(open(DEMO, encoding="utf-8")))
        reports = analyze(wls)
        worker = next(r for r in reports if r["name"] == "worker")
        flags = worker["containers"][0]["findings"]
        self.assertTrue(any("under-provisioned" in f for f in flags))

    def test_missing_mem_limit(self):
        wls = parse_workloads(json.load(open(DEMO, encoding="utf-8")))
        reports = analyze(wls)
        cache = next(r for r in reports if r["name"] == "cache")
        flags = cache["containers"][0]["findings"]
        self.assertTrue(any("no memory limit" in f for f in flags))

    def test_summary(self):
        wls = parse_workloads(json.load(open(DEMO, encoding="utf-8")))
        summ = summarize(analyze(wls))
        self.assertEqual(summ["workloads"], 3)
        self.assertGreater(summ["total_monthly_cost"], 0)
        self.assertGreaterEqual(summ["potential_monthly_savings"], 0)

    def test_pricesheet(self):
        p = PriceSheet(cpu_core_hour=0.04, mem_gib_hour=0.005)
        # 1000m + 1024Mi for 730h
        self.assertAlmostEqual(p.cost(1000, 1024), 0.04 * 730 + 0.005 * 730, places=4)

    def test_raw_k8s_deployment(self):
        obj = {
            "kind": "Deployment",
            "metadata": {"name": "web", "namespace": "prod"},
            "spec": {
                "replicas": 2,
                "template": {"spec": {"containers": [
                    {"name": "web", "resources": {
                        "requests": {"cpu": "250m", "memory": "256Mi"},
                        "limits": {"cpu": "500m", "memory": "256Mi"}}}
                ]}},
            },
        }
        wls = parse_workloads(obj)
        self.assertEqual(wls[0].name, "web")
        self.assertEqual(wls[0].replicas, 2)
        self.assertEqual(wls[0].namespace, "prod")

    def test_bad_input(self):
        with self.assertRaises(CostError):
            parse_workloads(42)
        with self.assertRaises(CostError):
            parse_workloads({"workloads": [{"name": "x", "containers": []}]})


class TestCLI(unittest.TestCase):
    def test_version_constants(self):
        self.assertEqual(TOOL_NAME, "k8scost")
        self.assertTrue(TOOL_VERSION)

    def test_cli_json(self):
        rc = cli.main(["--format", "json", "analyze", DEMO])
        self.assertEqual(rc, 0)

    def test_cli_table(self):
        rc = cli.main(["analyze", DEMO, "--advise"])
        self.assertEqual(rc, 0)

    def test_cli_missing_file(self):
        rc = cli.main(["analyze", "/no/such/file.json"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
