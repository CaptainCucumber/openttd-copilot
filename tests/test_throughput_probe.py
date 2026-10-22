from pathlib import Path
import copy
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_throughput_probe as probe
from run_control_probe import ProbeError


def complete_run(index, observation=1.0, construction=2.0):
    return {
        "status": "passed",
        "observation": {"count": 10_000},
        "construction": {
            "built": 100, "readback_present": 100, "wrong_owner": 0,
            "cost": 9_000,
        },
        "metrics": {
            "observation_wall_seconds": observation,
            "observation_ticks": index,
            "construction_wall_seconds": construction,
            "construction_ticks": index + 1,
            "post_operation_hello_seconds": 0.01 * index,
            "admin_ping_seconds": 0.005 * index,
            "worst_concurrent_admin_ping_seconds": 0.004 * index,
            "worst_queued_hello_seconds": 0.02 * index,
            "max_gamescript_packet_bytes": 300 + index,
        },
    }


class ThroughputReportTests(unittest.TestCase):
    def test_five_run_summary_uses_median_and_nearest_rank_p95(self):
        runs = [complete_run(index, observation=float(index), construction=float(6 - index))
                for index in range(1, 6)]
        summary = probe.summarize_runs(runs)
        self.assertEqual(summary["run_count"], 5)
        self.assertEqual(summary["metrics"]["observation_wall_seconds"],
                         {"median": 3.0, "p95": 5.0})
        self.assertEqual(summary["metrics"]["construction_wall_seconds"],
                         {"median": 3.0, "p95": 5.0})
        self.assertEqual(probe.nearest_rank_p95([5, 1, 3, 2, 4]), 5)

    def test_summary_refuses_partial_unowned_or_over_budget_construction(self):
        for field, value in [("built", 99), ("readback_present", 99),
                             ("wrong_owner", 1), ("cost", 20_001)]:
            with self.subTest(field=field):
                run = complete_run(1)
                run["construction"][field] = value
                with self.assertRaises(ProbeError):
                    probe.summarize_runs([run])

    def test_summary_refuses_wrong_observation_count_and_invalid_metric(self):
        run = complete_run(1)
        run["observation"]["count"] = 9_999
        with self.assertRaises(ProbeError):
            probe.summarize_runs([run])
        run = complete_run(1)
        run["metrics"]["observation_wall_seconds"] = float("nan")
        with self.assertRaises(ProbeError):
            probe.summarize_runs([run])

    def test_summary_refuses_failed_run_instead_of_hiding_it(self):
        run = complete_run(1)
        run["status"] = "failed"
        with self.assertRaises(ProbeError):
            probe.summarize_runs([run])


if __name__ == "__main__":
    unittest.main()
