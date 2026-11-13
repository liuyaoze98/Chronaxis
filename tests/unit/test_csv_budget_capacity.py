"""用默认公开配置及实际跨批输入检查 CSV 容量，不把 batch_rows 当预分配量。"""

from pathlib import Path
from sys import getsizeof
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core import SignalDefinition, TimebaseSpec, TimeType
from chronaxis.core.types import QualityFlag, SignalDType
from chronaxis.execution.csv_reader import BudgetedSignalCSVSourceAdapter, _CSVResources
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest, SourceReadError
from chronaxis.sources.csv_spec import SignalCSVSpec


class CSVCapacityTests(unittest.TestCase):
    """窄表默认容量、宽表提前交批及短引用多行均按真实结果验收。"""

    def test_default_public_integral_accepts_twenty_and_hundred_thousand_rows(self):
        """完整相邻区间积分为 100W 乘 N-1 秒，默认配置无需用户调小批次。

        参数: 无。返回: None。异常: 运行失败、默认值改变或手算积分不符时失败。
        """
        with TemporaryDirectory(prefix="chronaxis-csv-capacity-") as folder:
            root = Path(folder)
            for count in (20000, 100000):
                with self.subTest(count=count):
                    path = root / f"power-{count}.csv"
                    with path.open("w", encoding="utf-8", newline="") as stream:
                        stream.write("time,power\n")
                        stream.writelines(f"{index},100\n" for index in range(count))
                    config = dict(
                        config_version=4, dataset=dict(name="capacity"),
                        sources=[dict(name="table", source_type="signal_csv", path=str(path),
                                      time_column="time", time=dict(unit="s"))],
                        signals=[dict(name="power", source="table", field="power", dtype="float64",
                                      unit="W", valid_for="2s")],
                        calculations=[dict(name="energy", operation="integral", expr="power", unit="J")],
                    )
                    plan = AnalysisPlan.from_dict(config)
                    self.assertEqual(plan.execution.memory_budget_bytes, 256 * 1024 ** 2)
                    self.assertEqual(plan.execution.batch_rows, 65536)
                    with AnalysisRunner().run(plan, work_dir=root / f"result-{count}") as result:
                        rows = tuple(result.iter_calculations())
                        self.assertEqual(len(rows), 1)
                        self.assertEqual(rows[0].value, 100 * (count - 1))
                        self.assertEqual(rows[0].unit, "J")
                        self.assertEqual(rows[0].status, "complete")

    def test_wide_table_capacity_splits_preserve_same_time_across_files(self):
        """小预算提前交批仍保留所有列、同刻更新及跨文件序号。

        参数: 无。返回: None。异常: 漏样本、打乱顺序、费用或句柄未归还时失败。
        """
        with TemporaryDirectory(prefix="chronaxis-csv-wide-") as folder:
            root = Path(folder)
            paths = tuple(root / f"part-{part}.csv" for part in range(2))
            for part, path in enumerate(paths):
                with path.open("w", encoding="utf-8", newline="") as stream:
                    stream.write("time,a,b,c,d\n")
                    for index in range(part * 301, (part + 1) * 301):
                        stream.write(f"{index // 3},{index},{index + 1},{index + 2},{index + 3}\n")
            definitions = tuple(SignalDefinition(name, "table", name, SignalDType.INT64, "1", 2)
                                for name in ("a", "b", "c", "d"))
            spec = SignalCSVSpec("table", paths, TimebaseSpec("clock", TimeType.RELATIVE, "capacity"),
                                 "time", "ns")
            request = ReadRequest("session", tuple(item.name for item in definitions), None, None, 65536)
            for backend in ("reference", "numpy"):
                budget = ResourceBudget(2 * 1024 ** 2)
                adapter = BudgetedSignalCSVSourceAdapter(budget, spec, "session", definitions, backend=backend)
                collected = {name: [] for name in request.signal_names}
                batch_count = 0
                try:
                    for batch in adapter.iter_batches(request):
                        batch_count += 1
                        for name, column in batch.series.items():
                            collected[name].extend(zip(column.time_ns.tolist(), column.sequence.tolist(),
                                                       column.values.tolist(), column.valid.tolist()))
                    self.assertGreater(batch_count, 1)
                    for offset, name in enumerate(request.signal_names):
                        expected = [(index // 3, index, index + offset, True) for index in range(602)]
                        self.assertEqual(collected[name], expected)
                    self.assertFalse(adapter.handles)
                finally:
                    adapter.close()
                self.assertEqual(budget.ram_bytes, 0)

    def test_short_multiline_cell_does_not_pay_fixed_buffer_per_physical_line(self):
        """400 行引用单元格本身很小，不应按 400 个独立读取缓冲收费。

        参数: 无。返回: None。异常: 小记录被拒绝、解析改变或清理残留时失败。
        """
        with TemporaryDirectory(prefix="chronaxis-csv-multiline-") as folder:
            path = Path(folder) / "quoted.csv"
            path.write_text('time,power,note\n0,100,"' + 'x\n' * 400 + 'end"\n', encoding="utf-8")
            spec = SignalCSVSpec("table", (path,), TimebaseSpec("clock", TimeType.RELATIVE, "capacity"),
                                 "time", "s")
            definition = SignalDefinition("power", "table", "power", SignalDType.FLOAT64, "W", 2)
            budget = ResourceBudget(1024 ** 2)
            adapter = BudgetedSignalCSVSourceAdapter(budget, spec, "session", (definition,))
            try:
                batches = list(adapter.iter_batches(ReadRequest("session", ("power",), None, None, 65536)))
                self.assertEqual(sum(batch.sample_count for batch in batches), 1)
                column = batches[0].series["power"]
                self.assertEqual(column.values.tolist(), [100.0])
                self.assertEqual(column.source_ref[0].line_number, 402)
            finally:
                adapter.close()
            self.assertEqual(budget.ram_bytes, 0)

    def test_expanded_integer_capacity_quality_and_cancellation(self):
        """短指数和长整数按展开空间计费，精度/指数边界与取消清理仍沿原规则。

        参数: 无。返回: None。异常: 低估原整数、错误质量、边界放宽或退款残留时失败。
        """
        with TemporaryDirectory(prefix="chronaxis-csv-expanded-") as folder:
            path = Path(folder) / "numbers.csv"
            definition = SignalDefinition("power", "table", "power", SignalDType.FLOAT64, "W", 2)
            spec = SignalCSVSpec("table", (path,), TimebaseSpec("clock", TimeType.RELATIVE, "capacity"),
                                 "time", "s")
            texts = ("1e4095", "9" * 4096, str(2 ** 53 + 1))
            path.write_text("time,power\n" + "".join(f"{i},{texts[i % 3]}\n" for i in range(300)),
                            encoding="utf-8")
            expected = [QualityFlag.OVERFLOW, QualityFlag.OVERFLOW, QualityFlag.PRECISION_LOSS] * 100
            for backend in ("reference", "numpy"):
                budget = ResourceBudget(1024 ** 2)
                adapter = BudgetedSignalCSVSourceAdapter(budget, spec, "session", (definition,), backend=backend)
                original = _CSVResources.before_pack
                observed = []

                def check_original_storage(resources, pending, validator):
                    """在打包前用真实 Python int 大小独立核对原值存储费用。

                    参数: 原资源、缓冲和校验器。返回: 原打包预约结果。异常: 低估或原预算失败。
                    """
                    count = sum(len(rows) for rows in pending.values())
                    actual = sum(getsizeof(row[2]) for rows in pending.values() for row in rows)
                    self.assertGreaterEqual(resources._pending_cost, actual + count * 64)
                    observed.append(count)
                    return original(resources, pending, validator)

                try:
                    with patch.object(_CSVResources, "before_pack", check_original_storage):
                        quality = [int(q) for batch in adapter.iter_batches(
                            ReadRequest("session", ("power",), None, None, 65536))
                                   for q in batch.series["power"].quality]
                    self.assertEqual(quality, expected)
                    self.assertGreater(len(observed), 1)
                finally:
                    adapter.close()
                self.assertEqual(budget.ram_bytes, 0)

            for text in ("1e4096", "1e-4095", "1e4095"):
                path.write_text(f"time,power\n0,{text}\n", encoding="utf-8")
                budget = ResourceBudget(1024 ** 2)
                adapter = BudgetedSignalCSVSourceAdapter(budget, spec, "session", (definition,))
                baseline = budget.ram_bytes
                parse = adapter._parse_value

                def cancel_after_parse(raw, selected):
                    """真实展开整数后取消，确认已预约的费用仍由原 owner 清理。

                    参数: 原文本和声明。返回: 无。异常: KeyboardInterrupt 或原解析错误。
                    """
                    parse(raw, selected)
                    raise KeyboardInterrupt("expanded integer cancelled")

                try:
                    if text == "1e4095":
                        with patch.object(adapter, "_parse_value", cancel_after_parse):
                            with self.assertRaises(KeyboardInterrupt):
                                next(adapter.iter_batches(ReadRequest("session", ("power",), None, None, 65536)))
                    else:
                        with self.assertRaises(SourceReadError) as caught:
                            next(adapter.iter_batches(ReadRequest("session", ("power",), None, None, 65536)))
                        self.assertIsInstance(caught.exception.__cause__, ValueError)
                    self.assertEqual(budget.ram_bytes, baseline)
                    self.assertFalse(adapter.handles)
                finally:
                    adapter.close()
                self.assertEqual(budget.ram_bytes, 0)
