"""验证ASC快速解析的精确边界与原错误顺序，不依赖某个私有解析函数。

只生成数行合成ASC，预算在完成和异常后必须归零。Decimal上下文由with恢复，
不影响其他测试；负载不用于性能计时。
"""
from decimal import Decimal, Overflow, Subnormal, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.asc import ASCRead, ASCSpec
from chronaxis.sources.raw_can import CANTextError


class ASCFastContextTests(unittest.TestCase):
    """覆盖低精度、精确时间物化、跨行比较及异常格式回退。"""

    def setUp(self):
        """建立独立临时输入目录。参数: 无。返回: None。异常: 临时目录创建失败。"""
        self.temporary = TemporaryDirectory(prefix='asc-fast-context-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.number = 0
        self.budget = ResourceBudget()

    def reader(self, body, **options):
        """创建同次只读解析器。参数: 数据正文及读取选项。返回: ASCRead。异常: 写入或构造失败。"""
        self.number += 1
        path = self.root / f'input-{self.number}.asc'
        path.write_text('base hex timestamps absolute\n' + body, encoding='utf8')
        result = ASCRead(ASCSpec(path), self.budget, **options)
        self.addCleanup(result.close)
        return result

    def assert_released(self, reader):
        """检查关闭事实和共享预算。参数: 读取器。返回: None。异常: 资源未释放则断言失败。"""
        self.assertTrue(reader.closed)
        self.assertEqual(self.budget.ram_bytes, 0)

    def test_low_precision_preserves_first_last_and_record_metadata(self):
        """参数: 无。返回: None。异常: 首末时刻或记录元数据被上下文舍入则失败。"""
        for precision in (2, 5):
            with self.subTest(precision=precision), localcontext() as context:
                context.prec = precision
                with self.reader('0.123456789 1 100 Rx d 0\n0.223456789 1 101 Tx d 0\n',
                                 retain_original=False, retain_source_time=False) as reader:
                    rows = list(reader)
                self.assertEqual(reader.first_exact_time, Decimal('0.123456789'))
                self.assertEqual(reader.last_exact_time, Decimal('0.223456789'))
                self.assertEqual([(r.time_ns, r.line_number, r.sequence) for r in rows],
                                 [(123456789, 2, 0), (223456789, 3, 1)])
                self.assertTrue(all(r.raw_time is None and r.source_time_ns is None for r in rows))
                self.assertFalse(any(r.time_quantized for r in rows))
                self.assert_released(reader)

    def test_previous_exact_time_rejects_backward_and_accepts_forward(self):
        """参数: 无。返回: None。异常: 跨文件前序比较漏报回退或误拒前进则失败。"""
        with localcontext() as context:
            context.prec = 5
            previous = Decimal('0.123456789')
            with self.assertRaises(CANTextError) as caught:
                with self.reader('0.123456788 1 100 Rx d 0\n', previous_exact_time=previous) as reader:
                    list(reader)
            self.assertEqual(caught.exception.reason, 'ASC来源时间回退')
            self.assertEqual(caught.exception.line_number, 2)
            self.assertEqual(reader.count, 0)
            self.assertEqual(reader.last_exact_time, previous)
            self.assert_released(reader)
            context.prec = 2
            with self.reader('0.125 1 100 Rx d 0\n', previous_exact_time=Decimal('0.124')) as reader:
                row, = reader
            self.assertEqual(row.time_ns, 125000000)
            self.assert_released(reader)

    def test_subnanosecond_fallback_keeps_previous_fast_boundary(self):
        """参数: 无。返回: None。异常: 回退解析将已保留时刻截短而放过亚纳秒回退则失败。"""
        with localcontext() as context:
            context.prec = 2
            with self.assertRaises(CANTextError) as caught:
                with self.reader('0.123456789 1 100 Rx d 0\n0.1234567889 1 100 Rx d 0\n') as reader:
                    first = next(reader)
                    next(reader)
            self.assertEqual(first.time_ns, 123456789)
            self.assertEqual(caught.exception.line_number, 3)
            self.assertEqual(caught.exception.reason, 'ASC来源时间回退')
            self.assertEqual(reader.count, 1)
            self.assertEqual(reader.last_exact_time, Decimal('0.123456789'))
            self.assert_released(reader)

    def test_reading_last_exact_time_does_not_weaken_next_order_check(self):
        """参数: 无。返回: None。异常: 查询元数据使后续时间检查失效则失败。"""
        with localcontext() as context:
            context.prec = 5
            with self.assertRaises(CANTextError):
                with self.reader('0.123456789 1 100 Rx d 0\n0.123456788 1 100 Rx d 0\n') as reader:
                    next(reader)
                    self.assertEqual(reader.last_exact_time, Decimal('0.123456789'))
                    next(reader)
            self.assertEqual(reader.count, 1)
            self.assert_released(reader)

    def test_exponent_clamp_and_subnormal_context_keep_original_errors(self):
        """参数: 无。返回: None。异常: 快速解析绕过原指数边界或钳位错误则失败。"""
        cases = [('overflow', '12345', Overflow), ('clamp', '0.123456789', CANTextError),
                 ('subnormal', '0.123456789', Subnormal)]
        for name, stamp, error in cases:
            with self.subTest(case=name), localcontext() as context:
                context.prec = 2
                if name == 'overflow':
                    context.Emax = 3
                elif name == 'clamp':
                    context.Emax, context.clamp = 9, 1
                else:
                    context.Emin = 0
                    context.traps[Subnormal] = True
                with self.assertRaises(error):
                    with self.reader(stamp + ' 1 100 Rx d 0\n') as reader:
                        list(reader)
                self.assertEqual(reader.count, 0)
                self.assert_released(reader)

    def test_invalid_payload_keeps_time_check_order_and_error_metadata(self):
        """参数: 无。返回: None。异常: 先后校验顺序或失败时的精确边界改变则失败。"""
        for stamp, reason, expected_last in [('0.9', 'ASC来源时间回退', '1'),
                                              ('1.1', 'ASC载荷字节字符或进制错误', '1.1')]:
            with self.subTest(time=stamp):
                with self.assertRaises(CANTextError) as caught:
                    with self.reader('1 1 100 Rx d 0\n' + stamp + ' 1 100 Rx d 1 GG\n') as reader:
                        next(reader)
                        next(reader)
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(caught.exception.line_number, 3)
                self.assertEqual(reader.last_exact_time, Decimal(expected_last))
                self.assertEqual(reader.count, 1)
                self.assert_released(reader)


if __name__ == '__main__':
    unittest.main()
