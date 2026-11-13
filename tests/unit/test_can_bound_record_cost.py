"""验证同次CAN绑定复用与固定记录计费，保留公开结构边界及原预算金额。

仅构造合成已解码记录；不读日志或DBC、不启动进程、不生成工作产物。
费用以原通用估算公式独立比较，不以性能断言代替数值和类型检查。
"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chronaxis.execution.history import _metadata_bytes
from chronaxis.execution.text_can_reader import _record_metadata_bytes
from chronaxis.execution.message_delivery import deliver_message
from chronaxis.results.budget import ResourceBudget
from chronaxis.legacy.records import LegacyCANField, LegacyRawFrame
from chronaxis.sources.raw_can import RawCANRecord
from chronaxis.sources.text_can_decode import DecodedCANRecord
from chronaxis.sources.can_updates import CANUpdateProjection


class BoundCANRecordTests(unittest.TestCase):
    """同一绑定只复用字段语法；每次的值、位置、状态与费用继续检查。"""

    def raw(self):
        """建立合法原帧及定位。参数: 无。返回: RawCANRecord。异常: 构造合同失败。"""
        frame = LegacyRawFrame(0., 256, False, False, False, 0, 8, bytes(8),
                               False, True, False, False)
        return RawCANRecord(frame, 0, Path('test.blf'), None, 0, None, 'blf-v1', None)

    def test_internal_binding_reuse_keeps_public_parsing_and_value_checks(self):
        """内部已绑定键不重解析，外部键和内部未知键仍拒绝。

        参数: 无。返回: None。异常: 断言失败。
        """
        key = LegacyCANField(0, 'Power', 256).key
        args = ('bus', 0, 0, self.raw(), ((key, 1.),), 'decoded', (), ())
        expected = DecodedCANRecord(*args)
        with patch('chronaxis.sources.text_can_decode.can_field_from_key',
                   side_effect=AssertionError('must parse only at the external boundary')):
            actual = DecodedCANRecord._from_bound_values(*args, frozenset((key,)))
            self.assertEqual(actual, expected)
            with self.assertRaises(AssertionError):
                DecodedCANRecord(*args)
        with self.assertRaises(ValueError):
            DecodedCANRecord._from_bound_values(*args, frozenset())
        with self.assertRaises((TypeError, ValueError)):
            DecodedCANRecord('bus', 0, 0, self.raw(), (('not a field', 1.),), 'decoded')
        # 已绑定只免重复语法解析，不能让字符串值、重复键或非法状态混入。
        for values, status in ((((key, 'bad'),), 'decoded'),
                               (((key, 1.), (key, 2.)), 'decoded'),
                               (((key, 1.),), 'unknown')):
            with self.subTest(values=values, status=status):
                with self.assertRaises((TypeError, ValueError)):
                    DecodedCANRecord._from_bound_values('bus', 0, 0, self.raw(),
                        values, status, (), (), frozenset((key,)))

    def test_fixed_cost_equals_recursive_formula_for_all_native_values(self):
        """长文本、宽字段、重建值和大整数逐项保持原计费。

        参数: 无。返回: None。异常: 两种公式不等时断言失败。
        """
        values = (None, False, True, -(2**63), 2**64-1, 2**4096, -0.,
                  1.5, float('nan'), float('inf'))
        for width in (0, 1, 17):
            for raw_time in (None, '1.000000000', '时刻' * 2048):
                pairs = tuple((LegacyCANField(0, f'P{i}', 256).key, values[i % len(values)])
                              for i in range(width))
                raw = replace(self.raw(), path=Path('目录') / ('long' * 256 + '.blf'), raw_time=raw_time)
                row = DecodedCANRecord('bus', 0, 0, raw, pairs, 'decoded',
                    (('mux', 2**80), ('missing', None)), (('mux', 7),))
                original = _metadata_bytes((row.values, row.frame_values, row.frame_layout,
                                             str(row.raw.path), row.raw.raw_time))
                self.assertEqual(_record_metadata_bytes(row), original)

    def test_internal_constructor_preserves_position_and_rebuild_boundaries(self):
        """复用绑定时非法位置、未知原帧或重建字段仍失败。

        参数: 无。返回: None。异常: 合同没有拒绝非法值时断言失败。
        """
        valid = ['bus', 0, 0, self.raw(), (), 'unknown', (), ()]
        for index, value in ((0, 'bad name'), (1, -1), (2, True), (3, object()),
                             (6, (('x', 1.),)), (7, (('x', 1),))):
            args = valid.copy()
            args[index] = value
            with self.subTest(index=index):
                with self.assertRaises((TypeError, ValueError)):
                    DecodedCANRecord._from_bound_values(*args, frozenset())

    def test_delivery_reuses_bound_key_and_keeps_budget_and_missing_updates(self):
        """交付已绑定值时不再编码键；缺值仍更新None且临时费用全退。

        参数: 无。返回: None。异常: 断言失败。
        """
        field = LegacyCANField(0, 'Power', 256)
        key = field.key
        projection = CANUpdateProjection('bus', 'session', (field,))
        owner = SimpleNamespace(_budget=ResourceBudget(), _held_cost=0, _update_cost=0)
        received = []
        # 初始化后任何再生成field.key的行为均立即失败，覆盖计费和投影两个消费者。
        def forbidden_key(item):
            """拒绝逐报文重新编码。参数: item字段。返回: 无。异常: AssertionError。"""
            raise AssertionError('field key must be reused')
        with patch.object(LegacyCANField, 'key', property(forbidden_key)):
            for sequence, value in enumerate((2., None)):
                deliver_message(owner, projection, received.append, self.raw().frame,
                    sequence, {key: value}, sequence, canonical_keys=True)
        self.assertEqual([dict(update.values) for update in received],
                         [{'Power': 2.}, {'Power': None}])
        self.assertEqual((owner._budget.ram_bytes, owner._update_cost, owner._held_cost), (0, 0, 0))
