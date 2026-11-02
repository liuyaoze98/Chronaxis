"""检查时间文本与日期转换为纳秒后，精度和时间范围是否正确。

输入为合成数值、ISO日期和一维INT64数组，输出为unittest断言。先用手算
核对T01和T33端点，再用高精度Decimal及固定种子交叉检查；参考路径
不调用数组实现。大坐标下1纳秒差、同刻0差、跨度溢出和固定偏移分别验证，
不排序、不修改输入或丢弃同刻记录。无时区日期需要明确来源时区，
不使用机器默认值。需NumPy，不加载旧代码、不写夹具；禁用site的导入检查
属于另一个断言，本轮文字修改未重新运行，也不作真实日志或性能结论。
"""

# 标准库提供独立十进制真值、确定性样本、可控时区与隔离导入检查。
import random
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from datetime import timedelta, timezone, tzinfo
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path

# 明确导入数组后端；标准库核心的依赖隔离在独立进程检查。
import numpy as np
from chronaxis import (
    TimeOverflowError, checked_add_ns, convert_time, parse_datetime_ns,
    parse_duration, shift_times_reference, time_deltas_reference,
)
from chronaxis.timebase.numpy_ops import shift_times_numpy, time_deltas_numpy

# 手算边界在测试中独立声明，不从被测常量取得预期范围。
MIN_NS, MAX_NS = -(2 ** 63), 2 ** 63 - 1


class _FoldTimezone(tzinfo):
    """构造fold0/1偏移不同的测试时区，只验证歧义拒绝分支。

    无可变状态、文件或IANA数据库依赖；该合成映射不冒充实际地区规则。
    """

    def utcoffset(self, dt):
        """返回与fold相关的合成偏移。

        参数:
            dt (datetime|None): 测试墙钟时刻；None采用0小时。
        返回:
            timedelta: fold0为0、fold1为1小时。
        异常:
            无主动异常；调用者须传入datetime或None。
        """
        # 偏移差异专用于证明入口没有静默挑选重复时刻。
        return timedelta(hours=0 if dt is None else dt.fold)

    def dst(self, dt):
        """为合成时区提供固定零DST。

        参数:
            dt (datetime|None): 不影响测试结果。
        返回:
            timedelta: 固定0，不推断真实夏令时。
        异常:
            无。
        """
        # 固定零值使测试只覆盖fold偏移校验。
        return timedelta(0)

    def tzname(self, dt):
        """给测试诊断提供名称。

        参数:
            dt (datetime|None): 不影响名称。
        返回:
            str: 合成时区标识。
        异常:
            无。
        """
        # 名称明确标识合成规则，没有真实地区含义。
        return "synthetic-fold"


class _GapTimezone(_FoldTimezone):
    """构造UTC往返不保持墙钟值的映射，验证跳空保护。

    偏移固定0以避开fold分支；fromutc故意平移，不能作为生产时区使用。
    """

    def utcoffset(self, dt):
        """提供相同fold偏移，让往返保护独立接受检验。

        参数:
            dt (datetime|None): 不影响合成偏移。
        返回:
            timedelta: 固定0。
        异常:
            无。
        """
        # 同偏移使测试不能仅靠fold检测而通过。
        return timedelta(0)

    def fromutc(self, dt):
        """制造与原墙钟不一致的往返值。

        参数:
            dt (datetime): 由astimezone传入、带本合成tzinfo的时刻。
        返回:
            datetime: 加1小时，保留tzinfo供入口检查。
        异常:
            OverflowError: 超datetime历法范围时传播，测试采用epoch附近。
        """
        # 故意不保持墙钟值，只用于负例验证，不进行真实时区规范化。
        return dt + timedelta(hours=1)


