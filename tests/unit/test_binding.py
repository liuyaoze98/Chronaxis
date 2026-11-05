"""检查原字段怎样绑定成别名，以及哪些声明应在运行前被拒绝。

输入是合成内存行、明确的信号定义和固定时间偏移依据；输出为unittest断言。
用手算mA到A系数核对单位声明，检查重名、原字段缺项、可选语义名称、有效期
以及输入变化后的绑定身份。不同来源只有实际联合使用时才检查公共起点或
显式同步依据。这里检验配置与定位，不执行有效期保持、表达式或领域预设。
数据在内存，无文件写入或旧DBC加载；声明检查通过不能代替实际计算验收。
"""

# unittest和冻结异常只承担合成契约校验，不使用测试替身替代绑定入口。
import unittest
from dataclasses import FrozenInstanceError, replace

# 导入实际core入口同时覆盖BUG-M1-005的错误导入回归。
from chronaxis.core import (MemoryRow, SessionSpec, SignalBindings, SignalDefinition, SignalDType,
                            SourceSpec, SynchronizationEvidence, TimebaseSpec, TimeType)
from chronaxis.core.unit_registry import ATOMIC_UNITS


def _session(**changes) -> SessionSpec:
    """构造每次独立的两来源公共起点输入。

    参数: changes为SessionSpec字段覆盖；默认0—10ns、run_1公共起点。
    返回: SessionSpec；a字段raw.current/b字段raw.voltage。
    异常: typed模型错误直接传播，不自动校准或修补。
    """
    # 公共起点是合成输入声明，不是实际设备同步证明。
    clock = TimebaseSpec("clock", TimeType.RELATIVE, "synthetic-run-1")
    # 两来源值明确，不隐藏字段映射或重复应用缩放。
    sources = (SourceSpec("a", clock, (MemoryRow(0, {"raw.current": 1000}, 0),)),
               SourceSpec("b", clock, (MemoryRow(0, {"raw.voltage": 5000}, 0),)))
    # 会话域和输入独立局部构造。
    values = {"session_id": "session_a", "timebase": clock, "domain_start_ns": 0,
              "domain_end_ns": 10, "sources": sources}
    # 将负例原样交给真实构造校验。
    values.update(changes)
    # 每次返回新的冻结会话，无全局可变输入。
    return SessionSpec(**values)


def _definition(**changes) -> SignalDefinition:
    """构造明确额外mA到A转换的信号定义。

    参数: changes为定义字段覆盖；默认current/a/raw.current及10ns有效期。
    返回: SignalDefinition；scale=0.001，目标float64。
    异常: 定义构造错误直接传播，测试负例负责断言。
    """
    # 原值1000mA的目标契约是1A，不自行执行数值转换。
    values = {"name": "current", "source": "a", "field": "raw.current",
              "dtype": SignalDType.FLOAT64, "unit": "A", "input_unit": "mA",
              "scale": 0.001, "valid_for_ns": 10}
    # 保留被测输入，不能放宽错误声明。
    values.update(changes)
    # 调用实际typed定义入口。
    return SignalDefinition(**values)


