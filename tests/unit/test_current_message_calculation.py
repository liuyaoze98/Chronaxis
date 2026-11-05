"""用手算和真实三格式小文件核共同累计；旧N次贡献不改成N−1记录对。"""

from configuration_fixtures import current_fixture

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, validate_analysis_plan, AnalysisRunner
from chronaxis.core.models import SourceRef, Interval
from chronaxis.core.types import QualityFlag as Q
from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
from chronaxis.legacy.updates import LegacyDecodedUpdate, LegacyUntimedUpdate
from chronaxis.legacy.sum import LegacySkipReason
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import ResultClosedError, BudgetExceededError, AnalysisError
from chronaxis.sources.models import ReadRequest
from test_plan_message_calculations import legacy_config
import test_raw_can_continuous as files


def config(kind='can_blf'):
    """同一个功率×周期公式仅改变输入格式。参数: kind。返回: schema2字典。异常: 无。"""
    raw = legacy_config()
    raw.update(config_version=4)
    raw['outputs'] = {'contributions': 'none'}
    raw['signals'][0]['dtype'] = 'float64'
    raw['signals'][0]['field'].update(signal='Power')
    raw['sources'][0]['source_type'] = kind
    if kind != 'can_blf':
        raw['sources'][0].pop('legacy_profile')
        raw['message_calculations'][0]['profile'] = 'can-text-v1'
        if kind == 'raw_can_csv':
            layout = {name: {'column': index} for index, name in enumerate(
                ('timestamp', 'frame_id', 'data', 'payload_length'), 1)}
            layout.update({name: {'fixed': value} for name, value in (
                ('channel', 0), ('is_rx', True), ('is_extended', False), ('is_fd', False), ('frame_kind', 'data'))})
            raw['sources'][0]['parser'] = {'time_format': 'numeric', 'id_base':16, 'layout': {'fields': layout}}
    return current_fixture(raw)


def update(value, sequence, *, time=None, field='Power'):
    """创建有明确来源和顺序的合成消息。参数: 数值/序号/时间/字段。返回: 更新。异常: 模型错误。"""
    cls = LegacyUntimedUpdate if time is None else LegacyDecodedUpdate
    return cls(time, 'bus', 0, 256, False, False, False, False,
               SourceRef('session', 'bus', field), sequence, sequence, {field: value})


