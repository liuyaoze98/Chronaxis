"""检查内部列到记录的快速构造仍保留类型、质量、原码和公开拒绝边界。

先由实际打包器校验输入，再交付同刻组；独立断言观测值及无效原因。
测试只使用合成内存，不读日志，不用耗时断言代替行为验证。
"""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
import pickle
import unittest
from unittest.mock import patch

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.scalar import _scalar_from_validated_fields
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.batch_signal_groups import BatchSignalGroups
from chronaxis.execution.calculation_values import scalar_from_column, _scalar_from_validated_column
from chronaxis.execution.record_sample import RecordSample
from chronaxis.sources.packing import pack_decoded, pack_message_values
from chronaxis.results.budget import ResourceBudget


class InternalConstructionTests(unittest.TestCase):
    """当前运行新建的可信列可省重复校验，公共数据边界仍严格拒绝。"""

    def test_validated_columns_preserve_invalid_values_and_enum_raw_codes(self):
        """两种归一化后端均保留无效原因及枚举原码；不把占位零当正常值。"""
        numeric = SignalDefinition('current', 'table', 'raw', D.INT64, 'A', 10)
        enum = SignalDefinition('state', 'table', 'raw', D.ENUM, '1', 10,
                                choices=((0, 'off'), (7, 'on')), code_dtype=D.INT64, capture_code=True)
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                column = pack_message_values(numeric, (2**53+1, None, 2**65), backend)
                scalars = tuple(_scalar_from_validated_column(column, i) for i in range(3))
                self.assertEqual(scalars[0].value, 2**53+1)
                self.assertTrue(scalars[0].valid)
                self.assertEqual((scalars[1].value, scalars[1].quality), (None, Q.MISSING))
                self.assertFalse(scalars[2].valid)
                self.assertEqual(scalars[2].quality, Q.OVERFLOW)
                column = pack_message_values(enum, (7, 33), backend)
                first, second = (_scalar_from_validated_column(column, i) for i in range(2))
                self.assertEqual((first.value, first.labels, first.code.value), ('on', ('off', 'on'), 7))
                self.assertFalse(second.valid)
                self.assertTrue(second.code.valid)
                self.assertEqual(second.code.value, 33)
                self.assertEqual(pickle.loads(pickle.dumps(first)), first)

    def test_groups_use_owned_columns_without_reconstructing_validation_samples(self):
        """真实已校验列进入归组后不再执行逐样本模型检查；输出事实仍可公开重建。"""
        definition = SignalDefinition('power', 'table', 'raw', D.FLOAT64, 'W', 10)
        source = SourceRef('session', 'table', 'raw')
        column = pack_decoded(definition, ((0, 0, 100.), (1, 1, 'bad'), (2, 2, 200.)), source, 'reference')
        output, budget = [], ResourceBudget()
        groups = BatchSignalGroups(budget, (definition,), 'session', output.append)
        try:
            with patch.object(ScalarValue, '__post_init__', side_effect=AssertionError('重复标量校验')), \
                 patch.object(RecordSample, '__post_init__', side_effect=AssertionError('重复记录校验')):
                groups.consume(SimpleNamespace(series={'power': column}, watermark_ns=2))
                groups.finish()
            self.assertEqual([group.time_ns for group in output], [0, 1, 2])
            self.assertEqual(output[0].samples[0].value.value, 100.)
            invalid = output[1].samples[0].value
            self.assertFalse(invalid.valid)
            self.assertEqual(invalid.value, 'bad')
            for group in output:
                record = group.samples[0]
                value = record.value
                checked = ScalarValue(value.value, value.dtype, value.valid, value.quality, value.labels, value.code)
                self.assertEqual(RecordSample(record.name, record.time_ns, record.sequence, checked,
                                              record.unit, record.source_ref, record.enum_code), record)
        finally:
            output.clear()
            groups.close()
        self.assertEqual(budget.ram_bytes, 0)

    def test_public_constructors_and_column_extraction_still_reject_invalid_input(self):
        """外部非有限数、越界整数和不合法时间不因内部路径改变而接受。"""
        for value, dtype, error in ((float('inf'), D.FLOAT64, ValueError),
                                    (2**63, D.INT64, OverflowError), (True, D.INT64, TypeError)):
            with self.subTest(dtype=dtype, value=value), self.assertRaises(error):
                ScalarValue(value, dtype)
        import numpy as np
        malformed = SimpleNamespace(valid=[True], quality=[0], values=np.array([float('inf')]),
                                    dtype=D.FLOAT64, labels=(), code=None)
        with self.assertRaises(ValueError):
            scalar_from_column(malformed, 0)
        with self.assertRaises(TypeError):
            RecordSample('power', True, 0, ScalarValue(1., D.FLOAT64), 'W', SourceRef('s', 't', 'p'))
        scalar = _scalar_from_validated_fields(2., D.FLOAT64, partial=True)
        self.assertTrue(scalar.partial)
        with self.assertRaises(FrozenInstanceError):
            scalar.value = 3.
