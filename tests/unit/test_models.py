"""检查来源、会话和信号样本的结构，拒绝模糊或不合法的输入。

输入为明确类型的合成模型以及非法Python对象，输出为unittest断言。
手算时间范围和整数端点，区分有效0、None、NaN及其质量原因；同名来源
跨会话仍须保持独立身份。冻结字段不能被调用者后续修改，连续范围不含
末点，真实末点另按点查询检查。这里只验收模型，不执行保持或表达式。
导入依赖边界另用禁用site的子进程检查；本次未重新运行该检查，不能凭
说明推断当前包的导入结果。无历史资源读写，也不代替数组内核验收。
"""

# 标准库负责冻结异常、精度端点、导入隔离和实际测试报告。
import math
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

# 只选择模型层，不导入NumPy或CAN。
from chronaxis import TimeOverflowError
from chronaxis.core import (
    DatasetSpec, Interval, MemoryRow, QualityFlag, SessionSpec, SignalDType,
    SignalSample, SourceType, SourceRef, SourceSpec, TimebaseSpec, TimeType, Truth,
)
from chronaxis.core.validation import require_identifier

# 端点在测试中独立声明，不以被测范围常量产生预期。
MIN_NS, MAX_NS = -(2 ** 63), 2 ** 63 - 1


def _sample(**changes) -> SignalSample:
    """每次独立构造合法基线样本，再替换指定合成输入。

    参数: changes为SignalSample字段覆盖，不修补非法类型或质量。
    返回: SignalSample；默认session_a/sensor/raw.value、0ns有效整数0。
    异常: 模型构造异常直接传播，测试负责断言，不吞错误。
    副作用: 只分配局部字典/冻结对象，无全局共享输入状态。
    """
    # 基线全部事实明确声明，来源引用每次独立创建。
    fields = {"name": "reading", "time_ns": 0, "value": 0, "valid": True,
              "quality": QualityFlag.NONE, "source_ref": SourceRef("session_a", "sensor", "raw.value"),
              "sequence": 0}
    # 覆盖用于真实负例，不将坏值强制转换为合法值。
    fields.update(changes)
    # 让实际模型入口决定接受/拒绝。
    return SignalSample(**fields)


def _source(**changes) -> SourceSpec:
    """构造可定位字段的合成memory来源，无读取或自动同步。

    参数: changes为SourceSpec字段覆盖；默认原坐标0/1/2ns、唯一序号0/1/2。
    返回: SourceSpec；字段raw.value、声明观测[0,2]点范围。
    异常: 模型错误直接传播，不排序或丢行来让测试通过。
    """
    # 三条原行是独立明确数据，按声明顺序输入模型。
    rows = tuple(MemoryRow(time, {"raw.value": time}, time) for time in (0, 1, 2))
    # 来源起点是合成事实，不代表真实设备已校准。
    fields = {"name": "sensor", "timebase": TimebaseSpec("clock", TimeType.RELATIVE, "run_001"),
              "rows": rows, "observation_start_ns": 0, "observation_end_ns": 2}
    # 保留负例原始内容给模型验证。
    fields.update(changes)
    # 返回实际构造结果，不使用测试stub代替核心。
    return SourceSpec(**fields)


