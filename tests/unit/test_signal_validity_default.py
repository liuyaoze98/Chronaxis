"""核对信号周期三倍默认有效期，显式覆盖以及实际时间过期。

静态用例不读取DBC；运行用例复用独立三格式合成帧，按4000W乘有效时间
手算积分。只写测试专用临时目录，不接触历史快照；关闭结果后核资源清理。
"""

from configuration_fixtures import current_fixture

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner, explain_analysis_plan
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType
from chronaxis.legacy.records import LegacyCANField, field_to_dict
from chronaxis.planning.checks import PlanValidationError
from chronaxis.planning.signal_validity import declared_valid_for, triple_period
from chronaxis.execution.signal_validity import resolve_signal_validity
from chronaxis.execution.state import LatestSignalState
from chronaxis.results.budget import ResourceBudget
from test_analysis_plan import config_fixture
import test_record_runner as record_fixtures


class SignalValidityDefaultTests(unittest.TestCase):
    """默认值只取本信号的明确周期，未知周期不伪造时间或有效值。"""

    def test_explicit_period_and_validity_precedence(self):
        """100ms默认300ms，显式50ms覆盖；参数无，返回None，异常为断言失败。"""
        self.assertEqual(declared_valid_for({'period': '100ms'}, '$.s', dbc_available=True), 300_000_000)
        self.assertEqual(declared_valid_for({'period': '100ms', 'valid_for': '50ms'}, '$.s', dbc_available=True), 50_000_000)
        self.assertEqual(declared_valid_for({'period': '10ms'}, '$.s', dbc_available=False), 30_000_000)
        self.assertIsNone(declared_valid_for({}, '$.s', dbc_available=True))

    def test_invalid_null_missing_and_overflow_do_not_fall_back(self):
        """空值、无周期及三倍溢出均拒绝；参数无，返回None，异常为断言失败。"""
        for raw in ({}, {'valid_for': None}, {'period': None}, {'period': '0s'},
                    {'period': '-1s'}, {'period': '0s', 'valid_for': '1s'}):
            with self.subTest(raw=raw), self.assertRaises(PlanValidationError):
                declared_valid_for(raw, '$.s', dbc_available=False)
        with self.assertRaises(PlanValidationError):
            triple_period((1 << 63) // 3 + 1, '$.s')

    def test_memory_period_is_static_and_missing_period_is_actionable(self):
        """已解码信号可显式周期，无依据报补填；参数无，返回None，异常为断言失败。"""
        raw = config_fixture()
        signal = raw['signals'][0]
        signal.pop('valid_for')
        signal['period'] = '100ms'
        with patch('builtins.open', side_effect=AssertionError('静态检查不得读取文件')):
            plan = AnalysisPlan.from_dict(current_fixture(raw))
            self.assertEqual(plan.signals[0].definition.valid_for_ns, 300_000_000)
        del signal['period']
        with self.assertRaisesRegex(PlanValidationError, 'period或valid_for'):
            AnalysisPlan.from_dict(current_fixture(raw))

    def test_runtime_metadata_resolves_once_without_mutating_declaration(self):
        """只复用已提供的周期，原声明仍为待查；参数无，返回None，异常为断言失败。"""
        field = LegacyCANField(0, 'Voltage', 256)
        definition = SignalDefinition('voltage', 'bus', field.key, SignalDType.FLOAT64, 'V', None)
        cursor = SimpleNamespace(metadata={'fields': [{'locator': field_to_dict(field), 'cycle_ns': 100_000_000}]})
        with patch('builtins.open', side_effect=AssertionError('补全不得重新读取DBC')):
            result = resolve_signal_validity((definition,), {'bus': cursor})
        self.assertEqual(result[0].valid_for_ns, 300_000_000)
        self.assertIsNone(definition.valid_for_ns)
        with self.assertRaisesRegex(ValueError, 'period或valid_for'):
            resolve_signal_validity((definition,), {})
        # 未解析定义不能被底层状态误当成无限有效期。
        budget = ResourceBudget()
        with self.assertRaisesRegex(ValueError, '有效期'):
            LatestSignalState(budget, (definition,), 'session')
        self.assertEqual(budget.ram_bytes, 0)


class SignalValidityRunnerTests(unittest.TestCase):
    """同一DBC周期在三种原始格式、两后端产生相同实际有效期。"""

    setUp = record_fixtures.RecordRunnerTests.setUp
    asc = record_fixtures.RecordRunnerTests.asc
    csv = record_fixtures.RecordRunnerTests.csv
    blf = record_fixtures.RecordRunnerTests.blf
    fixtures = record_fixtures.RecordRunnerTests.fixtures
    plan = record_fixtures.RecordRunnerTests.plan

    def test_each_signal_uses_its_own_dbc_period(self):
        """电压100ms、电流10ms各自乘三；参数无，返回None，异常为断言失败。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 VoltageFrame: 1 Node\n SG_ Voltage : 0|8@1+ (2,0) [0|510] "V" Node\n'
            'BO_ 257 CurrentFrame: 1 Node\n SG_ Current : 0|8@1+ (1,0) [0|255] "A" Node\n'
            'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 100000;\n'
            'BA_ "GenMsgCycleTime" BO_ 256 100;\n'
            'BA_ "GenMsgCycleTime" BO_ 257 10;\n', encoding='utf-8')
        path = self.asc('0.00 1 100 Rx d 1 C8\n0.00 1 101 Rx d 1 0A\n'
                        '0.12 1 101 Rx d 1 0C\n0.30 1 101 Rx d 1 14\n').path

        def edit(raw):
            """给电流指定独立报文，均省略有效期。参数: 配置。返回: None。异常: 键错误。"""
            for signal in raw['signals']:
                signal.pop('valid_for')
                signal['field'].pop('message', None)
            raw['signals'][1]['field']['frame_id'] = 257

        for backend in ('reference', 'numpy'):
            plan = self.plan('can_asc', path, 'actual', edit)
            with AnalysisRunner(backend).run(plan, work_dir=self.root / uuid4().hex) as result:
                energy = next(row.value for row in result.iter_calculations() if row.calculation_id == 'energy')
                # V持续300ms，I每次只持续30ms：4000×.03+4800×.03=264J。
                self.assertAlmostEqual(energy, 264.0, places=6)

    def test_missing_dbc_cycle_and_explicit_validity_override(self):
        """无周期提示补填，显式有效期无需周期；参数无，返回None，异常为断言失败。"""
        from chronaxis.results.errors import AnalysisError
        paths = self.fixtures()
        # 删除合成DBC中的周期属性，保留报文和信号定义。
        self.dbc.write_text('\n'.join(line for line in self.dbc.read_text(encoding='utf-8').splitlines()
                                      if not line.startswith('BA_')) + '\n', encoding='utf-8')

        def edit(raw):
            """省略有效期，保留合法最小绑定。参数: 合成配置。返回: None。异常: 键错误。"""
            for signal in raw['signals']:
                signal.pop('valid_for')
                signal['field'].pop('message', None)

        plan = self.plan('can_asc', paths['can_asc'], 'actual', edit)
        with self.assertRaisesRegex(AnalysisError, 'period|valid_for'):
            AnalysisRunner().run(plan, work_dir=self.root / uuid4().hex)

        def explicit(raw):
            """显式有效期覆盖默认周期。参数: 合成配置。返回: None。异常: 键错误。"""
            for signal in raw['signals']:
                signal['field'].pop('message', None)
                signal['valid_for'] = '1s'
                signal['period'] = '10ms'

        plan = self.plan('can_asc', paths['can_asc'], 'actual', explicit)
        import cantools
        # 同次来源仍只加载一个DBC；有效期不要求额外周期属性或二次读库。
        with patch('cantools.database.load', wraps=cantools.database.load) as load:
            with AnalysisRunner().run(plan, work_dir=self.root / uuid4().hex) as result:
                energy = next(row.value for row in result.iter_calculations() if row.calculation_id == 'energy')
                self.assertAlmostEqual(energy, 1344.0, places=3)
            self.assertEqual(load.call_count, 1)

    def test_three_formats_dbc_default_and_explicit_period(self):
        """DBC100ms默认300ms保持，手填10ms仅保持30ms；参数无，返回None，异常为断言失败。"""
        for kind, path in self.fixtures().items():
            for backend in ('reference', 'numpy'):
                for period, energy in ((None, 1344.0), ('10ms', 264.0)):
                    def edit(raw):
                        """只改信号有效期声明。参数: 合成配置。返回: None。异常: 夹具键错误。"""
                        for signal in raw['signals']:
                            signal.pop('valid_for')
                            signal['field'].pop('message', None)
                            if period is not None:
                                signal['period'] = period
                    with self.subTest(kind=kind, backend=backend, period=period):
                        plan = self.plan(kind, path, 'actual', edit)
                        # explain不把待查DBC的有效期冒充已知常数。
                        explained = explain_analysis_plan(plan)
                        self.assertEqual(explained.history_ns['voltage'], None if period is None else 30_000_000)
                        with AnalysisRunner(backend).run(plan, work_dir=self.root / uuid4().hex) as result:
                            rows = {row.calculation_id: row for row in result.iter_calculations()}
                            self.assertAlmostEqual(rows['energy'].value, energy, places=3)


if __name__ == '__main__':
    unittest.main()
