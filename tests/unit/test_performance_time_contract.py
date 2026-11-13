"""核对整数时间快速入口仍保留公开类型、精确范围及异常定位。

使用手算int64端点、NumPy标量和有自定义转换的整数子类；无文件副作用。
性能另外由公开执行基准衡量，本文件不使用脆弱的耗时断言。
"""

import unittest
from decimal import Decimal

import numpy as np

from chronaxis.timebase.conversion import require_int64_ns, TimeOverflowError


class _ConvertedInt(int):
    """模拟外部整数子类，其显式int转换仍应由公开入口调用。"""

    def __int__(self):
        """返回约定的精确整数。参数: 无。返回: 9。异常: 无。"""
        return 9


class IntegerTimeContractTests(unittest.TestCase):
    """直接覆盖时间入口，防止快速分支改变非原生输入的既定行为。"""

    def test_native_values_and_large_nanosecond_precision(self):
        """参数: 无。返回: None。异常: 断言失败；端点和大数1ns保持精确。"""
        for value in (-(1 << 63), -1, 0, 1, (1 << 53) + 1, (1 << 63) - 1):
            with self.subTest(value=value):
                result = require_int64_ns(value)
                self.assertIs(type(result), int)
                self.assertEqual(result, value)

    def test_numpy_and_subclass_conversion_still_apply(self):
        """参数: 无。返回: None。异常: 断言失败；容器转换不丢位也不跳过子类协议。"""
        for value in (np.int64(-(1 << 63)), np.int64((1 << 53) + 1), np.uint64((1 << 63) - 1)):
            with self.subTest(value=value):
                self.assertIs(type(require_int64_ns(value)), int)
                self.assertEqual(require_int64_ns(value), int(value))
        self.assertEqual(require_int64_ns(_ConvertedInt(7)), 9)

    def test_invalid_types_keep_field_diagnostic(self):
        """参数: 无。返回: None。异常: 断言失败；布尔/小数/文本不能被截断转换。"""
        for value in (True, False, np.bool_(True), 1.0, Decimal(1), '1', None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(TypeError, '^stamp必须为整数纳秒，不能为布尔或浮点$'):
                    require_int64_ns(value, 'stamp')

    def test_native_and_numpy_overflow_keep_same_error(self):
        """参数: 无。返回: None。异常: 断言失败；两侧超界不回绕或饱和。"""
        for value in (-(1 << 63) - 1, 1 << 63, np.uint64(1 << 63), 1 << 300):
            with self.subTest(value=value):
                with self.assertRaisesRegex(TimeOverflowError, '^stamp超出int64纳秒范围$'):
                    require_int64_ns(value, 'stamp')
