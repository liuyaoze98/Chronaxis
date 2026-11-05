"""用明确工程结果和定宽边界核对两个独立的单位仿射数值后端。

输入为有限合成数值、倍率/偏移及上游质量；断言数值、类型、有效性和原因。
毫秒换秒与摄氏换开尔文采用手算真值；整数包含中间越界但最终合法、跨
signed/unsigned范围等情况。数组实现必须与独立标量参考及手算同时一致。
不读取真实日志、不写文件、不建立来源或运行计划，也不改共享状态。
"""

# unittest与NumPy仅用于构造两种输入、逐项检查已有手算期望。
import unittest

import numpy as np

from chronaxis.core.affine import affine_reference
from chronaxis.core.affine_numpy import affine_numpy
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.numeric_numpy import DTYPES, NumericArray
from chronaxis.core.types import QualityFlag as Q, SignalDType as D


class AffineConversionTests(unittest.TestCase):
    """每例单独创建数值与质量列，验证转换不污染输入或保留跨调用状态。

    测试辅助方法仅用于断言，不作为产品数值实现或参考真值来源。
    """

    def check(self, raw, source_dtype, scale, offset, dtype, expected, quality=None):
        """将两个后端与显式给出的值/质量期望核对。

        参数: raw为原生数值列表，source_dtype/dtype为源/目标类型；scale和
            offset为转换系数；expected每项为(值,质量)；quality为可选上游原因。
        返回: 数组结果，供检查只读布局等额外要求。
        异常: 后端异常传播；值、类型或质量不一致时unittest断言失败。
        """
        # 保留输入列副本，证明函数没有在原缓冲上修改数值或掩码。
        reasons = [Q.NONE] * len(raw) if quality is None else quality
        original = NumericArray(source_dtype, np.array(raw, dtype=DTYPES[source_dtype]),
                                np.array([item == Q.NONE for item in reasons], dtype=bool),
                                np.array(reasons, dtype=np.uint16))
        before = tuple(array.copy() for array in (original.values, original.valid, original.quality))
        actual = affine_numpy(original, scale, offset, dtype)
        self.assertIs(actual.dtype, dtype)
        self.assertEqual(len(actual.values), len(raw))
        # 断言循环属于测试；产品数组核不能调用这一逐样本参考过程。
        for index, (item, reason, wanted) in enumerate(zip(raw, reasons, expected)):
            reference = affine_reference(ScalarValue(item, source_dtype, reason == Q.NONE, reason),
                                         scale, offset, dtype)
            expected_value, expected_quality = wanted
            self.assertEqual(reference.quality, expected_quality, index)
            self.assertEqual(int(actual.quality[index]), int(expected_quality), index)
            self.assertEqual(reference.valid, expected_quality == Q.NONE, index)
            self.assertEqual(bool(actual.valid[index]), reference.valid, index)
            self.assertIs(reference.dtype, dtype)
            if reference.valid:
                self.assertEqual(reference.value, expected_value, index)
                self.assertEqual(actual.values[index].item(), expected_value, index)
        # 三列独立只读，调用方原列连同无效位置都保持原样。
        for array, copy in zip((original.values, original.valid, original.quality), before):
            np.testing.assert_array_equal(array, copy)
        for array in (actual.values, actual.valid, actual.quality):
            self.assertFalse(array.flags.writeable)
        return actual

    def test_milliseconds_promote_to_fractional_seconds(self):
        """1500毫秒转为1.5秒，不因原值是整数而丢掉小数。

        参数: 无。
        返回: None；两个后端的目标类型和数值一致。
        异常: 值或质量不符时断言失败。
        """
        # 三个值覆盖零、可整除和需要小数的单位转换。
        self.check([0, 1000, 1500], D.INT64, .001, 0, D.FLOAT64,
                   [(0., Q.NONE), (1., Q.NONE), (1.5, Q.NONE)])

    def test_temperature_offset_zero_is_valid(self):
        """绝对零度转换为0K是正常抵消，不是浮点下溢。

        参数: 无。
        返回: None；摄氏到开尔文及逆转换都保留正常零。
        异常: 有效性或数值不符时断言失败。
        """
        # 用温度的明确常数，避免把纯倍率下溢判据套到带偏移结果。
        self.check([-273.15, 0.], D.FLOAT64, 1, 273.15, D.FLOAT64,
                   [(0., Q.NONE), (273.15, Q.NONE)])
        self.check([0., 273.15], D.FLOAT64, 1, -273.15, D.FLOAT64,
                   [(-273.15, Q.NONE), (0., Q.NONE)])

    def test_integer_complete_result_can_rescue_intermediate(self):
        """整数乘积越界但完整仿射结果合法时应保留最终精确结果。

        参数: 无。
        返回: None；signed最小值翻转后再减一得到最大值。
        异常: 按中间结果误报溢出或发生wrap时断言失败。
        """
        # 不能先按64位求负再偏移；完整式的每个手算结果都合法。
        low, high = -(2 ** 63), 2 ** 63 - 1
        self.check([low, 0, high], D.INT64, -1, -1, D.INT64,
                   [(high, Q.NONE), (-1, Q.NONE), (low, Q.NONE)])
        self.check([high], D.INT64, 2, -high, D.INT64, [(high, Q.NONE)])

    def test_integer_cross_signed_unsigned_boundaries(self):
        """整数单位转换跨signed/unsigned目标仍按精确范围检查。

        参数: 无。
        返回: None；两个方向均覆盖端点，不经过浮点中间值。
        异常: 极值舍入、回绕或dtype错误时断言失败。
        """
        # 全输入跨度恰好映射到另一个64位域，结果可以逐项手算。
        self.check([0, 2 ** 63 - 1, 2 ** 63, 2 ** 64 - 1], D.UINT64,
                   1, -(2 ** 63), D.INT64,
                   [(-(2 ** 63), Q.NONE), (-1, Q.NONE), (0, Q.NONE), (2 ** 63 - 1, Q.NONE)])
        self.check([-(2 ** 63), -1, 0, 2 ** 63 - 1], D.INT64,
                   1, 2 ** 63, D.UINT64,
                   [(0, Q.NONE), (2 ** 63 - 1, Q.NONE), (2 ** 63, Q.NONE), (2 ** 64 - 1, Q.NONE)])

    def test_integer_overflow_and_wide_static_coefficient(self):
        """合法输入与溢出输入按位置区分，巨大静态系数不必能装入uint64。

        参数: 无。
        返回: None；唯一可映射的输入得到3，其余输入明确OVERFLOW。
        异常: 溢出位置被wrap或错误拒绝合法静态系数时断言失败。
        """
        # 系数在编译期是Python整数，不能先强制cast为NumPy uint64。
        self.check([0, 1, 2], D.INT64, 2 ** 64, -(2 ** 64) + 3, D.INT64,
                   [(None, Q.OVERFLOW), (3, Q.NONE), (None, Q.OVERFLOW)])
        self.check([0, 1, 2 ** 64 - 1], D.UINT64, 1, -1, D.UINT64,
                   [(None, Q.OVERFLOW), (0, Q.NONE), (2 ** 64 - 2, Q.NONE)])

    def test_float_precision_is_checked_before_multiplication(self):
        """大整数能否转float由原值决定，不先舍入后再检查。

        参数: 无。
        返回: None；2**53+1失效，两侧可精确表示值保持有效。
        异常: 舍入值被输出为正常结果时断言失败。
        """
        # 单位倍率为1仍必须遵守用户要求的无损整数转浮点政策。
        self.check([2 ** 53, 2 ** 53 + 1, 2 ** 53 + 2], D.UINT64, 1, 0, D.FLOAT64,
                   [(float(2 ** 53), Q.NONE), (None, Q.PRECISION_LOSS), (float(2 ** 53 + 2), Q.NONE)])

    def test_float_overflow_and_pure_scale_underflow(self):
        """非有限输出与下溢成零都不能成为正常能量或信号值。

        参数: 无。
        返回: None；真正的输入零仍有效，微小非零下溢则明确标注。
        异常: 溢出/下溢被遗漏或零被误判时断言失败。
        """
        # 不依赖NumPy警告是否打开；质量由明确掩码给出。
        self.check([0., 1e-300, -1e-300], D.FLOAT64, 1e-100, 0, D.FLOAT64,
                   [(0., Q.NONE), (None, Q.PRECISION_LOSS), (None, Q.PRECISION_LOSS)])
        self.check([1e308], D.FLOAT64, 1e308, 0, D.FLOAT64, [(None, Q.NONFINITE)])
        self.check([1], D.INT64, 2 ** 53 + 1, 0, D.FLOAT64, [(None, Q.PRECISION_LOSS)])
        self.check([1], D.INT64, 2 ** 2000, 0, D.FLOAT64, [(None, Q.NONFINITE)])

    def test_invalid_input_is_not_revived_by_zero_or_offset(self):
        """已有缺失或过期值不执行转换，不被乘零或加偏移修复。

        参数: 无。
        返回: None；已有原因保持，正常值仍能使用相同声明。
        异常: 无效值变有效或增加占位计算错误时断言失败。
        """
        # 无效位置保留NaN占位，证明ufunc没有将其参与正常结果。
        self.check([float('nan'), 5., 2.], D.FLOAT64, 0, 273.15, D.FLOAT64,
                   [(None, Q.MISSING), (None, Q.STALE), (273.15, Q.NONE)],
                   [Q.MISSING, Q.STALE, Q.NONE])

    def test_empty_array_and_static_contract(self):
        """空列合法，逻辑类型、坏系数和未提升的小数目标在执行前拒绝。

        参数: 无。
        返回: None；空输出保持类型，结构错误得到明确异常。
        异常: 空列失败或错误声明被接受时断言失败。
        """
        # 空列不生成一条偏移值；声明拒绝在两个公开核保持一致。
        self.check([], D.FLOAT64, 1, 273.15, D.FLOAT64, [])
        for scale, offset, target in ((True, 0, D.FLOAT64), (1, float('inf'), D.FLOAT64),
                                      (.001, 0, D.INT64), (1, 0, D.BOOL)):
            with self.subTest(scale=scale, offset=offset, target=target):
                with self.assertRaises((TypeError, ValueError)):
                    affine_reference(ScalarValue(1, D.INT64), scale, offset, target)
                source = NumericArray(D.INT64, np.array([1], dtype=np.int64),
                                      np.array([True]), np.array([0], dtype=np.uint16))
                with self.assertRaises((TypeError, ValueError)):
                    affine_numpy(source, scale, offset, target)


# 独立专项入口不创建工作目录或读取业务数据。
if __name__ == '__main__':
    unittest.main()
