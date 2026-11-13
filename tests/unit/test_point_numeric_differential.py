"""用固定种子及定宽端点检查生产逐点核和两个独立既有实现。

手算边界位于test_expression_point；本文件补充大量值组合，防止只覆盖少数
例值。只执行计算，不读日志或测量速度；失败给出类型、操作和原始值。
"""

from math import copysign, ldexp
import random
import unittest

from chronaxis.core import expression_numpy, expression_reference
from chronaxis.core.expression_point import PointProgram
from chronaxis.core.numeric import result_dtype
from chronaxis.core.scalar import ScalarValue
from chronaxis.core.types import SignalDType as D
import test_expression_point as facts


class PointNumericDifferentialTests(unittest.TestCase):
    """共享类型与输入模型，三个数值执行核保持独立。"""

    def compare(self, root, left, right):
        """比较值、类型、有效性和依赖质量，额外核对零符号。

        参数: 静态树及两条规范输入。返回: None。异常: 任一结果差异的断言。
        """
        context = {'a': left, 'b': right}
        point = PointProgram(root).evaluate(context, {})
        reference = expression_reference._evaluate(root, context, {})
        array = expression_numpy._evaluate(root, {k: facts.column(v) for k, v in context.items()}, 1, {})
        self.assertEqual(point, reference)
        self.assertEqual((point.value.dtype, point.value.valid, int(point.value.quality),
                          int(point.dependency_quality)),
                         (array.value.dtype, bool(array.value.valid[0]), int(array.value.quality[0]),
                          int(array.dependency_quality[0])))
        if point.value.valid:
            value = array.value.values[0].item()
            self.assertEqual(point.value.value, value)
            if point.value.dtype is D.FLOAT64 and value == 0:
                self.assertEqual(copysign(1., point.value.value), copysign(1., value))

    def test_seeded_arithmetic_and_comparison_values(self):
        """逐类型检查精确端点、零、极小数与固定种子随机组合。

        参数: 无。返回: None。异常: 数值或质量不一致的断言。
        """
        rng = random.Random(20261111)
        sets = {
            D.INT64: [-(1 << 63), -1, 0, 1, (1 << 53) + 1, (1 << 63) - 1]
                     + [rng.randrange(-(1 << 63), 1 << 63) for _ in range(18)],
            D.UINT64: [0, 1, (1 << 53) + 1, 1 << 63, (1 << 64) - 1]
                      + [rng.randrange(1 << 64) for _ in range(19)],
            D.FLOAT64: [-0., 0., 5e-324, -5e-324, 1., -1., 1e308, -1e308]
                       + [ldexp(rng.uniform(-1., 1.), rng.randrange(-1022, 1024)) for _ in range(16)],
        }
        # 每个值分别与自身、零和一个固定选中的同类型值组合；不是只抽取正数正常路径。
        for dtype, values in sets.items():
            for op in ('add', 'sub', 'mul', 'div', 'eq', 'ne', 'lt', 'le', 'gt', 'ge'):
                root = facts.node(op, result_dtype(op, dtype, dtype), facts.name('a', dtype), facts.name('b', dtype))
                for index, a in enumerate(values):
                    for b in (a, values[0], values[(index * 7 + 3) % len(values)]):
                        with self.subTest(dtype=dtype, op=op, a=a, b=b):
                            self.compare(root, ScalarValue(a, dtype), ScalarValue(b, dtype))

    def test_mixed_signed_unsigned_comparisons(self):
        """大整数比较不因生产逐点路径而先舍入到float。

        参数: 无。返回: None。异常: 三核比较或定宽类型差异。
        """
        for left, right in ((D.INT64, D.UINT64), (D.UINT64, D.INT64)):
            inputs = {D.INT64: (-(1 << 63), -1, 0, (1 << 53) + 1, (1 << 63) - 1),
                      D.UINT64: (0, (1 << 53) + 1, 1 << 63, (1 << 64) - 1)}
            for op in ('eq', 'ne', 'lt', 'le', 'gt', 'ge'):
                root = facts.node(op, D.BOOL, facts.name('a', left), facts.name('b', right))
                for a in inputs[left]:
                    for b in inputs[right]:
                        with self.subTest(left=left, op=op, a=a, b=b):
                            self.compare(root, ScalarValue(a, left), ScalarValue(b, right))
