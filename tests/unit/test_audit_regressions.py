"""验证外部审查确认的INI资源风险、事件诊断与公开错误提示。

使用合成INI和核心时间组，不读真实报文。指数测试在模块的format入口设置保护，
防止回归时真的分配巨大字符串；正常结果和拒绝报告仍通过公开迁移入口取得。
同时锁定观测域与int64末点的不变量，避免为不可达反例放宽产品契约。
"""
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from chronaxis import AnalysisPlan
from chronaxis.migration import import_legacy_ini
from chronaxis.migration import sclicer, start_end
from chronaxis.core.calculations import CalculationDefinition, CalculationSeries
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.temporal import ConditionTick, TemporalRule
from chronaxis.core.temporal_reference import ReferenceTemporalDetector
from chronaxis.core.temporal_numpy import NumpyTemporalDetector
from chronaxis.core.types import Truth as T, QualityFlag as Q, SignalDType as D
from chronaxis.core.conditional_time_reduction_reference import ReferenceConditionalTimeReduction
from chronaxis.core.conditional_time_reduction_numpy import NumpyConditionalTimeReduction
from test_legacy_import_sclicer import mapping_fixture
from test_legacy_import_start_end import mapping_fixture as start_mapping, ini_fixture

ROOT = Path(__file__).resolve().parents[2]