class TimeConversionTests(unittest.TestCase):
    """验证标量精度、诊断、日期和非法输入，不保留跨用例状态。

    固定输入均有独立手算或Decimal真值；不读真实数据或改变机器时区。
    """

    def test_declared_units_and_t01(self):
        """检查T01及显式单位等价，不经浮点中间值。

        参数: 无；unittest实例。
        返回: None；精确结果和表示元数据须符合断言。
        异常: AssertionError或未预期的被测异常表示失败。
        """
        # 各文本独立对应123456789ns，整数大坐标额外覆盖T33精度。
        cases = [("0.123456789", "s", 123456789), ("123.456789", "ms", 123456789),
                 ("123456.789", "us", 123456789), (123456789, "ns", 123456789),
                 (np.int64(2 ** 53 + 1), "ns", 2 ** 53 + 1)]
        # 同一意义不同输入类型不应改变整数时间坐标。
        for value, unit, expected in cases:
            # 子样例用于定位单位/输入，不重复计算测试数量。
            with self.subTest(value=value, unit=unit):
                # 实际入口须给出新冻结诊断对象。
                result = convert_time(value, unit)
                # 手算纳秒必须精确，不能使用近似容差。
                self.assertEqual(result.time_ns, expected)
                # 整纳秒输入没有实际量化。
                self.assertFalse(result.quantized)
                # 声明单位不可由入口猜测或覆盖。
                self.assertEqual(result.input_unit, unit)

    def test_symmetric_half_even_and_context(self):
        """覆盖正负半值、实际量化和调用者Decimal上下文隔离。

        参数: 无。
        返回: None；最近偶数舍入只发生在最终纳秒边界。
        异常: AssertionError或未预期异常表示失败。
        """
        # 手算正负半值对称；1.000ns虽然有小数文字但没有量化。
        cases = [("0.5", 0), ("1.5", 2), ("2.5", 2), ("3.5", 4),
                 ("-0.5", 0), ("-1.5", -2), ("-2.5", -2), ("-3.5", -4)]
        # 遍历半值证明没有向零截断或负值独立舍入偏差。
        for text, expected in cases:
            # 定位每个手算半值的断言。
            with self.subTest(text=text):
                # 实际舍入必须是最近偶数且报告量化。
                result = convert_time(text, "ns")
                # 纳秒真值精确检查。
                self.assertEqual(result.time_ns, expected)
                # 非整数半值均确实量化。
                self.assertTrue(result.quantized)
        # 整纳秒文本不因保留无效小数位而误报量化。
        self.assertFalse(convert_time("1.000", "ns").quantized)
        # 局部上下文结束后恢复，不改调用者全局设置。
        with localcontext() as context:
            # 极低精度能暴露在Decimal乘法中提前舍入的错误。
            context.prec = 2
            # T01必须在该环境保持全部9位分数。
            self.assertEqual(convert_time("0.123456789", "s").time_ns, 123456789)
            # 输入Decimal对象同样不应受运算上下文影响。
            self.assertEqual(convert_time(Decimal("0.123456789"), "s").time_ns, 123456789)

    def test_int64_rounding_boundaries_and_exponents(self):
        """检查定宽端点、舍入进位溢出与极大指数资源界限。

        参数: 无。
        返回: None；合法端点保留、超界拒绝。
        异常: AssertionError或未预期异常表示失败。
        """
        # 两端整数合法，MIN绝对值比MAX大1不能造成中间溢出。
        for value in (MIN_NS, MAX_NS):
            # 直接端点与0偏移都不得拒绝。
            self.assertEqual(convert_time(value, "ns").time_ns, value)
        # MIN是偶数，外侧半值仍按最近偶数返回MIN。
        self.assertEqual(convert_time("-9223372036854775808.5", "ns").time_ns, MIN_NS)
        # MAX内侧小余数不进位，仍为合法MAX。
        self.assertEqual(convert_time("9223372036854775807.4", "ns").time_ns, MAX_NS)
        # 外侧整数/进位及巨大正指数必须在分配巨大幂之前拒绝。
        for value in (MIN_NS - 1, MAX_NS + 1, "9223372036854775807.5",
                      "-9223372036854775808.6", "1e1000000000"):
            # 每项都是具体定宽溢出，不接受任何wrap结果。
            with self.subTest(value=value), self.assertRaises(TimeOverflowError):
                # 入口应显式失败，没有饱和值回退。
                convert_time(value, "ns")
        # 巨大负指数量化为0；真正零不报告实际量化。
        self.assertTrue(convert_time("1e-1000000000", "s").quantized)
        # 不应为极小值构造巨大分母。
        self.assertEqual(convert_time("1e-1000000000", "s").time_ns, 0)
        # 带巨大指数的零不需要幂运算。
        self.assertFalse(convert_time("0e1000000000", "s").quantized)
        # 已声明4096位有效数字界限须明确拒绝更大系数。
        with self.assertRaises(ValueError):
            # 指数抵消不能绕过输入系数资源界限。
            convert_time("1" * 4097 + "e-4097", "ns")

    def test_decimal_oracle(self):
        """用独立高精度Decimal算术校核整数系数算法。

        参数: 无；固定种子20261008和200组声明输入。
        返回: None；合法值精确相等，超界异常一致。
        异常: AssertionError或未预期异常表示失败。
        """
        # 固定种子使样本身份可复现，不使用被测代码生成预期。
        generator = random.Random(20261008)
        # 独立声明单位倍率；oracle使用Decimal乘法而非系数/除余实现。
        scales = {"s": 1000000000, "ms": 1000000, "us": 1000, "ns": 1}
        # 100位足够这些有限样本，避免oracle自身舍入提前丢精度。
        with localcontext() as context:
            # 指定oracle工作精度，退出后恢复上下文。
            context.prec = 100
            # 同时覆盖符号、单位与小数位置，逐次输入可独立定位。
            for index in range(200):
                # 原始文本包含科学计数法，大小不依赖被测实现。
                text = f"{generator.randint(-10 ** 12, 10 ** 12)}e-{generator.randrange(13)}"
                # 四种显式单位均匀选择，不假定默认秒。
                unit = generator.choice(tuple(scales))
                # 独立Decimal oracle显式执行最终最近偶数舍入。
                expected = int((Decimal(text) * scales[unit]).to_integral_value(rounding=ROUND_HALF_EVEN))
                # 标记样本输入以便失败时准确复现。
                with self.subTest(index=index, text=text, unit=unit):
                    # 独立判断最终值而非共享被测范围校验。
                    if MIN_NS <= expected <= MAX_NS:
                        # 合法范围必须精确相等，无相对容差。
                        self.assertEqual(convert_time(text, unit).time_ns, expected)
                    else:
                        # 超界不得因采用其他单位而逃过检查。
                        with self.assertRaises(TimeOverflowError):
                            # 执行实际入口的拒绝分支。
                            convert_time(text, unit)

    def test_float_diagnostics_and_frozen_record(self):
        """区分浮点已有精度限制与实际纳秒量化，冻结返回记录。

        参数: 无。
        返回: None；诊断和数值同时检查。
        异常: AssertionError或未预期异常表示失败。
        """
        # 0.125是精确二进制分数，但不能证明上游源精度。
        exact = convert_time(0.125, "s")
        # 二进制精确分数转换正确。
        self.assertEqual(exact.time_ns, 125000000)
        # 每个float都记录已有精度限制。
        self.assertTrue(exact.precision_limited)
        # 该二进制值正好整纳秒，不应误报实际量化。
        self.assertFalse(exact.quantized)
        # 0.1二进制展开非整纳秒，最终仍舍入至手算100000000ns。
        rounded = convert_time(0.1, "s")
        # 明确两个诊断可以同时为True。
        self.assertEqual((rounded.time_ns, rounded.quantized, rounded.precision_limited),
                         (100000000, True, True))
        # 十进制文本相同数值没有float输入限制。
        self.assertFalse(convert_time("0.1", "s").precision_limited)
        # 调用者不能把结果原地变成不同坐标。
        with self.assertRaises(FrozenInstanceError):
            # 修改冻结字段须显式失败。
            exact.time_ns = 0

    def test_invalid_numbers_and_units(self):
        """拒绝非有限数值、布尔、任意对象和不明单位。

        参数: 无。
        返回: None；错误不能变成正常0或猜测单位。
        异常: AssertionError或未预期异常表示失败。
        """
        # 类型拒绝与数值语法拒绝分开，避免吞异常误称通过。
        for value, error in [(True, TypeError), (np.bool_(False), TypeError), ([], TypeError),
                             (float("nan"), ValueError), (float("inf"), ValueError),
                             (Decimal("-Infinity"), ValueError), ("NaN", ValueError),
                             ("", ValueError), ("12oops", ValueError)]:
            # 每种错误需要约定异常类别。
            with self.subTest(value=value), self.assertRaises(error):
                # 只调用被测入口，禁止测试中预先替换坏值。
                convert_time(value, "ns")
        # 单位缺失、大写、未知或非文本均不猜测秒。
        for unit in (None, "", "S", "minutes", []):
            # 单位协议错误必须在数值换算前拒绝。
            with self.subTest(unit=unit), self.assertRaises(ValueError):
                # 保留合法数值，使失败原因仅为单位。
                convert_time(1, unit)

    def test_duration_contract(self):
        """带单位持续参数允许零，负值在量化前拒绝。

        参数: 无。
        返回: None；时间坐标和持续配置的负值政策明确区分。
        异常: AssertionError或未预期异常表示失败。
        """
        # 合法持续包括毫秒、科学计数法、零和会量化的半纳秒。
        for text, expected in [("500ms", 500000000), ("1e-3s", 1000000),
                               ("0ns", 0), (".5ns", 0)]:
            # 输入原文与规范持续值同时核对。
            result = parse_duration(text)
            # 手算纳秒不能依赖另一被测入口提供预期。
            self.assertEqual((result.time_ns, result.input_text), (expected, text))
        # 负小值即使会舍为0，也不满足非负持续契约。
        for text in ("-0.1ns", "-1s", "3", "1seconds", "1 s", "NaNs", "1MS"):
            # 配置语法/值失败不是正常空持续。
            with self.subTest(text=text), self.assertRaises(ValueError):
                # 不先量化负值来规避检查。
                parse_duration(text)
        # 数字没有声明单位文本，必须拒绝。
        with self.assertRaises(TypeError):
            # 入口不得默认将1解释为秒。
            parse_duration(1)

    def test_datetime_offsets_and_fraction(self):
        """日期归一化到UTC，保留亚微秒和最终分数进位。

        参数: 无。
        返回: None；手算epoch前后和±23:59均精确。
        异常: AssertionError或未预期异常表示失败。
        """
        # 不调用timestamp或另一日期库来构造预期。
        cases = [("1970-01-01T00:00:00.123456789Z", 123456789),
                 ("1970-01-01T08:00:00+08:00", 0),
                 ("1969-12-31T23:59:59.9999999995Z", 0),
                 ("1970-01-01T00:00:00.0000000015Z", 2),
                 ("1970-01-01T00:00:00+23:59", -86340000000000),
                 ("1970-01-01T00:00:00-23:59", 86340000000000)]
        # 显式offset在任何来源时区参数下都优先。
        for text, expected in cases:
            # 子样例定位日期、分数和offset边界。
            with self.subTest(text=text):
                # 传入+8时区证明显式offset没有被覆盖。
                result = parse_datetime_ns(text, timezone(timedelta(hours=8)))
                # 所有结果以UTC epoch整数纳秒比较。
                self.assertEqual(result.time_ns, expected)
                # 日期精度不通过浮点epoch获得。
                self.assertFalse(result.precision_limited)
        # 高于纳秒的实际小数舍入须记录。
        self.assertTrue(parse_datetime_ns(cases[2][0]).quantized)

    def test_naive_timezone_and_ambiguous_mapping(self):
        """无offset须有来源时区，模糊和无法往返的时刻拒绝。

        参数: 无；合成tzinfo不依赖系统IANA数据库。
        返回: None；明确时区可用，缺项/歧义失败。
        异常: AssertionError或未预期异常表示失败。
        """
        # 明确UTC+8将墙钟08:00唯一映射至epoch。
        result = parse_datetime_ns("1970-01-01 08:00:00", timezone(timedelta(hours=8)))
        # 同时检查坐标与采用的时区诊断。
        self.assertEqual((result.time_ns, result.source_timezone), (0, "UTC+08:00"))
        # 缺少来源事实、错误类型、模糊或跳空都必须拒绝。
        for zone in (None, "UTC", _FoldTimezone(), _GapTimezone()):
            # 不退回机器时区或选择某一fold。
            with self.subTest(zone=zone), self.assertRaises(ValueError):
                # epoch附近没有datetime边界异常，专测来源校验。
                parse_datetime_ns("1970-01-01T00:00:00", zone)

    def test_datetime_range_and_invalid_offset(self):
        """覆盖int64日期端点、非法历法和BUG-M1-001 offset回归。

        参数: 无。
        返回: None；非法offset不能被datetime自动归一化。
        异常: AssertionError或未预期异常表示失败。
        """
        # 纳秒端点的ISO值为已知UTC坐标，MIN的整秒基准可暂超int64。
        self.assertEqual(parse_datetime_ns("1677-09-21T00:12:43.145224192Z").time_ns, MIN_NS)
        # 上界保留全部9位分数，没有微秒截断。
        self.assertEqual(parse_datetime_ns("2262-04-11T23:47:16.854775807Z").time_ns, MAX_NS)
        # 外侧1ns和分数进位超过上界都拒绝。
        for text in ("1677-09-21T00:12:43.145224191Z", "2262-04-11T23:47:16.8547758075Z"):
            # 异常必须是时间范围失败。
            with self.subTest(text=text), self.assertRaises(TimeOverflowError):
                # 合法历法不等于合法纳秒范围。
                parse_datetime_ns(text)
        # 分钟60/99和小时24不属于有效±HH:MM，不能进位规范化。
        for text in ("1970-01-01T00:00:00+00:60", "1970-01-01T00:00:00-01:99",
                     "1970-01-01T00:00:00+24:00", "1970-02-30T00:00:00Z",
                     "1970-01-01", "1970-01-01T00:00:60Z"):
            # 完整格式/历法错误应在执行前定位。
            with self.subTest(text=text), self.assertRaises(ValueError):
                # BUG-M1-001最小输入在此直接调用实际函数。
                parse_datetime_ns(text)
        # 日期入口不接受任意数字对象。
        with self.assertRaises(TypeError):
            # 不从数字猜测epoch秒。
            parse_datetime_ns(0)

    def test_timezone_fractional_offset(self):
        """BUG-M1-003：合法亚秒时区偏移不能在UTC坐标合成时丢失。

        参数: 无；显式固定tzinfo，不依赖机器时区或IANA库。
        返回: None；正负微秒offset和原日期分数量化精确符合手算。
        异常: AssertionError或未预期异常表示失败。
        """
        # epoch墙钟减来源offset得到UTC坐标，预期在整数域手算。
        for offset, expected in [(timedelta(microseconds=1), -1000),
                                  (timedelta(microseconds=-1), 1000),
                                  (timedelta(seconds=30, microseconds=1), -30000001000)]:
            # 每个合法亚秒offset都需保留，没有先取UTC整秒。
            with self.subTest(offset=offset):
                # source_timezone为显式tzinfo，生产入口完整执行。
                result = parse_datetime_ns("1970-01-01T00:00:00", timezone(offset))
                # 手算纳秒精确比较，不能采用秒级或微秒级容差。
                self.assertEqual(result.time_ns, expected)
        # 原输入1.5ns舍为2，加上UTC-1000ns得到-998ns。
        rounded = parse_datetime_ns("1970-01-01T00:00:00.0000000015", timezone(timedelta(microseconds=1)))
        # 时区微秒是精确坐标，只有原日期分数产生实际量化。
        self.assertEqual((rounded.time_ns, rounded.quantized), (-998, True))

    def test_core_import_without_site_packages(self):
        """禁用site加载验证标准库时间入口独立于NumPy/CAN。

        参数: 无；src绝对路径来自本测试所在仓库。
        返回: None；子进程成功并报告未加载三个外部模块。
        异常: AssertionError、子进程错误或超时传播表示失败。
        副作用: 创建有10秒上限的子进程，只读源码，不生成pyc或文件。
        """
        # 定位项目源码，不依赖调用者当前目录或已安装包。
        source = str(Path(__file__).resolve().parents[2] / "src")
        # 小脚本只导入核心并查看模块表，不通过stub模拟依赖缺失。
        command = "import sys; sys.path.insert(0, sys.argv[1]); import chronaxis; print(all(name not in sys.modules for name in ('numpy', 'can', 'cantools')))"
        # -S不加载site-packages，-B禁止源码缓存；超时防止挂起。
        completed = subprocess.run([sys.executable, "-B", "-S", "-c", command, source],
                                   check=True, capture_output=True, text=True, timeout=10)
        # 核心真实导入成功且没有加载任何外部数值或CAN模块。
        self.assertEqual(completed.stdout.strip(), "True")


