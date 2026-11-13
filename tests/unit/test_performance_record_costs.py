"""用未改的通用估算器核对记录快速费用，不把固定形状当成固定大小。

输入覆盖原生值、Unicode、变长诊断、枚举域、扩展引用与不同整数位宽。
纯内存构造，无输入读取；状态事务另由现役所有权/故障测试验证。
"""

from dataclasses import replace
import unittest
from unittest.mock import patch

from chronaxis.core.models import SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.history_records import estimate_record_bytes
from chronaxis.execution.record_sample import RecordSample
from chronaxis.results.codec import _estimate
from chronaxis.sources.csv_spec import CSVSourceRef

import test_audit_state_costs as state_cases
from chronaxis.execution.groups import DecodedTimeGroup


class RecordFeeTests(unittest.TestCase):
    """快速估算只省遍历，必须逐字节保持原费用规则。"""

    def assert_fee(self, record):
        """参数: 合法记录。返回: None。异常: 断言失败；以通用原规则独立计算。"""
        original = _estimate((record.name, record.time_ns, record.sequence, record.value,
                              record.unit, record.source_ref, record.enum_code)) * 16 + 4096
        self.assertEqual(estimate_record_bytes(record), original)

    def test_dynamic_values_and_integer_sizes(self):
        """参数: 无。返回: None。异常: 断言失败；同类型大小变化也必须完整计费。"""
        source = SourceRef('session', 'input', 'raw')
        values = (ScalarValue(0, D.INT64), ScalarValue((1 << 63) - 1, D.INT64),
                  ScalarValue((1 << 64) - 1, D.UINT64), ScalarValue(1.0, D.FLOAT64),
                  ScalarValue(True, D.BOOL), ScalarValue(1.0, D.FLOAT64, partial=True),
                  ScalarValue(None, D.FLOAT64, False, Q.MISSING),
                  ScalarValue('诊断' * 4000, D.FLOAT64, False, Q.DECODE_ERROR),
                  ScalarValue(float('nan'), D.FLOAT64, False, Q.NONFINITE))
        for value in values:
            for sequence in (0, 1 << 300):
                with self.subTest(dtype=value.dtype, sequence=sequence):
                    record = RecordSample('value', 0, sequence, value, 'A', source)
                    self.assert_fee(record)
                    self.assert_fee(replace(record, source_ref=SourceRef('session', 'input', '量' * 2000)))

    def test_extended_references_and_enum_keep_generic_rules(self):
        """参数: 无。返回: None。异常: 断言失败；扩展引用/枚举码不会误用普通固定布局。"""
        for width in (0, 4096):
            source = CSVSourceRef('session', 'input', 'raw', 'synthetic.csv', 2, '0', '0' * width + '1', False)
            record = RecordSample('value', 0, 0, ScalarValue(1.0, D.FLOAT64), 'A', source)
            self.assert_fee(record)
        enum = ScalarValue('on', D.ENUM, labels=('off', 'on'), code=ScalarValue(7, D.INT64))
        self.assert_fee(RecordSample('state', 0, 0, enum, '1', SourceRef('session', 'input', 'raw'), 1))

    def test_selected_unchanged_record_is_estimated_once_per_group(self):
        """参数: 无。返回: None。异常: 断言失败；实际保留值和费用仍由完整原规则核对。"""
        fixture = state_cases.StateCostCacheTests()
        definition = fixture.definition('current')
        state = fixture.state((definition,))
        try:
            sample = fixture.sample(definition, 0, 0, 1.0)
            with patch('chronaxis.execution.state.estimate_record_bytes', wraps=estimate_record_bytes) as estimate:
                state.apply(DecodedTimeGroup(0, (sample,)))
            self.assertEqual(estimate.call_count, 1)
            self.assertIs(state.get('current'), sample)
            fixture.assert_owned_cost(state)
        finally:
            fixture.doCleanups()