class AuditRegressionTests(unittest.TestCase):
    """核对审查修复和已排除反例；每次构造独立输入，不修改共享夹具。"""

    def test_extreme_ini_exponents_fail_without_fixed_expansion(self):
        """巨大正指数返回完整拒绝报告。参数: 无。返回: None。异常: 断言失败。"""
        # 即使修复被撤回也先在format处失败，不让测试本身触发十亿字符分配。
        with patch.object(sclicer, 'format', side_effect=AssertionError('禁止定点展开'), create=True), \
                patch.object(start_end, 'format', side_effect=AssertionError('禁止定点展开'), create=True):
            for field in ('pre_sec', 'post_sec'):
                content = ('[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\n'
                           + field + '=1E+999999999\n').encode()
                result = import_legacy_ini(content, mapping_fixture(), mode='sclicer_single', base_dir=ROOT)
                self.assertIsNone(result.plan)
                self.assertEqual(result.report.status, 'failed')
                self.assertTrue(any(x.code == 'invalid_duration' and x.path.endswith(field)
                                    for x in result.report.issues))
                self.assertEqual(result.original_ini, content)
            # 起止规则的超时走另一条转换路径，必须同样先拒绝再输出报告。
            result = import_legacy_ini(ini_fixture('1E+999999999'), start_mapping(),
                                       mode='sclicer_start_end', base_dir=ROOT)
            self.assertIsNone(result.plan)
            self.assertTrue(any(x.code == 'invalid_duration' for x in result.report.issues))

    def test_compact_seconds_preserve_units_rounding_and_unlimited_timeout(self):
        """指数表示保留原时长与不限时政策。参数: 无。返回: None。异常: 断言失败。"""
        with patch.object(sclicer, 'format', side_effect=AssertionError('禁止定点展开'), create=True), \
                patch.object(start_end, 'format', side_effect=AssertionError('禁止定点展开'), create=True):
            for raw, expected in (('1E-1', 100000000), ('0E+999999999', 0), ('1E-999999999', 0)):
                content = ('[TRIGGER_test]\nmode=single\nexpr=OBC_OpMod==2\npre_sec=' + raw + '\n').encode()
                result = import_legacy_ini(content, mapping_fixture(), mode='sclicer_single', base_dir=ROOT)
                self.assertIsNotNone(result.plan, result.report.to_dict())
                self.assertEqual(result.plan.windows[0].pre_ns, expected)
            for raw, expected in (('5E-9', 5), ('0E+999999999', None), ('-1E+999999999', None)):
                result = import_legacy_ini(ini_fixture(raw), start_mapping(), mode='sclicer_start_end', base_dir=ROOT)
                self.assertIsNotNone(result.plan, result.report.to_dict())
                self.assertEqual(result.plan.rules[0].start_end.timeout_ns, expected)
            # 正超时不能舍为零；小数舍入规则不因资源修复被放宽。
            result = import_legacy_ini(ini_fixture('1E-999999999'), start_mapping(),
                                       mode='sclicer_start_end', base_dir=ROOT)
            self.assertIsNone(result.plan)
            self.assertTrue(any(x.code == 'invalid_duration' for x in result.report.issues))

    def test_candidate_onset_quality_survives_batches_and_clock_modes(self):
        """起点点质量参与诊断且不改变区间。参数: 无。返回: None。异常: 断言失败。"""
        ticks = (ConditionTick(0, T.TRUE, point_state=T.UNKNOWN, point_quality=Q.MISSING,
                               diagnostic_quality=Q.STALE),
                 ConditionTick(10, T.TRUE), ConditionTick(20, T.FALSE, terminal=True))
        for record_clock in (False, True):
            for threshold in (0, 5):
                rule = TemporalRule('alarm', 'data', 'session', 'condition_duration', threshold)
                for size in (1, 2, 3):
                    outputs = []
                    for factory in (ReferenceTemporalDetector, NumpyTemporalDetector):
                        owner = factory(rule, 0, 20, record_clock=record_clock)
                        for start in range(0, len(ticks), size):
                            args = {'advances': (0, 10, 10)[start:start+size]} if record_clock else {}
                            owner.push(ticks[start:start+size], **args)
                        outputs.append(owner.finish())
                    self.assertEqual(*outputs)
                    event, = outputs[0]
                    confirmed = (10 if record_clock else 5) if threshold else 0
                    self.assertEqual((event.start_ns, event.confirmed_ns, event.end_ns), (0, confirmed, 20))
                    self.assertEqual(event.dependency_quality, Q.MISSING | Q.STALE)
                    self.assertEqual((event.quality, event.status), (Q.NONE, 'closed'))

    def test_diagnostic_resets_between_activities(self):
        """下一活动只含自己的诊断。参数: 无。返回: None。异常: 断言失败。"""
        ticks = (ConditionTick(0, T.TRUE, point_state=T.UNKNOWN, point_quality=Q.MISSING),
                 ConditionTick(10, T.FALSE),
                 ConditionTick(20, T.TRUE, point_state=T.UNKNOWN, point_quality=Q.STALE),
                 ConditionTick(30, T.FALSE, terminal=True))
        rule = TemporalRule('alarm', 'data', 'session', 'condition_duration')
        for factory in (ReferenceTemporalDetector, NumpyTemporalDetector):
            owner = factory(rule, 0, 30)
            for tick in ticks:
                owner.push((tick,))
            self.assertEqual(tuple(e.dependency_quality for e in owner.finish()), (Q.MISSING, Q.STALE))

    def test_observation_rejects_the_reported_unreachable_counterexample(self):
        """首末点不匹配观测域不能进入积分。参数: 无。返回: None。异常: 断言失败。"""
        value = ScalarValue(1.0, D.FLOAT64)
        with self.assertRaisesRegex(ValueError, '首末'):
            CalculationSeries(Interval(2, 8), (0, 10), (value, value), (True, True), 'W')

    def test_maximum_timestamp_remains_excluded_from_half_open_samples(self):
        """无deadline不改变半开末点样本计数。参数: 无。返回: None。异常: 断言失败。"""
        end = (1 << 63) - 1
        times = (end - 10, end)
        truth = ScalarValue(True, D.BOOL)
        series = CalculationSeries(Interval(*times), times, (truth, truth), (True, True),
                                   '1', conditions=(truth, truth))
        spec = CalculationDefinition('duration', 'duration', Interval(*times))
        for factory in (ReferenceConditionalTimeReduction, NumpyConditionalTimeReduction):
            owner = factory(spec, '1', D.BOOL)
            facts = owner.push(series, valid_until_ns=(None, None), condition_valid_until_ns=(None, None))
            self.assertEqual(facts.valid_sample_count, 1)
            self.assertEqual(owner.finish().value, 1e-8)

    def test_csv_error_names_the_public_delimiter(self):
        """错误指出实际字段。参数: 无。返回: None。异常: 断言失败。"""
        config = AnalysisPlan.from_dict(mapping_fixture()['analysis'], base_dir=ROOT).sources[0].config
        with self.assertRaisesRegex(ValueError, 'csv.delimiter'):
            replace(config, delimiter=';;')

    def test_frame_grid_error_names_the_dbc_mode(self):
        """不使用不存在的schema2概念。参数: 无。返回: None。异常: 断言失败。"""
        from ruamel.yaml import YAML
        path = ROOT / 'Docs/Current/examples/export-can-grid.yaml'
        config = YAML(typ='safe', pure=True).load(path.read_text(encoding='utf8'))
        config['outputs']['can_frames']['resampling']['period'] = {'mode': 'actual'}
        with self.assertRaises(ValueError) as caught:
            AnalysisPlan.from_dict(config, base_dir=path.parent)
        self.assertIn('period.mode必须为dbc', str(caught.exception))
        self.assertNotIn('schema2', str(caught.exception))
