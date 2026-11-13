"""穷举内部质量合并，并保持公开负值和未知位的拒绝行为。"""

import unittest
from chronaxis.core.scalar import ScalarValue
from chronaxis.core.types import QualityFlag as Q, SignalDType as D, _QUALITY_BY_MASK
from chronaxis.core.numeric_point import binary_point


class QualityMaskTests(unittest.TestCase):
    """固定内部表不改公开IntFlag或基础质量策略。"""

    def test_all_pairs_keep_the_union_and_invalid_value(self):
        """所有512×512组合均按位保留原原因，只有双方无原因时才返回数值。"""
        values = [ScalarValue(None, D.INT64, False, Q(mask)) if mask else ScalarValue(3, D.INT64)
                  for mask in range(512)]
        for left in range(512):
            self.assertIs(_QUALITY_BY_MASK[left], Q(left))
            for right in range(512):
                value = binary_point('add', values[left], values[right], D.INT64)
                expected = left | right
                self.assertIs(value.quality, Q(expected))
                self.assertEqual(value.valid, expected == 0)
                self.assertEqual(value.value, 6 if expected == 0 else None)

    def test_public_masks_still_reject_negative_and_unknown_bits(self):
        """查表不改变外部QualityFlag构造、组合和反序列化所依赖的严格边界。"""
        self.assertIsInstance(_QUALITY_BY_MASK, tuple)
        self.assertEqual(len(_QUALITY_BY_MASK), 512)
        for mask in (-1, -512, -513, 512, 1023, 2**32):
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                Q(mask)
        self.assertIs(Q.MISSING | Q.STALE, Q(3))