class BindingTests(unittest.TestCase):
    """检查编译前绑定门槛，每项无跨任务注册状态。

    错误声明执行前失败；合法原字段点号保留，optional语义不改变实际定位。
    """

    def test_optional_semantics_and_complete_reference(self):
        """可选语义保留原定位与转换，完整引用包含会话。

        参数: 无；同一定义仅增加大小写敏感semantic字符串。
        返回: None；基本定位相同，元数据完整保存。
        异常: 断言失败由unittest报告。
        """
        # 原字段与别名分开，配置领域语义可选。
        first = SignalBindings(_session(), (_definition(),))
        # 有语义不要求核心加载汽车或电池目录。
        second = SignalBindings(_session(), (_definition(semantic_id="battery.current", semantic_contract_version="1"),))
        # 两个绑定都定位相同原字段与当前会话。
        self.assertEqual(first.source_ref("current"), second.source_ref("current"))
        # optional metadata不改变转换声明。
        self.assertEqual(first.resolve("current").scale, second.resolve("current").scale)
        # metadata身份需要可追溯，不能被缓存键忽略。
        self.assertNotEqual(first.identity, second.identity)
        # 当前会话完整身份在引用中保存。
        self.assertEqual(first.source_ref("current").session_id, "session_a")
        # 元数据点号原样保存。
        self.assertEqual(second.resolve("current").semantic_id, "battery.current")

    def test_namespaces_and_explicit_same_name(self):
        """重复别名、派生重名及保留名称拒绝，原字段可显式同名。

        参数: 无；合成重复signals/derived和简单原列。
        返回: None；名称错误定位，合法同名绑定成功。
        异常: 未按预期拒绝时断言失败。
        """
        # 同一原字段可用于多个不同别名，但不能重复别名。
        for definitions, derived in (((_definition(), _definition()), ()), ((_definition(),), ("current",)),
                                     ((), ("derived", "derived"))):
            # 每种冲突独立检查，不重命名输入。
            with self.subTest(derived=derived, count=len(definitions)):
                # 构造入口必须拒绝歧义。
                with self.assertRaises(ValueError):
                    # 真正绑定构造包含统一名称空间检查。
                    SignalBindings(_session(), definitions, derived)
        # 点号、关键字、函数名不进入表达式变量域。
        for name in ("battery.current", "for", "abs", "isclose"):
            # 每个非法别名不能自动改写。
            with self.assertRaises(ValueError):
                # typed定义先做名称校验。
                _definition(name=name)
        # 简单原字段允许明示同名，没有自动绑定。
        session = _session()
        # 使用独立来源实际列名，不碰历史路径。
        source = replace(session.sources[0], rows=(MemoryRow(0, {"current": 1.0}, 0),))
        # 同名只是显式定位合法，不跳过来源检查。
        binding = SignalBindings(replace(session, sources=(source,)), (_definition(field="current"),))
        # 确认原定位没有被隐藏替换。
        self.assertEqual(binding.source_ref("current").field, "current")

    def test_source_field_and_unknown_alias_fail_before_run(self):
        """来源字段缺项及未知别名在执行前失败。

        参数: 无；不存在来源、原字段或当前别名。
        返回: None；错误包含实际缺项名称。
        异常: 断言失败由unittest报告。
        """
        # 无法定位的声明不能等到求值时猜字段。
        for definition in (_definition(source="missing"), _definition(field="missing")):
            # 验证真绑定入口的诊断。
            with self.assertRaisesRegex(ValueError, "不存在"):
                # 尚未运行任何输入计算。
                SignalBindings(_session(), (definition,))
        # 合法定义独立构造当前绑定。
        bindings = SignalBindings(_session(), (_definition(),))
        # 列出可用别名帮助调用者，不通过semantic推断未知名字。
        with self.assertRaisesRegex(ValueError, "可用：current"):
            # 不继承其他任务里的missing信号。
            bindings.resolve("missing")
        # semantic字符串不能作属性路径引用。
        with self.assertRaises(ValueError):
            # 保留简单别名规则。
            bindings.resolve("battery.current")

    def test_known_units_and_explicit_direction(self):
        """手算首版换算倍率及明示方向，错误系数不自动修正。

        参数: 无；mV/V、mA/A、kW/W、Wh/J、Ah/A·s等转换。
        返回: None；所有显式正确倍率verified。
        异常: 不符手算或错误输入未拒绝则断言失败。
        """
        # 期望倍率来自工程单位定义，不从被测表生成。
        for input_unit, unit, scale in (("mV", "V", .001), ("mA", "A", .001), ("kW", "W", 1000),
                                        ("Wh", "J", 3600), ("kWh", "Wh", 1000), ("ms", "s", .001),
                                        ("Ah", "A·s", 3600), ("J", "Wh", 1 / 3600)):
            # 合法声明不执行样本计算。
            definition = _definition(input_unit=input_unit, unit=unit, scale=scale)
            # 单位校验状态明确保存。
            self.assertEqual(definition.unit_status, "verified")
        # 错倍率、偏移和量纲冲突均是配置错误。
        for changes in ({"scale": 1}, {"offset": 1}, {"unit": "V"}):
            # 不猜或修复用户系数。
            with self.assertRaises(ValueError):
                # 负例通过实际定义入口。
                _definition(**changes)
        # 原方向和目标方向是显式合成元数据，不来自名称。
        reversed_definition = _definition(scale=-.001, direction_factor=-1,
                                          input_sign_convention="positive_is_out", sign_convention="positive_is_in")
        # 已声明方向因子的系数正确。
        self.assertEqual(reversed_definition.unit_status, "verified")
        # 缺证据不能仅靠负scale通过。
        with self.assertRaises(ValueError):
            # 没有转换前/后方向。
            _definition(scale=-.001, direction_factor=-1)
        # 单位表自身不可原地修改。
        with self.assertRaises(TypeError):
            # 防止缓存已验证关系后来发生变化。
            ATOMIC_UNITS["A"] = ("wrong", 1)

    def test_unknown_units_and_metadata_are_unverified(self):
        """未知单位保留显式转换，版本声明不冒充语义契约验证。

        参数: 无；自定义原/目标标签和领域字符串。
        返回: None；unknown标unverified，空元数据拒绝。
        异常: 不符合明示状态时断言失败。
        """
        # 未知单位可用于普通分析，但没有量纲证明。
        definition = _definition(input_unit="raw_count", unit="custom", scale=2, offset=3,
                                 semantic_id="custom.signal", mapping_version="v1")
        # 不以标签声明代替已知单位关系。
        self.assertEqual(definition.unit_status, "unverified")
        # 单位完全同名未知也不能verified。
        self.assertEqual(_definition(input_unit="custom", unit="custom", scale=1).unit_status, "unverified")
        # 空语义/版本和孤立契约版本拒绝。
        for changes in ({"semantic_id": ""}, {"mapping_version": " "}, {"semantic_contract_version": "1"}):
            # 每种缺项单独检查。
            with self.assertRaises(ValueError):
                # 不内置默认领域契约。
                _definition(**changes)

    def test_dtype_choices_and_validity_declarations(self):
        """严格类型/域/有效期声明，逻辑映射不使用truthiness。

        参数: 无；enum/bool编码和不同非法声明。
        返回: None；明确映射保留，输入矛盾拒绝。
        异常: 回归失败由unittest报告。
        """
        # enum多个原编码可表示同一业务标签，目标逻辑标签不自动编号。
        enum = _definition(dtype=SignalDType.ENUM, unit="1", input_unit="1", scale=1,
                           choices=((0, "off"), (1, "scope"), (2, "scope")))
        # 原编码映射完整保留。
        self.assertEqual(enum.choices[-1], (2, "scope"))
        # bool原编码只通过显式映射接受。
        boolean = _definition(dtype=SignalDType.BOOL, unit="1", input_unit="1", scale=1,
                              choices=((0, False), (1, True)))
        # 数值1没有变成目标类型int。
        self.assertIs(boolean.choices[1][1], True)
        # 类型结构和有限期都是运行前硬门槛。
        for changes in ({"valid_for_ns": 0}, {"valid_for_ns": True}, {"dtype": "float64"},
                        {"sample_policy": "linear"}, {"same_time_policy": "first"},
                        {"scale": float("nan")}, {"choices": []}, {"valid_range": (2, 1)},
                        {"invalid_values": []}, {"invalid_values": ([],)}, {"quality_policy": "allow_estimated"}):
            # 对应类型/值错误都不能接受。
            with self.assertRaises((TypeError, ValueError)):
                # 不cast/修补非法声明。
                _definition(**changes)
        # enum重复编码不能隐式覆盖。
        with self.assertRaises(ValueError):
            # 即使标签不同也明确拒绝重复定位。
            replace(enum, choices=((1, "scope"), (1, "off")))
        # bool不能把数值标签当作True。
        with self.assertRaises(TypeError):
            # 原码可以1，目标标签必须实际bool。
            replace(boolean, choices=((1, 1),))

    def test_binding_identity_changes_with_actual_input_and_policy(self):
        """来源内容、字段、版本与有效期变化均改变执行绑定身份。

        参数: 无；同名不同数据及各个策略变更。
        返回: None；独立构造相同输入稳定，所有重要变化不复用旧身份。
        异常: 断言失败由unittest报告。
        """
        # 基线独立构造，只比较真正可执行引用身份。
        session = _session()
        # 生成完整当前绑定。
        base = SignalBindings(session, (_definition(),))
        # 相同输入没有全局随机状态。
        self.assertEqual(base.identity, SignalBindings(_session(), (_definition(),)).identity)
        # 策略和版本改变必须可追溯。
        for changes in ({"valid_for_ns": 11}, {"same_time_policy": "last_by_sequence"},
                        {"mapping_version": "v2"}, {"invalid_values": (-1,)}, {"valid_range": (0, 10)},
                        {"measurement_location": "point_a"}):
            # 新定义独立生成身份。
            modified = SignalBindings(session, (_definition(**changes),))
            # 不只按别名缓存旧契约。
            self.assertNotEqual(base.identity, modified.identity)
        # 同名来源实际内容变化也不能复用旧输入绑定。
        changed_source = replace(session.sources[0], rows=(MemoryRow(0, {"raw.current": 2000}, 0),))
        # 保留另一来源，实际新数据进入新会话上下文。
        changed = SignalBindings(replace(session, sources=(changed_source, session.sources[1])), (_definition(),))
        # 实际来源身份纳入绑定hash。
        self.assertNotEqual(base.identity, changed.identity)
        # 同别名换成另一来源/字段明确可见。
        rebound = SignalBindings(session, (_definition(source="b", field="raw.voltage"),))
        # 旧引用没有污染新对象。
        self.assertEqual(base.source_ref("current").source_name, "a")
        # 新引用实际指向b，身份不同。
        self.assertEqual(rebound.source_ref("current").source_name, "b")
        # 原字段和来源一起进入缓存身份。
        self.assertNotEqual(base.identity, rebound.identity)

    def test_session_isolation_and_frozen_inputs(self):
        """跨会话同名绑定独立，冻结定义不能原地改写。

        参数: 无；相同来源名但session_id不同。
        返回: None；完整引用/身份不同，非法容器拒绝。
        异常: 冻结或断言失败由unittest报告。
        """
        # 每会话保存自己的来源上下文。
        first = SignalBindings(_session(), (_definition(),))
        # 新会话不能继承旧引用身份。
        second = SignalBindings(_session(session_id="session_b"), (_definition(),))
        # 同别名同字段也保留会话边界。
        self.assertNotEqual(first.source_ref("current"), second.source_ref("current"))
        # 会话实际身份进入执行缓存键。
        self.assertNotEqual(first.identity, second.identity)
        # 冻结字段禁止外部修改。
        with self.assertRaises(FrozenInstanceError):
            # 不允许运行中改变绑定定义。
            first.resolve("current").valid_for_ns = 100
        # 可变容器不能进入冻结计划。
        with self.assertRaises(TypeError):
            # 不自动tuple转换来掩盖调用者结构错误。
            SignalBindings(_session(), [_definition()])

    def test_joint_sync_requires_public_origin_or_explicit_evidence(self):
        """不同origin联合依赖拒绝，显式固定offset证据才通过。

        参数: 无；两相对来源、不同合成origin及offset=2ns。
        返回: None；独立分析允许，联合缺证据失败，核实声明可追溯。
        异常: 不符同步门槛时断言失败。
        """
        # 两别名分别实际定位来源a/b。
        definitions = (_definition(), _definition(name="voltage", source="b", field="raw.voltage"))
        # 共有起点已声明，联合输入可用。
        shared = SignalBindings(_session(), definitions)
        # 不仅比较各自首点数值0。
        shared.require_synchronized(("current", "voltage"))
        # 原source b新起点与a不同，即使相对时间均为0。
        session = _session()
        # offset只是映射数值，没有依据声明还不能证明同步。
        second_source = replace(session.sources[1], timebase=TimebaseSpec("other", TimeType.RELATIVE, "other-run"), offset_ns=2)
        # 当前会话保留真实不同时基事实。
        session = replace(session, sources=(session.sources[0], second_source))
        # 构造允许独立来源，不自动将联合任务判通过。
        separate = SignalBindings(session, definitions)
        # 单来源可以独立分析。
        separate.require_synchronized(("voltage",))
        # 同一节点请求联合计算才触发T02门槛。
        with self.assertRaisesRegex(ValueError, "同步依据：b"):
            # 没有证据不能联合。
            separate.require_synchronized(("current", "voltage"))
        # 明示合成核实依据，不代表真实硬件验证。
        evidence = SynchronizationEvidence("b", session.timebase, "synthetic calibration: source + 2ns")
        # 固定offset已在来源中声明，证据不会改写它。
        calibrated = SignalBindings(session, definitions, synchronization=(evidence,))
        # 实际显式校准后才通过联合依赖。
        calibrated.require_synchronized(("current", "voltage"))
        # 同步依据属于实际执行绑定身份。
        self.assertNotEqual(separate.identity, calibrated.identity)
        # 重复证据不能取第一个。
        with self.assertRaises(ValueError):
            # 两次声明同一来源产生歧义。
            SignalBindings(session, definitions, synchronization=(evidence, evidence))


# 只在直接运行时启动测试，不在被导入时创建运行状态。
if __name__ == "__main__":
    # 标准unittest报告失败，不吞输入错误。
    unittest.main()