class ModelTests(unittest.TestCase):
    """检验冻结结构与输入不变量，每用例无跨会话状态。

    构造失败必须具有对应类别；合法0、未知范围和原无效值不可补齐或误拒。
    """

    def test_truth_and_quality_bits(self):
        """三值不能隐式bool，九质量位及组合保留，非法位拒绝。

        参数: 无。
        返回: None；位值和错误均精确断言。
        异常: AssertionError或未预期异常表示失败。
        """
        # 三个值的公开表示与设计一致，UNKNOWN独立存在。
        self.assertEqual([truth.value for truth in Truth], ["true", "false", "unknown"])
        # 默认Enum真值会把FALSE/UNKNOWN当True，入口必须统一拒绝。
        for truth in Truth:
            # 每个结果均须显式处理，而非仅拒绝UNKNOWN。
            with self.subTest(truth=truth), self.assertRaises(TypeError):
                # 实际调用Python bool检验保护入口。
                bool(truth)
        # 九个已知单旗手算为连续2的幂，至少16位才可存储256。
        self.assertEqual([int(flag) for flag in QualityFlag], [1, 2, 4, 8, 16, 32, 64, 128, 256])
        # 全部组合保留511，不截断到uint8。
        self.assertEqual(int(QualityFlag(511)), 511)
        # 组合原因不能压缩成单个布尔值。
        self.assertEqual(int(QualityFlag.STALE | QualityFlag.NONFINITE), 10)
        # BUG-M1-004负mask和未定义正位均必须拒绝。
        for value in (-512, -1, 512, 1024):
            # 负mask不能被标准库归一化成NONE或已知位。
            with self.subTest(value=value), self.assertRaises(ValueError):
                # 直接执行实际枚举构造入口。
                QualityFlag(value)

    def test_identifiers_and_raw_fields(self):
        """ID安全名称与原字段分开，保留原定位文本和大小写。

        参数: 无。
        返回: None；合法名称原样返回，点号别名等明确拒绝。
        异常: AssertionError或未预期异常表示失败。
        """
        # 标识符合ASCII语法且大小写可区分。
        for text in ("reading", "_x", "A1", "a1"):
            # 校验不改名字或自动小写。
            self.assertEqual(require_identifier(text, 'name'), text)
        # 点号、关键字/保留函数名、空白及非ASCII都不是简单ID。
        for text in ("battery.current", "1value", "for", "True", "abs", "isclose", "", " name", "中文"):
            # 每个非法名称应在模型入口拒绝。
            with self.subTest(text=text), self.assertRaises(ValueError):
                # 不进行点号到下划线替换。
                require_identifier(text, 'name')
        # 非文本ID不能靠str推断来源。
        with self.assertRaises(TypeError):
            # 类型拒绝应独立于语法拒绝。
            require_identifier(1, 'name')
        # 原字段不是表达式名，两端原有空格和点号完整保留。
        ref = SourceRef("session_a", "sensor", " raw.value ")
        # 模型不擅自改变实际列定位字符串。
        self.assertEqual(ref.field, " raw.value ")

    def test_interval_half_open_point_and_overflow(self):
        """范围构造检查跨度，连续半开与末点包含显式分开。

        参数: 无。
        返回: None；手算端点/零长度/跨度溢出均检查。
        异常: AssertionError或未预期异常表示失败。
        """
        # 手算合法长度包括最大非负int64跨度。
        for start, end, expected in ((0, 0, 0), (-2, 2, 4), (MIN_NS, -1, MAX_NS), (0, MAX_NS, MAX_NS)):
            # 构造已经证明输入范围，不使用浮点长度。
            interval = Interval(start, end)
            # 精确长度不额外加样本周期。
            self.assertEqual(interval.duration_ns(), expected)
            # 连续末端永远不包含，包括零长度。
            self.assertFalse(interval.contains(end))
            # 真实点上下文包含同一个末点。
            self.assertTrue(interval.contains(end, point=True))
        # 一个普通范围验证包含开始及排除外侧点。
        interval = Interval(0, 2)
        # 开始含、外侧不含，不能只检查end规则。
        self.assertEqual([interval.contains(time) for time in (-1, 0, 1, 2, 3)], [False, True, True, False, False])
        # 不自动将任意整数当作point开关。
        with self.assertRaises(TypeError):
            # 错误开关不能改变半开语义。
            interval.contains(2, point=1)
        # 反向、bool/float、输入/跨度超界分别有明确异常。
        for start, end, error in ((2, 1, ValueError), (True, 2, TypeError), (0, 2.0, TypeError),
                                   (0, MAX_NS + 1, TimeOverflowError), (MIN_NS, 0, TimeOverflowError)):
            # 超界不能通过互相抵消、交换边界或wrap修补。
            with self.subTest(start=start, end=end), self.assertRaises(error):
                # 实际构造入口检查完整跨度。
                Interval(start, end)

    def test_timebase_keeps_origin_without_inference(self):
        """相对起点必填、UTC绝对无相对origin，不自动证明同步。

        参数: 无。
        返回: None；不同origin保留为不同模型事实。
        异常: AssertionError或未预期异常表示失败。
        """
        # 起点文本可以是来源描述，不必改成表达式ID。
        relative = TimebaseSpec("clock", TimeType.RELATIVE, "device/run-001")
        # 原来源事实原样保留。
        self.assertEqual(relative.origin, "device/run-001")
        # UTC绝对时基不靠本机时区确定。
        self.assertIsNone(TimebaseSpec("utc_epoch", TimeType.ABSOLUTE).origin)
        # 相同timebase_id但不同来源起点仍不相等。
        self.assertNotEqual(relative, TimebaseSpec("clock", TimeType.RELATIVE, "device/run-002"))
        # 类型缺项和语义冲突都在构造时定位。
        for kind, origin, error in (("relative", "run", TypeError), (TimeType.RELATIVE, None, TypeError),
                                    (TimeType.RELATIVE, " ", ValueError), (TimeType.ABSOLUTE, "run", ValueError)):
            # 不从机器时区或前一次会话补起点。
            with self.subTest(kind=kind, origin=origin), self.assertRaises(error):
                # 保留非法输入检验真实构造分支。
                TimebaseSpec("clock", kind, origin)

    def test_memory_snapshot_and_invalid_original_values(self):
        """字段映射复制并只读，None/NaN和有效0不被替换。

        参数: 无。
        返回: None；外部修改不污染已构造行，嵌套容器拒绝。
        异常: AssertionError或未预期异常表示失败。
        """
        # 合成原值含正常0、缺失、非有限和布尔等独立逻辑类型。
        original = {"raw.value": 0, "missing": None, "nonfinite": float("nan"), "alarm": False}
        # 构造必须复制原dict，不能只冻结外层对象。
        row = MemoryRow(0, original, 0)
        # 后续调用方修改原输入，模型快照应独立。
        original["raw.value"] = 7
        # 0是实际正常原值，不因truthiness丢失。
        self.assertEqual(row.values["raw.value"], 0)
        # 缺失保持None，不补0。
        self.assertIsNone(row.values["missing"])
        # NaN作为原无效观测保留，不伪装为正常0。
        self.assertTrue(math.isnan(row.values["nonfinite"]))
        # 字典只读保护调用者共享输入。
        with self.assertRaises(TypeError):
            # 原映射不能被规则侧原地改写。
            row.values["raw.value"] = 8
        # dataclass字段也不可修改。
        with self.assertRaises(FrozenInstanceError):
            # 不能修改时间改变其他规则看到的观测。
            row.time_ns = 2
        # 不可变标量域以外的嵌套可变对象必须拒绝。
        with self.assertRaises(TypeError):
            # 冻结映射不能掩盖内部list仍可变。
            MemoryRow(0, {"raw.value": []}, 0)
        # 负序号、非整数时间和非映射值保留错误类别。
        for time, values, sequence, error in ((0, {}, -1, ValueError), (False, {}, 0, TypeError),
                                             (0, [], 0, TypeError), (0, {" ": 1}, 0, ValueError)):
            # 不自动重编号或把错误容器变空行。
            with self.subTest(time=time, values=values), self.assertRaises(error):
                # 真实行构造入口检查模型。
                MemoryRow(time, values, sequence)

    def test_source_order_same_time_and_unknown_bounds(self):
        """来源保留同时间不同身份，未知观测边界不推测完整覆盖。

        参数: 无。
        返回: None；原顺序/序号保持，空/部分未知来源可描述。
        异常: AssertionError或未预期异常表示失败。
        """
        # 原行可有相同时间但不同序号；信号冲突解析留STATE。
        rows = (MemoryRow(1, {"raw.value": 1}, 10), MemoryRow(1, {"raw.value": 2}, 11))
        # 原时间/值未绑定，来源模型不擅自去重。
        source = _source(rows=rows)
        # 两个原观测都保留，不能仅按timestamp删除。
        self.assertEqual([(row.time_ns, row.sequence) for row in source.rows], [(1, 10), (1, 11)])
        # 空来源和unknown双端不制造最后周期或0覆盖。
        empty = _source(rows=(), observation_start_ns=None, observation_end_ns=None)
        # 已知kind是当前实际支持的memory。
        self.assertEqual((empty.rows, empty.observation_start_ns, empty.observation_end_ns, empty.source_type),
                         ((), None, None, SourceType.MEMORY))
        # 一个已知端点不能迫使另一端被推断。
        self.assertIsNone(_source(observation_start_ns=None).observation_start_ns)
        # 源范围字段冻结，不继承另一个会话的结束事实。
        self.assertIsNone(_source(observation_end_ns=None).observation_end_ns)

    def test_source_rejects_bad_identity_order_and_mapping(self):
        """回退、重复原身份和偏移溢出不能在来源描述中隐藏。

        参数: 无。
        返回: None；不通过排序/去重/强制cast修补错误来源。
        异常: AssertionError或未预期异常表示失败。
        """
        # 各负例单独对应来源结构、顺序、身份或坐标契约。
        cases = [({"rows": []}, TypeError), ({"rows": ({"time": 0},)}, TypeError),
                 ({"source_type": "can_blf"}, TypeError), ({"offset_ns": True}, TypeError),
                 ({"rows": (MemoryRow(1, {}, 0), MemoryRow(0, {}, 1))}, ValueError),
                 ({"rows": (MemoryRow(0, {}, 0), MemoryRow(1, {}, 0))}, ValueError),
                 ({"offset_ns": MAX_NS}, TimeOverflowError),
                 ({"observation_start_ns": 2, "observation_end_ns": 1}, ValueError),
                 ({"observation_start_ns": 1}, ValueError)]
        # 输入保持原错误以验证真实拒绝路径。
        for changes, error in cases:
            # 每个错误用对应异常类别定位。
            with self.subTest(changes=changes), self.assertRaises(error):
                # 不在测试中先排序或删除非法行。
                _source(**changes)

    def test_session_dataset_and_unknown_constructor_fields(self):
        """首版单会话/实体及唯一来源，缺项/未知构造字段不放行。

        参数: 无。
        返回: None；合法输入可描述，重复来源或无类型对象拒绝。
        异常: AssertionError或未预期异常表示失败。
        """
        # 合成来源与明确会话时基，不靠全局默认环境。
        source = _source()
        # 一个会话一个数据集，可用于任意试验实体。
        session = SessionSpec("session_a", source.timebase, 0, 2, (source,))
        # 数据集保存真实typed会话引用而非无类型占位。
        dataset = DatasetSpec("dataset_a", "specimen_a", session)
        # 构造不会串接或复制成不同会话状态。
        self.assertIs(dataset.session, session)
        # 同会话来源名必须唯一，不能默认取第一个。
        with self.assertRaises(ValueError):
            # 两个合法来源也不能使用同一会话名称。
            SessionSpec("session_a", source.timebase, 0, 2, (source, _source()))
        # sources必须不可变tuple而非共享可变列表。
        with self.assertRaises(TypeError):
            # 结构错误不会自动修补。
            SessionSpec("session_a", source.timebase, 0, 2, [source])
        # 首版dataset不将多个会话串接为一条时间轴。
        with self.assertRaises(TypeError):
            # M3批量任务不以列表隐式提前实现。
            DatasetSpec("dataset_a", "specimen_a", [session])
        # 未实现的构造字段不能悄悄忽略，T58仅该模型范围。
        with self.assertRaises(TypeError):
            # dataclass实际入口拒绝未知键，不代表完整JSON schema已实现。
            SessionSpec("session_a", source.timebase, 0, 2, (source,), unknown=True)
        # 必需typed字段缺失明确失败。
        with self.assertRaises(TypeError):
            # 不从上一任务补会话。
            DatasetSpec("dataset_a", "specimen_a")

    def test_sample_quality_preserves_zero_and_invalid_reason(self):
        """有效0合法，九种禁止质量均不得与valid=True同时存在。

        参数: 无。
        返回: None；invalid保留原值及组合原因，不自动清质量或补0。
        异常: AssertionError或未预期异常表示失败。
        """
        # 明确0是可用数值，而非默认缺失。
        self.assertEqual((_sample().value, _sample().valid), (0, True))
        # 所有首版质量标志都属于基础禁止策略，ESTIMATED也不默认允许。
        for flag in QualityFlag:
            # 每个单旗不能被有效值覆盖。
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                # 模型拒绝质量/valid矛盾，而非偷偷改valid。
                _sample(quality=flag)
            # 无效值可保留原有限诊断值，原因不丢失。
            invalid = _sample(valid=False, quality=flag, value=7)
            # 同一原值/原因在无效输入中保留。
            self.assertEqual((invalid.value, invalid.valid, invalid.quality), (7, False, flag))
        # 明确缺失与非有限不能冒充正常0。
        missing = _sample(value=None, valid=False, quality=QualityFlag.MISSING)
        # None保留，基础策略不会替换为0。
        self.assertIsNone(missing.value)
        # 非有限原值与多个原因一起保留。
        invalid = _sample(value=float("nan"), valid=False, quality=QualityFlag.NONFINITE | QualityFlag.STALE)
        # NaN仍是诊断原值，不进入正常数值域。
        self.assertTrue(math.isnan(invalid.value))
        # 全部组合原因原样存在。
        self.assertEqual(int(invalid.quality), 10)
        # 无原因的invalid会丢失可追溯性，必须拒绝。
        with self.assertRaises(ValueError):
            # NONE不能替代已知无效原因。
            _sample(valid=False)
        # 缺失/非有限与valid=True矛盾。
        for value in (None, float("nan"), float("inf"), -float("inf")):
            # 每个坏原值都要显式失败。
            with self.subTest(value=value), self.assertRaises(ValueError):
                # 不用isfinite结果补0或清valid。
                _sample(value=value)

    def test_sample_strict_structure_and_frozen_fields(self):
        """样本不接受整数truthiness、裸质量位或非typed来源。

        参数: 无。
        返回: None；非法结构失败，合法对象字段冻结。
        异常: AssertionError或未预期异常表示失败。
        """
        # 每个负例隔离一个具体结构不变量。
        for changes, error in (({"valid": 1}, TypeError), ({"quality": 0}, TypeError),
                               ({"source_ref": "sensor"}, TypeError), ({"value": []}, TypeError),
                               ({"time_ns": True}, TypeError), ({"sequence": False}, TypeError),
                               ({"sequence": -1}, ValueError), ({"time_ns": MAX_NS + 1}, TimeOverflowError)):
            # 模型类型错误不能被当正常缺失。
            with self.subTest(changes=changes), self.assertRaises(error):
                # 未转换非法输入再测试，保持真实入口行为。
                _sample(**changes)
        # 样本冻结避免跨规则污染。
        sample = _sample()
        # 即使改为看似合法数值也不允许原地改共享样本。
        with self.assertRaises(FrozenInstanceError):
            # 新值必须形成新观测，不能改变输入历史。
            sample.value = 8

    def test_dtype_exact_ranges_and_enum_domain(self):
        """有效值类型和定宽范围严格，bool独立、枚举只认声明标签。

        参数: 无。
        返回: None；不将大整数/任意数值隐式转float或bool。
        异常: AssertionError或未预期异常表示失败。
        """
        # 所有合法端点手算，不从NumPy隐式promotion取得预期。
        for value, dtype in ((MIN_NS, SignalDType.INT64), (MAX_NS, SignalDType.INT64),
                              (0, SignalDType.UINT64), (2 ** 64 - 1, SignalDType.UINT64),
                              (1.25, SignalDType.FLOAT64), (False, SignalDType.BOOL)):
            # 真实定义dtype校验不得误拒合法0/False。
            _sample(value=value).validate_dtype(dtype)
        # 枚举原标签可用完整文本，不转换为标识符。
        _sample(value="mode.scope").validate_dtype(SignalDType.ENUM, ("mode.scope", "mode.off"))
        # 超界在有符号/无符号域分别拒绝，Python大整数不能放宽定义。
        for value, dtype in ((MIN_NS - 1, SignalDType.INT64), (MAX_NS + 1, SignalDType.INT64),
                              (-1, SignalDType.UINT64), (2 ** 64, SignalDType.UINT64)):
            # 构造只保留原标量，声明类型后必须检查定宽范围。
            with self.subTest(value=value, dtype=dtype), self.assertRaises(OverflowError):
                # 不把overflow值仍标记为正常有效计算输入。
                _sample(value=value).validate_dtype(dtype)
        # Python bool是int子类也不意味着整数信号；float/int也不隐式互换。
        for value, dtype in ((True, SignalDType.INT64), (1, SignalDType.BOOL),
                              (1, SignalDType.FLOAT64), (1.0, SignalDType.INT64)):
            # 显式归一化层以后承担转换及精度检查。
            with self.subTest(value=value, dtype=dtype), self.assertRaises(TypeError):
                # 当前模型校验不执行cast。
                _sample(value=value).validate_dtype(dtype)
        # 枚举缺项/重复标签/未知值和非enum choices都明确拒绝。
        for value, dtype, choices in (("scope", SignalDType.ENUM, ()), ("scope", SignalDType.ENUM, ("scope", "scope")),
                                      ("other", SignalDType.ENUM, ("scope",)), (1, SignalDType.INT64, ("scope",))):
            # 域错误不能当作正常默认标签。
            with self.subTest(value=value, choices=choices), self.assertRaises(ValueError):
                # 未声明标签不会自动注册。
                _sample(value=value).validate_dtype(dtype, choices)
        # 无效原值不是正常数值，dtype检查不对其计算或替换。
        invalid = _sample(value=None, valid=False, quality=QualityFlag.DECODE_ERROR)
        # 保留缺失诊断，合法dtype声明仍可用于后续掩码路径。
        invalid.validate_dtype(SignalDType.FLOAT64)
        # 原None不被cast成0.0。
        self.assertIsNone(invalid.value)

    def test_session_sample_identity_and_terminal_point(self):
        """样本只归属明确会话/来源/字段，真实终点可用于点事件。

        参数: 无。
        返回: None；身份缺项和范围错误均拒绝。
        异常: AssertionError或未预期异常表示失败。
        """
        # 合成会话纳秒范围[0,2)与实际点终点2。
        source = _source()
        # 来源名称已唯一，不允许跨任务默认来源。
        session = SessionSpec("session_a", source.timebase, 0, 2, (source,))
        # 起点样本归属通过。
        session.validate_sample(_sample())
        # 真实点终点包含，但Interval连续范围仍不含end。
        session.validate_sample(_sample(time_ns=2, sequence=2))
        # 各负例只替换归属或时间，不改变质量预期。
        for changes in ({"source_ref": SourceRef("other_session", "sensor", "raw.value")},
                        {"source_ref": SourceRef("session_a", "other_source", "raw.value")},
                        {"source_ref": SourceRef("session_a", "sensor", "missing.field")},
                        {"time_ns": -1}, {"time_ns": 3}):
            # 来源/字段缺项不能靠别名默认取第一个。
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                # 实际归属检查执行，不用测试替身。
                session.validate_sample(_sample(**changes))

    def test_source_range_offset_and_cross_session_isolation(self):
        """已知来源范围独立限制样本，跨会话同名来源不泄漏身份。

        参数: 无。
        返回: None；显式offset纳秒映射保留，多个会话结构独立。
        异常: AssertionError或未预期异常表示失败。
        """
        # 来源原坐标0/1/2加明确偏移10后点范围为[10,12]。
        shifted = _source(offset_ns=10)
        # 会话范围更长不能扩大来源实际范围。
        session = SessionSpec("session_a", shifted.timebase, 9, 13, (shifted,))
        # 来源结束点12属于点上下文，不能自动视为已同步多源。
        session.validate_sample(_sample(time_ns=12, sequence=2))
        # 会话内但来源外的点应拒绝，来源覆盖不能借其他来源延长。
        for time in (9, 13):
            # 上下界各校验一次，已知源末点严格外侧才拒绝。
            with self.subTest(time=time), self.assertRaises(ValueError):
                # 当前样本仍在会话点域内，失败应来自来源域。
                session.validate_sample(_sample(time_ns=time))
        # 另一个会话可以独立使用同名sensor，不继承旧来源offset。
        other = _source()
        # 明确新的会话身份，与前一个对象同名来源隔离。
        other_session = SessionSpec("session_b", other.timebase, 0, 2, (other,))
        # 该新来源原偏移仍为0，未受前会话影响。
        self.assertEqual(other_session.sources[0].offset_ns, 0)
        # 相同别名和来源名不是相同跨会话引用。
        with self.assertRaises(ValueError):
            # 旧sample ref不能被新会话重新解释。
            other_session.validate_sample(_sample())
        # 新引用明确声明会话才能通过。
        other_session.validate_sample(_sample(source_ref=SourceRef("session_b", "sensor", "raw.value")))

    def test_core_import_without_external_packages(self):
        """真实禁site进程导入core，不需要数组/CAN依赖。

        参数: 无；src绝对路径由测试文件定位。
        返回: None；模块成功加载且外部依赖未加载。
        异常: AssertionError、子进程错误/超时传播表示失败。
        副作用: 只读子进程、10秒超时、禁止pyc，不写临时目录。
        """
        # 不依赖当前目录或已安装分发包。
        source = str(Path(__file__).resolve().parents[2] / "src")
        # 实际禁site导入，不用mock假装依赖可选。
        command = "import sys; sys.path.insert(0, sys.argv[1]); import chronaxis.core; print(all(name not in sys.modules for name in ('numpy', 'can', 'cantools')))"
        # -S禁site-packages，-B禁缓存，子进程执行有界。
        completed = subprocess.run([sys.executable, "-B", "-S", "-c", command, source],
                                   check=True, capture_output=True, text=True, timeout=10)
        # 真正core导入成功且没有意外加载外部依赖。
        self.assertEqual(completed.stdout.strip(), "True")


# 直接运行与discover采用同一组用例，没有文件副作用。
if __name__ == "__main__":
    # 报告真实断言结果，不忽略失败。
    unittest.main()
