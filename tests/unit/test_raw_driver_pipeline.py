"""将三格式实际解码更新贯通同刻归组、最新状态、表达式和周期积分。

测试只创建合成DBC与原始文件，不启动公开尚未接线的schema2 AnalysisRunner。
同刻归组无磁盘历史；所有读取完成并关闭后才交付最后组和最终数值。
"""

from configuration_fixtures import current_fixture

from copy import deepcopy
from dataclasses import replace
from itertools import product
import unittest
from chronaxis import AnalysisPlan
from chronaxis.core.expression import validate_expression
from chronaxis.core.models import Interval
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
from chronaxis.execution.state import LatestSignalState
from chronaxis.execution.driver_expression import DriverExpression
from chronaxis.execution.raw_signal_groups import RawSignalGroups
from chronaxis.execution.record_integral import RecordIntegral
from chronaxis.execution.record_time_calculation import RecordTimeCalculation
from chronaxis.results.errors import BudgetExceededError, ResultClosedError
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.can_spec import LegacyCANField
from test_current_message_calculation import config, update
import test_raw_can_continuous as files


class RawDriverPipelineTests(unittest.TestCase):
    """相同手算880J用于所有格式及两种后端，不从某一实现复制预期。"""

    setUp = files.RawCANContinuousTests.setUp
    asc = files.RawCANContinuousTests.asc
    csv = files.RawCANContinuousTests.csv
    blf = files.RawCANContinuousTests.blf

    def plan(self, kind='can_blf'):
        """声明一个Frame中的电压电流及功率公式。参数: 格式。返回: AnalysisPlan。异常: 模型错误。"""
        raw = config(kind)
        voltage = raw['signals'][0]
        voltage.update(name='voltage', unit='V', conversion={'input_unit':'V'}, valid_for='1s')
        voltage['field']['signal'] = 'Voltage'
        current = deepcopy(voltage)
        current.update(name='current', unit='A', conversion={'input_unit':'A'})
        current['field']['signal'] = 'Current'
        raw['signals'].append(current)
        raw['message_calculations'][0]['expr'] = 'voltage * current * period * factor'
        raw['sources'][0]['dbc_by_channel'] = {'1': str(self.dbc.absolute())}
        return AnalysisPlan.from_dict(current_fixture(raw))

    def chain(self, plan, backend, operation='integral'):
        """组装借用关系并按反向顺序登记清理。参数: 计划/后端。返回: groups,integral,state。异常: 构造失败。"""
        state = LatestSignalState(self.budget, tuple(item.definition for item in plan.signals), 'session')
        self.addCleanup(state.close)
        driver = DriverExpression(validate_expression('voltage * current', plan.bindings), state, 'current', backend=backend)
        self.addCleanup(driver.close)
        factory = RecordIntegral if operation == 'integral' else RecordTimeCalculation
        integral = factory(self.budget, CalculationDefinition('calculation', operation, Interval(0, 300_000_000)),
            'W', D.FLOAT64, 100_000_000, backend=backend, batch_intervals=1,
            **({'work_dir': self.root} if operation == 'time_weighted_mean' else {}))
        self.addCleanup(integral.close)
        def consume(group):
            """先提交整个同刻组再求值。参数: 完整组。返回: None。异常: 任一阶段原错。"""
            state.apply(group)
            row = driver.evaluate()
            if driver.invalidated_at is not None:
                integral.expire_at(driver.invalidated_at)
            if row is not None:
                integral.consume((row,))
        groups = RawSignalGroups(self.budget, tuple(state.definitions.values()),
                                 'session', consume, backend=backend)
        self.addCleanup(groups.close)
        return groups, integral, state, driver

    def test_all_formats_and_backends_without_history(self):
        """三条帧功率4000/4800/8000W，两个固定周期合计880J，末条不加。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 2 Node\n SG_ Voltage : 0|8@1+ (2,0) [0|510] "V" Node\n'
            ' SG_ Current : 8|8@1+ (1,0) [0|255] "A" Node\n', encoding='utf-8')
        paths = {'can_blf': self.blf(((0., bytes([200, 10])), (.12, bytes([200, 12])), (.3, bytes([200, 20])))),
                 'can_asc': self.asc('0.00 1 100 Rx d 2 C8 0A\n0.12 1 100 Rx d 2 C8 0C\n0.30 1 100 Rx d 2 C8 14\n').path,
                 'raw_can_csv': self.csv('0,100,C8 0A,2\n0.12,100,C8 0C,2\n0.30,100,C8 14,2\n').path}
        for kind, path in paths.items():
            for backend, operation in product(('reference', 'numpy'), ('integral', 'time_weighted_mean')):
                plan = self.plan(kind)
                groups, integral, state, driver = self.chain(plan, backend, operation)
                if kind == 'can_blf':
                    spec = replace(plan.sources[0].config, path=path, paths=(path,), offset_ns=-1700000000 * 10**9)
                else:
                    # 文本配置的解析器拥有实际路径，沿计划的显式布局。
                    original = plan.sources[0].config
                    spec = replace(original, inputs=(replace(original.inputs[0], path=path),))
                factory = BudgetedLegacyCANSourceAdapter if kind == 'can_blf' else BudgetedTextCANSourceAdapter
                adapter = factory(self.budget, spec, 'session', tuple(state.definitions.values()),
                    work_dir=self.root / (kind + backend + operation), backend=backend, message_consumer=groups.consume,
                    **({'batch_read': True} if kind == 'can_blf' else {}))
                try:
                    read = adapter.iter_batches(ReadRequest('session', (), 0, 10**9, 1))
                    try:
                        for batch in read:
                            self.assertFalse(batch.series)
                    finally:
                        read.close()
                finally:
                    adapter.close()
                groups.finish()
                groups.finish()
                self.assertAlmostEqual(integral.finish().value, 880. if operation == 'integral' else 4400., places=3)
                for owner in (groups, integral, driver, state):
                    owner.close()
                self.assertEqual(self.budget.ram_bytes, 0)

    def test_failure_does_not_finish_pending_group(self):
        """相关输入回退后不可发布剩余组，关闭不把未完成输入当EOF。"""
        plan = self.plan()
        groups, integral, state, driver = self.chain(plan, 'reference')
        first = replace(update(400., 0, time=10, field='Voltage'), values={'Voltage':400., 'Current':10.})
        groups.consume(first)
        self.assertEqual(state.revision, 0)
        with self.assertRaises(ValueError):
            groups.consume(replace(first, time_ns=9, sequence=1))
        with self.assertRaises(ResultClosedError):
            groups.finish()
        groups.close()
        self.assertEqual(state.revision, 0)

    def test_large_same_time_group_budget_and_missing_value(self):
        """无效更新照样进入组，预算不足先失败，不丢样本或暗中分组。"""
        plan = self.plan()
        groups, _, state, _ = self.chain(plan, 'numpy')
        first = replace(update(400., 0, time=0, field='Voltage'), values={'Voltage':400., 'Current':None})
        groups.consume(first)
        groups.finish()
        self.assertFalse(state.get('current').value.valid)
        groups, _, _, _ = self.chain(plan, 'numpy')
        self.budget.memory_budget_bytes = self.budget.ram_bytes + 1
        with self.assertRaises(BudgetExceededError):
            groups.consume(first)
        with self.assertRaises(ResultClosedError):
            groups.finish()

    def test_same_time_frames_across_calls_and_unrelated_frame(self):
        """不同物理帧同刻分次到达仍为同组，无关帧不触发交付或时间检查。"""
        plan = self.plan()
        voltage = plan.signals[0].definition
        current = replace(plan.signals[1].definition,
            field=LegacyCANField(0, 'Current', 257, False, False).key)
        groups_seen = []
        groups = RawSignalGroups(self.budget, (voltage, current), 'session', groups_seen.append)
        self.addCleanup(groups.close)
        groups.consume(update(400., 0, time=0, field='Voltage'))
        # 这两个consume可来自相邻读取批或连续文件；中间不能调用全会话finish。
        groups.consume(replace(update(10., 1, time=0, field='Current'), frame_id=257))
        groups.consume(replace(update(1., 2, time=None), frame_id=999))
        self.assertEqual(groups_seen, [])
        groups.consume(replace(update(12., 3, time=180_000_000, field='Current'), frame_id=257))
        self.assertEqual({row.name: row.value.value for row in groups_seen[0].samples}, {'voltage':400., 'current':10.})
        groups.finish()
        self.assertEqual([group.time_ns for group in groups_seen], [0, 180_000_000])
        groups_seen.clear()
        groups.close()
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_callback_failure_rejects_finalization(self):
        """下游失败后保原错误，不能再把末组当成正常完成发布。"""
        plan = self.plan()
        def fail(group):
            """模拟下游失败。参数: 借用组。返回: 无。异常: OSError。"""
            raise OSError('consumer failed')
        groups = RawSignalGroups(self.budget, tuple(item.definition for item in plan.signals), 'session', fail)
        self.addCleanup(groups.close)
        groups.consume(update(400., 0, time=0, field='Voltage'))
        with self.assertRaisesRegex(OSError, 'consumer failed'):
            groups.finish()
        with self.assertRaises(ResultClosedError):
            groups.finish()
        groups.close()
        self.assertEqual(self.budget.ram_bytes, 0)
