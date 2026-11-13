"""用手算值核对随手册和 AI 资料分发的功率台架统计示例。"""

from math import sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis import AnalysisRunner, load_analysis_plan
from example_result_contracts import power_statistics_expected, verify_power_statistics_publication


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "Docs/Current/examples/power-statistics.yaml"


class PowerStatisticsTeachingTest(unittest.TestCase):
    """让两个公开后端读取可下载的 ASC 与 DBC，核对文档给出的总体与数值。"""

    def test_downloaded_power_example(self):
        """核对计算及聚合的真实来源。参数：无。返回：无。异常：示例或文档值不符则失败。"""
        expected = {
            "readings": 5, "starts": 2, "loads": 2, "cycles": 1,
            "reading_variance": 80, "reading_spread": 8, "reading_rms": 10,
            "held_variance": 5000 / 81, "held_spread": sqrt(5000 / 81),
            "held_rms": sqrt(1100 / 9), "reading_median": 0, "reading_p95": 18,
        }
        plan = load_analysis_plan(PLAN)
        for backend in ("reference", "numpy"):
            with self.subTest(backend=backend), TemporaryDirectory(dir=ROOT / "work") as folder:
                with AnalysisRunner(backend).run(plan, work_dir=Path(folder) / "run") as result:
                    session_values = {}
                    starts = {event.event_id: event.start_ns for event in result.iter_events()
                              if event.rule_id == "loaded"}
                    load_means = {}
                    for row in result.iter_calculations():
                        self.assertEqual(row.status, "complete")
                        self.assertEqual(row.unit, 'W' if row.calculation_id == 'load_mean'
                                         else power_statistics_expected()[row.calculation_id][1])
                        if row.calculation_id == "load_mean":
                            load_means[starts[row.parent_id]] = row.value
                        else:
                            session_values[row.calculation_id] = row.value
                    self.assertEqual(session_values.keys(), expected.keys())
                    for name, value in expected.items():
                        self.assertAlmostEqual(session_values[name], value, msg=name)
                    self.assertEqual(load_means, {1_000_000_000: 10, 5_000_000_000: 20})
                    group, = result.iter_aggregations()
                    self.assertEqual((group.aggregation_id, group.source_id, group.group_values),
                                     ("load_mean_p95", "load_mean", ("power_bench",)))
                    self.assertEqual((group.value, group.unit, group.status), (19.5, "W", "complete"))
                    self.assertEqual((group.candidate_count, group.included_count,
                                      group.definition_excluded_count, group.quality_excluded_count),
                                     (2, 2, 0, 0))
                    self.assertTrue(group.discovery_complete)
                    publication = result.write(Path(folder) / 'published')
                    verify_power_statistics_publication(publication.manifest_path)


if __name__ == "__main__":
    unittest.main()