class TimeArrayTests(unittest.TestCase):
    """用手算边界与同输入对照验证真实数组时间计算。

    每个用例独立构造一维int64列；输入不可修改，输出必须是新存储。
    """

    def test_t33_and_same_time(self):
        """2**53附近的1ns差及同时间0差均精确。

        参数: 无。
        返回: None；两后端独立符合手算tuple。
        异常: AssertionError或未预期异常表示失败。
        """
        # 包含低于、等于和高于浮点整数精确边界的坐标。
        times = np.array([2 ** 53 - 1, 2 ** 53, 2 ** 53, 2 ** 53 + 1], dtype=np.int64)
        # Python整数参考不能调用NumPy内核才获得答案。
        self.assertEqual(time_deltas_reference(times), (1, 0, 1))
        # NumPy相同输入必须保留全部1ns与同时间点。
        np.testing.assert_array_equal(time_deltas_numpy(times), [1, 0, 1])

    def test_signed_delta_boundaries(self):
        """两端合法并不足以保证跨度合法，跨符号差在减法前校验。

        参数: 无。
        返回: None；MAX跨度包含、超界和来源回退拒绝。
        异常: AssertionError或未预期异常表示失败。
        """
        # 这些跨度分别手算为MAX、MAX、0、MAX。
        for values, expected in [([MIN_NS, -1], [MAX_NS]), ([-1, MAX_NS - 1], [MAX_NS]),
                                  ([MIN_NS, MIN_NS], [0]), ([0, MAX_NS], [MAX_NS])]:
            # 只声明dtype，不改变合法原坐标。
            times = np.array(values, dtype=np.int64)
            # 参考结果遵守定宽跨度范围。
            self.assertEqual(time_deltas_reference(times), tuple(expected))
            # 数组减法须在安全范围证明后给出相同精确值。
            np.testing.assert_array_equal(time_deltas_numpy(times), expected)
        # 跨度溢出与来源内回退的失败类别分开。
        for values, error in [([MIN_NS, 0], TimeOverflowError), ([-1, MAX_NS], TimeOverflowError),
                               ([MIN_NS, MAX_NS], TimeOverflowError), ([1, 0], ValueError)]:
            # 原坐标本身均合法，不能先diff后检查wrap结果。
            times = np.array(values, dtype=np.int64)
            # 各后端独立执行并拒绝同一错误。
            for kernel in (time_deltas_reference, time_deltas_numpy):
                # 失败结果不得保留为正常0/负跨度。
                with self.subTest(values=values, kernel=kernel.__name__), self.assertRaises(error):
                    # 回退也不得通过排序或去重修补。
                    kernel(times)

    def test_shift_extremes_and_invalid_scalars(self):
        """固定偏移校验输入和结果，不允许超界互相抵消。

        参数: 无。
        返回: None；两后端精确相等或同类失败。
        异常: AssertionError或未预期异常表示失败。
        """
        # MAX/MIN偏移和合法端点均在Python整数域手算。
        for values, offset, expected in [([MIN_NS, 0], MAX_NS, [-1, MAX_NS]),
                                         ([0, MAX_NS], MIN_NS, [MIN_NS, -1]),
                                         ([MIN_NS, MAX_NS], 0, [MIN_NS, MAX_NS])]:
            # 数组保留原输入顺序，不要求为了固定平移排序。
            times = np.array(values, dtype=np.int64)
            # 独立标量参考符合手算结果。
            self.assertEqual(shift_times_reference(times, offset), tuple(expected))
            # 真实ufunc符合相同精确结果。
            np.testing.assert_array_equal(shift_times_numpy(times, offset), expected)
        # 偏移后超界必须拒绝；参考标量也拒绝输入超界再抵消。
        for value, offset in ((MAX_NS, 1), (MIN_NS, -1), (MAX_NS + 1, -1)):
            # 三种情况都违反输入或结果定宽契约。
            with self.subTest(value=value), self.assertRaises(TimeOverflowError):
                # 不通过Python无界整数悄悄扩大对外范围。
                checked_add_ns(value, offset)
        # 数组两端溢出必须在ufunc前失败。
        for values, offset in (([MAX_NS], 1), ([MIN_NS], -1)):
            # 保留合法输入以单独检查结果溢出。
            times = np.array(values, dtype=np.int64)
            # 验证数组入口真实拒绝而非只是参考拒绝。
            with self.assertRaises(TimeOverflowError):
                # 不允许wrap回到另一端。
                shift_times_numpy(times, offset)
        # 空数组仍校验offset类型/范围，不能掩盖非法配置。
        for offset, error in ((True, TypeError), (1.0, TypeError), (MAX_NS + 1, TimeOverflowError)):
            # 参考和数组同样不能因空输入而跳过参数检查。
            for kernel in (shift_times_reference, shift_times_numpy):
                # 错误类别属于输入协议，正常空输出不可替代。
                with self.subTest(offset=offset, kernel=kernel.__name__), self.assertRaises(error):
                    # 明确声明空列仍是int64。
                    kernel(np.array([], dtype=np.int64), offset)

    def test_array_shape_dtype_empty_and_storage(self):
        """拒绝广播/有损cast，支持空/单点与只读非连续视图。

        参数: 无。
        返回: None；输出存储独立，输入内容/写权限保留。
        异常: AssertionError或未预期异常表示失败。
        """
        # 数组入口拒绝列表、非int64和MaskedArray，不能隐式丢失时间缺失信息。
        for value in ([1, 2], np.array([1.0]), np.array([1], dtype=np.uint64), np.array([1], dtype=object),
                      np.ma.array([1, 2], dtype=np.int64, mask=[False, True]),
                      np.ma.array([1, 2], dtype=np.int64, mask=False)):
            # 两个数组操作采用同一严格dtype协议。
            for kernel, arguments in ((time_deltas_numpy, (value,)), (shift_times_numpy, (value, 0))):
                # 类型拒绝必须发生在任何数值运算之前。
                with self.assertRaises(TypeError):
                    # 不把Python循环包装成隐式数组转换。
                    kernel(*arguments)
        # 标量或二维列都不是(N,)协议，不进行隐式广播。
        for value in (np.array(1, dtype=np.int64), np.array([[1, 2]], dtype=np.int64)):
            # 两个内核的shape错误均需定位。
            for kernel, arguments in ((time_deltas_numpy, (value,)), (shift_times_numpy, (value, 0))):
                # shape拒绝明确区别于数值溢出。
                with self.assertRaises(ValueError):
                    # 不扁平化错误输入来修补契约。
                    kernel(*arguments)
        # 空/单点没有跨度，固定偏移保留原长度。
        for values in ([], [MIN_NS]):
            # 显式空数组dtype使输入协议有效。
            times = np.array(values, dtype=np.int64)
            # 参考返回空tuple。
            self.assertEqual(time_deltas_reference(times), ())
            # 数组返回一维空int64而非None或标量。
            self.assertEqual((time_deltas_numpy(times).shape, time_deltas_numpy(times).dtype), ((0,), np.dtype("int64")))
            # 零偏移输出也不复用输入存储。
            self.assertFalse(np.shares_memory(times, shift_times_numpy(times, 0)))
        # 非连续视图与只读标志不能促使实现原地写入。
        backing = np.array([-3, -2, -1, 0, 1, 2], dtype=np.int64)
        # 取得shape=(3,)、步长非连续视图[-3,-1,1]。
        times = backing[::2]
        # 从调用方禁止写入以检测实现副作用。
        times.flags.writeable = False
        # 跨度手算2ns，输出不能与输入共享存储。
        deltas = time_deltas_numpy(times)
        # 固定偏移2ns的手算值是[-1,1,3]。
        shifted = shift_times_numpy(times, 2)
        # 验证两个输出真实内容。
        np.testing.assert_array_equal(deltas, [2, 2])
        # 不排序或去重固定偏移列。
        np.testing.assert_array_equal(shifted, [-1, 1, 3])
        # 原存储全部位置应未变。
        np.testing.assert_array_equal(backing, [-3, -2, -1, 0, 1, 2])
        # 两输出均为新内存，不能返回输入视图。
        self.assertFalse(np.shares_memory(times, deltas) or np.shares_memory(times, shifted))
        # 输入只读标志仍由调用方控制。
        self.assertFalse(times.flags.writeable)

    def test_independent_integer_differential(self):
        """固定种子检查200组坐标的合法结果及相同拒绝行为。

        参数: 无；种子20261009，输入包含全部int64符号区间。
        返回: None；NumPy与独立Python整数参考一致。
        异常: AssertionError或未预期异常表示失败。
        """
        # 样本可复现，与Decimal测试采用独立种子。
        generator = random.Random(20261009)
        # 每组以明确生成的有序来源列和定宽偏移对照。
        for index in range(200):
            # 测试生成排序仅构造合法来源输入，产品代码本身不得预排序。
            values = sorted(generator.randint(MIN_NS, MAX_NS) for _ in range(generator.randrange(9)))
            # 数组与参考获得同一精确坐标，没有float矩阵转换。
            times = np.array(values, dtype=np.int64)
            # 随机合法offset同时覆盖正负极值附近。
            offset = generator.randint(MIN_NS, MAX_NS)
            # 两套内核分别执行，参考失败不吞掉其他错误类型。
            for reference, kernel, arguments in ((time_deltas_reference, time_deltas_numpy, (times,)),
                                                  (shift_times_reference, shift_times_numpy, (times, offset))):
                # 标记样本与内核帮助准确复现。
                with self.subTest(index=index, kernel=kernel.__name__):
                    # 参考只用Python整数先证明合法性。
                    try:
                        # 取得独立数值结果，不调用NumPy。
                        expected = reference(*arguments)
                    except TimeOverflowError:
                        # 参考的定宽失败必须由数组独立校验同样拒绝。
                        with self.assertRaises(TimeOverflowError):
                            # 不从参考返回wrap或部分结果。
                            kernel(*arguments)
                    else:
                        # 合法结果逐位精确相等，不适用浮点容差。
                        np.testing.assert_array_equal(kernel(*arguments), expected)


# 直接执行与discover采用同一测试集，不写历史目录或缓存。
if __name__ == "__main__":
    # 标准测试入口负责报告真实成功/失败结果。
    unittest.main()