class CurrentMessageCalculationTests(unittest.TestCase):
    """同一独立预期同时核参考和NumPy，检查失败清理及真实三格式输入。"""

    setUp = files.RawCANContinuousTests.setUp
    asc = files.RawCANContinuousTests.asc
    csv = files.RawCANContinuousTests.csv
    blf = files.RawCANContinuousTests.blf

    def owner(self, raw=None, backend='numpy', **options):
        """建立计划及计算器并登记关闭。参数: 配置/后端/选项。返回: plan, owner。异常: 原错误。"""
        plan = AnalysisPlan.from_dict(current_fixture(raw or config()))
        owner = CurrentMessageCalculation(plan.message_calculations[0], plan.sources, plan.bindings,
            'session', self.budget, backend=backend, **options)
        self.addCleanup(owner.close)
        return plan, owner

    def test_where_skip_reason_uses_only_current_message_active_inputs(self):
        """活动分支除零时未选输入缺失不改累计原因，切换后区分缺失与非有限。

        参数: 无。返回: None。异常: 任一后端的当前帧贡献、原因或质量与手算不符。
        """
        raw = config()
        raw['config_version'] = 4
        power = raw['signals'][0]
        power['conversion'] = {'input_unit': 'W'}
        alternate = deepcopy(power)
        alternate.update(name='other')
        alternate['field']['signal'] = 'Other'
        raw['signals'].append(alternate)
        raw['message_calculations'][0].update(expr='where(power > 0, power / 0, other)', unit='W')
        # 同批不同分支，并覆盖所选值正常时的无跳过记录。
        samples = ((2., None), (2., float('inf')), (0., None), (0., float('inf')), (0., 4.))
        updates = tuple(replace(update(value, i, time=i), values={'Power': value, 'Other': other})
                        for i, (value, other) in enumerate(samples))
        expected = [(LegacySkipReason.EVALUATION_ERROR, Q.DOMAIN_ERROR)] * 2 + [
            (LegacySkipReason.MISSING_INPUT, Q.MISSING), (LegacySkipReason.NONFINITE_INPUT, Q.NONFINITE),
            (None, Q.NONE)]
        for backend in ('reference', 'numpy'):
            details = []
            _, owner = self.owner(raw, backend, contribution_consumer=lambda row, quality:
                                  details.append((row.skip_reason, quality)))
            owner.consume(updates)
            self.assertEqual(details, expected)
            self.assertEqual(owner.snapshot().value, 4.)

    def test_formula_same_time_invalid_and_batch_boundaries(self):
        """三条4000W加一条缺值：每条乘0.1s，1200J；同刻和分批不丢贡献。"""
        for backend in ('reference', 'numpy'):
            for size in (1, 2, 4):
                with self.subTest(backend=backend, size=size):
                    _, owner = self.owner(backend=backend, batch_rows=size)
                    rows = tuple(update(value, i, time=0) for i, value in enumerate((4000., None, 4000., 4000.)))
                    for start in range(0, len(rows), size):
                        owner.consume(rows[start:start + size])
                    result = owner.snapshot()
                    self.assertEqual((result.value, result.evaluation_count, result.contribution_count), (1200., 4, 3))
                    self.assertEqual(result.skip_counts[LegacySkipReason.MISSING_INPUT], 1)
                    owner.close()
                    self.assertEqual(self.budget.ram_bytes, 0)

    def test_direction_and_no_value_carry(self):
        """正负只按本条原值分桶，零/缺值跳过，不取绝对值。"""
        for backend in ('reference', 'numpy'):
            for bucket, expected in (('positive', 400.), ('negative', -200.)):
                raw = config()
                raw['message_calculations'][0]['split_by_sign'] = dict(signal='power', bucket=bucket, value_policy='raw_decoded-v1')
                _, owner = self.owner(raw, backend)
                owner.consume(tuple(update(value, i) for i, value in enumerate((4000., None, -2000., 0.))))
                self.assertEqual(owner.snapshot().value, expected)
                self.assertEqual(owner.snapshot().contribution_count, 1)
                owner.close()
                self.assertEqual(self.budget.ram_bytes, 0)

    def test_empty_zero_skip_and_requested_contributions(self):
        """空、全跳过、有效零分开；贡献回调不影响汇总，不生成原帧副本。"""
        details = []
        _, owner = self.owner(contribution_consumer=lambda contribution, quality: details.append(contribution))
        owner.consume(())
        self.assertEqual(owner.snapshot().reason, 'no_evaluations')
        owner.consume((update(None, 0),))
        self.assertEqual(owner.snapshot().reason, 'all_skipped')
        owner.consume((update(0., 1),))
        self.assertEqual(owner.snapshot().value, 0.)
        self.assertEqual([item.value for item in details], [None, 0.])
        self.assertIsNone(details[0].update.values['Power'])

    def test_window_identity_and_failed_owner(self):
        """筛选实际半开时间；错来源和回退不能继续交付成功结果。"""
        _, owner = self.owner(domain=Interval(10, 20))
        owner.consume(tuple(update(100., i, time=t) for i, t in enumerate((9, 10, 19, 20))))
        self.assertEqual(owner.snapshot().value, 20.)
        with self.assertRaises(ValueError):
            owner.consume((update(100., 4),))
        with self.assertRaises(ResultClosedError):
            owner.snapshot()
        owner.close()
        self.assertEqual(self.budget.ram_bytes, 0)
        _, owner = self.owner()
        owner.consume((update(1., 2),))
        with self.assertRaises(ValueError):
            owner.consume((update(1., 1),))
        owner.close()
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_budget_and_callback_failures(self):
        """超预算或输出失败不交部分成功，关闭只退自有费用。"""
        def fail(_, quality):
            raise OSError('synthetic output failure')
        _, owner = self.owner(contribution_consumer=fail)
        with self.assertRaises(OSError):
            owner.consume((update(1., 0),))
        with self.assertRaises(ResultClosedError):
            owner.snapshot()
        owner.close()
        self.assertEqual(self.budget.ram_bytes, 0)
        _, owner = self.owner()
        self.budget.memory_budget_bytes = self.budget.ram_bytes
        with self.assertRaises(BudgetExceededError):
            owner.consume((update(1., 0),))
        owner.close()
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_three_real_formats(self):
        """同三条4000W原帧经真实解码，再进入同一累计组件，均为1200J。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 2 Node\n SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node\n', encoding='utf-8')
        paths = {'can_blf': self.blf(((0., bytes([160, 15])), (.12, bytes([160, 15])), (.3, bytes([160, 15])))),
                 'can_asc': self.asc('0.00 1 100 Rx d 2 A0 0F\n0.12 1 100 Rx d 2 A0 0F\n0.30 1 100 Rx d 2 A0 0F\n').path,
                 'raw_can_csv': self.csv('0,100,A0 0F,2\n0.12,100,A0 0F,2\n0.30,100,A0 0F,2\n').path}
        for kind, path in paths.items():
            for constant in (False, True):
                raw = config(kind)
                raw['sources'][0]['path'] = str(path.absolute())
                raw['sources'][0]['dbc_by_channel'] = {'1': str(self.dbc.absolute())}
                if constant:
                    raw['message_calculations'][0]['expr'] = 'factor'
                    raw['message_calculations'][0]['parameters']['factor'] = {'value': 400., 'unit': 'J'}
                    if kind == 'can_blf':
                        raw['sources'][0]['decode_scope'] = 'requested'
                plan, owner = self.owner(raw)
                factory = BudgetedLegacyCANSourceAdapter if kind == 'can_blf' else BudgetedTextCANSourceAdapter
                options = {'batch_read': True} if kind == 'can_blf' else {}
                adapter = factory(self.budget, plan.sources[0].config, 'session',
                    (() if constant else tuple(item.definition for item in plan.signals)), work_dir=self.root / ('read-' + kind + str(constant)),
                    message_consumer=lambda row: owner.consume((row,)),
                    message_keys=((0, 256, False, False),) if constant else (), **options)
                try:
                    read = adapter.iter_batches(ReadRequest('session', (), 0, 12 * 10**9, 2))
                    try:
                        for batch in read:
                            self.assertFalse(batch.series)
                    finally:
                        read.close()
                    self.assertEqual(owner.snapshot().value, 1200.)
                    self.assertEqual(owner.snapshot().evaluation_count, 3)
                finally:
                    adapter.close()
                    owner.close()
                self.assertEqual(self.budget.ram_bytes, 0)

    def test_current_static_contract_ready_and_old_version_rejected(self):
        """新文本逐消息接线可执行；旧schema不能静默得到新格式语义。"""
        for kind in ('can_asc', 'raw_can_csv'):
            plan = AnalysisPlan.from_dict(current_fixture(config(kind)))
            self.assertTrue(validate_analysis_plan(plan).execution_ready)
            raw = config(kind)
            raw.update(config_version=2)
            with self.assertRaises(ValueError):
                AnalysisPlan.from_dict(current_fixture(raw))

    def test_schema_preserves_current_formula_for_all_formats(self):
        """三种原帧格式使用同一公开配置，当前入口不依赖INI转换。"""
        import json
        from jsonschema import Draft202012Validator
        schema = json.loads(Path('Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        validator = Draft202012Validator(schema)
        for kind in ('can_blf', 'can_asc', 'raw_can_csv'):
            raw = config(kind)
            validator.validate(raw)
            plan = AnalysisPlan.from_dict(current_fixture(raw))
            self.assertEqual(plan.message_calculations[0].expr.text, 'power * period * factor')
            self.assertEqual(dict((p.name,p.value) for p in plan.message_calculations[0].parameters)['period'], .1)
            self.assertEqual(plan.message_calculations[0].profile,
                             'sclicer-functions-v1' if kind == 'can_blf' else 'can-text-v1')

    def test_combined_failure_and_empty_trigger_contract(self):
        """保消费者原错和释放副错；无值触发须有完整定位和实际消费者。"""
        from chronaxis.sources.can_updates import CANUpdateProjection, require_message_keys
        from types import SimpleNamespace
        for keys in (None, ((0, 256, False),), ((True, 256, False, False),), ((0, 2048, False, False),)):
            with self.assertRaises(ValueError):
                require_message_keys(keys)
        projection = CANUpdateProjection('bus', 'session', (), message_keys=((0, 256, False, False),))
        frame = SimpleNamespace(channel=0, arbitration_id=256, is_extended_id=False, is_fd=False,
                                is_remote_frame=False, is_error_frame=False)
        row = projection.build(frame, 1, {'unused': 99}, None)
        self.assertEqual(dict(row.values), {})
        self.assertIsNone(row.time_ns)
        frame.is_remote_frame = True
        self.assertIsNone(projection.build(frame, 2, {}, None))
        def fail(_, quality):
            raise OSError('primary callback')
        _, owner = self.owner(contribution_consumer=fail)
        release = self.budget.release_ram
        def fail_release(amount):
            if amount == owner._batch_cost:
                raise RuntimeError('secondary release')
            release(amount)
        with patch.object(self.budget, 'release_ram', side_effect=fail_release):
            with self.assertRaisesRegex(OSError, 'primary callback') as caught:
                owner.consume((update(1., 0),))
        self.assertTrue(any('RuntimeError' in note for note in caught.exception.__notes__))
        owner.close()
        self.assertEqual(self.budget.ram_bytes, 0)


if __name__ == '__main__':
    unittest.main()
