"""检查表达式能引用什么、怎样计算，以及缺失数据怎样影响结果。

输入是明示时钟、单位、范围和原字段的合成内存数据；输出为unittest断言。
先检查别名、单位、派生依赖和语法白名单，再让参考与NumPy各自从原值
完成转换、保持和求值；手算结果另行核对。三值逻辑区分True、False和未知，
结果可以被False决定时仍保留未知依赖原因。测试还核对数组形状和定宽类型。
验收对应T37—T39、T42、T52—T53；需要NumPy，不读取旧资源，不使用动态eval。
"""

# 真实回归断言，不调整预期让错误通过。
import unittest
# 明确替换冻结声明用于绑定隔离测试，不原位改模型。
from dataclasses import replace
# NumPy仅被测后端及布局核对。
import numpy as np
# 当前模型/输入，不以纯类名占位冒充执行。
from chronaxis.core import (MemoryRow, QualityFlag as Q, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType as D, SourceSpec, TimebaseSpec, TimeType)
# 静态编译、真实派生定义和独立标量解释。
from chronaxis.core.expression import DerivedDefinition, compile_expression
# 参考不调用被测数组执行器。
from chronaxis.core.expression_reference import evaluate_memory_reference, evaluate_reference
# 数组入口实际归一化/搜索/ufunc/三值mask。
from chronaxis.core.expression_numpy import evaluate_memory_numpy, evaluate_numpy
# direct context包装不执行数值计算。
from chronaxis.core.numeric import ScalarValue
# 只读列模型验证dtype/mask，array执行仍在独立后端。
from chronaxis.core.numeric_numpy import DTYPES, NumericArray


def _bindings(rows=None, definitions=None, *, derived_names=()):
    """构造可控原行、明确时钟和观测范围的真实计划绑定。

    参数: rows可选原字典序列；definitions可选完整SignalDefinition tuple；
        derived_names为派生统一空间声明。
    返回: SignalBindings，各原字段时间/序号稳定。
    异常: 真模型校验失败传播，不跳过来源/名称规则。
    """
    # 默认原单位A/V，数值类型明确float而非隐式cast。
    rows = rows if rows is not None else ({'raw_i': 6., 'raw_v': 400., 'raw_count': 2 ** 53 + 1, 'raw_u': 2 ** 64 - 1, 'raw_soc': 92.5, 'raw_mode': 1},)
    # 明示公共相对起点，无真实同步证据假设。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'expression-synthetic-v1')
    # 来源保留原字段及行身份，不改变原时间顺序。
    source = SourceSpec('sensor', clock, tuple(MemoryRow(index, values, index) for index, values in enumerate(rows)), observation_start_ns=0, observation_end_ns=len(rows)+1)
    # 会话包含原行且末端明示。
    session = SessionSpec('session', clock, 0, len(rows)+1, (source,))
    # 普通分析可以没有领域语义名。
    definitions = definitions if definitions is not None else (
        SignalDefinition('current', 'sensor', 'raw_i', D.FLOAT64, 'A', 2),
        SignalDefinition('voltage', 'sensor', 'raw_v', D.FLOAT64, 'V', 2),
        SignalDefinition('counter', 'sensor', 'raw_count', D.INT64, '1', 2),
        SignalDefinition('unsigned_id', 'sensor', 'raw_u', D.UINT64, '1', 2),
        SignalDefinition('soc', 'sensor', 'raw_soc', D.FLOAT64, 'test_percent', 2),
        SignalDefinition('mode', 'sensor', 'raw_mode', D.ENUM, '1', 2, choices=((0, 'Idle'), (1, 'Run'))))
    # 名称/原字段/identity由实际绑定层校验。
    return SignalBindings(session, definitions, derived_names=derived_names)


def _column(values):
    """只把同型ScalarValue装箱为array测试context。

    参数: values非空同类型逻辑标量序列。
    返回: NumericArray，invalid占位与原因明确。
    异常: 模型校验传播。
    """
    # dtype/enum域来自明示声明，不跨型promotion。
    dtype, labels = values[0].dtype, values[0].labels
    # 仅存储编码/原值，不进行被测数值计算。
    packed = [labels.index(value.value) if labels and value.valid else value.value if value.valid else 0 for value in values]
    # normal mask/所有quality独立打包。
    return NumericArray(dtype, np.array(packed, dtype=DTYPES[dtype]), np.array([value.valid for value in values], dtype=bool), np.array([int(value.quality) for value in values], dtype=np.uint16), labels)


class ExpressionTests(unittest.TestCase):
    """从原行到输出核对完整静态安全/类型/单位/三值契约。

    差分同时检查依赖诊断；手算例验证两后端共同逻辑政策。
    """

    def _compare(self, compiled, times=(0,), *, point=False):
        """从相同原memory独立执行两后端并核对完整输出。

        参数: compiled真实计划；times明确ns tuple；point控制真实末端。
        返回: 标量Evaluation tuple与实际ArrayEvaluation。
        异常: 数值/valid/诊断差异由unittest报告。
        """
        # reference独立归一化/保持/解释，不借数组真值。
        reference = evaluate_memory_reference(compiled, times, point=point)
        # NumPy真实原行批量转换/searchsorted/表达式ufunc。
        array = evaluate_memory_numpy(compiled, np.array(times, dtype=np.int64), point=point)
        # UNKNOWN和正常False分开。
        self.assertEqual([item.value.valid for item in reference], array.value.valid.tolist())
        # 结果原因与所有依赖原因都对照。
        self.assertEqual([int(item.value.quality) for item in reference], array.value.quality.tolist())
        # 决断已知逻辑不得丢未知原诊断。
        self.assertEqual([int(item.dependency_quality) for item in reference], array.dependency_quality.tolist())
        # 只在有效位置解释值，invalid占位不当真值。
        for index, item in enumerate(reference):
            # 两后端输出类型必须同静态root。
            self.assertEqual(item.value.dtype, array.value.dtype)
            # enum按相同声明标签恢复，其他保留native类型。
            if item.value.valid:
                # 只比较正常逻辑值。
                value = array.value.labels[int(array.value.values[index])] if array.value.labels else array.value.values[index].item()
                # 同样数值步骤不放宽单位/整数质量。
                self.assertEqual(item.value.value, value)
        # 供手算再检查真实标量结果。
        return reference, array

    def test_t37_optional_semantics_full_pipeline(self):
        """有无semantic_id不改变普通别名两后端执行值与质量。

        参数: 无；6A/4A/None实际原更新。
        返回: None。
        异常: 回归失败由unittest报告。
        """
        # 三行真实原值，缺失是明确更新而非过滤。
        definitions = (SignalDefinition('pack_current', 'sensor', 'raw', D.INT64, 'A', 2),)
        # 来源只有当前字段，普通分析不需语义目录。
        plain = _bindings(({'raw': 6}, {'raw': 4}, {'raw': None}), definitions)
        # 修改optional metadata，物理值/规则不改变。
        semantic = replace(plain, signals=(replace(definitions[0], semantic_id='battery.current'),))
        # 身份可变但分析真值必须相同。
        observed = []
        # 两个计划各自独立编译与执行，不继承上个binding。
        for bindings in (plain, semantic):
            # 合法表达式只使用简单别名。
            plan = compile_expression('pack_current > 5', bindings)
            # 包含真实更新及TTL，完整端点由后续TEMP验收。
            reference, _ = self._compare(plan, (0, 1, 2, 3))
            # 取实际结果比较可选语义差异。
            observed.append([(item.value.value if item.value.valid else None, item.value.quality) for item in reference])
        # 手算6>5真、4>5假、更新None后UNKNOWN。
        self.assertEqual([value for value, _ in observed[0]], [True, False, None, None])
        # Optional语义名不改变直接规则值/质量。
        self.assertEqual(observed[0], observed[1])

    def test_t38_blacklist_and_position(self):
        """属性/任意函数/下标/幂等执行前拒绝，位置与可用别名明确。

        参数: 无；非法DSL文本，不真实执行其内容。
        返回: None。
        异常: 预期编译错误由assertRaises核对。
        """
        # 使用当前合法输入，非法语法不是源数据问题。
        bindings = _bindings()
        # 每种未支持AST都应整体失败。
        invalid = ['battery.current > 5', 'signal("battery.current")', 'current[0]', 'current ** 2', 'current % 2',
                   'sum(current)', '__import__("os")', '(lambda x: x)(current)', '[x for x in current]',
                   'current if True else voltage', '{"x": current}', '(x := current)', 'current in (1, 2)',
                   'abs(*current)', 'isclose(current, current, **current)', 'not current', 'current and True', 'True+1',
                   'isclose(True, False, atol=0, rtol=0)', 'None', '1e999', '"arbitrary"']
        # 遍历独立非法类别，不能仅测试第一种。
        for text in invalid:
            # 定位具体输入失败而非执行任何内容。
            with self.subTest(text=text):
                # 失败为配置ValueError，不正常UNKNOWN。
                with self.assertRaises(ValueError):
                    # AST仅解析/白名单，没有eval。
                    compile_expression(text, bindings)
        # 点号错误具体提供禁止原因/位置/合法别名。
        with self.assertRaisesRegex(ValueError, '行1列1.*ast.Attribute.*current'):
            # 保留point syntax，不静默改name。
            compile_expression('battery.current > 5', bindings)

    def test_t52_units_and_literal_context(self):
        """裸常量比较/加减与乘除按设计单位推断，已知错单位拒绝。

        参数: 无；A/V明确且额外mA绑定未转换。
        返回: None。
        异常: 回归或预期单位拒绝由unittest核对。
        """
        # 原默认current=6A、voltage=400V。
        bindings = _bindings()
        # 输出单位和手算值同时验收。
        cases = [('current > 5', '1', True), ('voltage + 1', 'V', 401.), ('current*2', 'A', 12.),
                 ('voltage*current', 'W', 2400.), ('current/current', '1', 1.), ('1+voltage', 'V', 401.),
                 ('current*(1+2)', 'A', 18.), ('voltage+(1+2)', 'V', 403.)]
        # 每表达式静态单位与真实两后端都核对。
        for text, unit, value in cases:
            # 不改变原信号单位来凑静态输出。
            plan = compile_expression(text, bindings)
            # 真实单位推断结果。
            self.assertEqual(plan.root.unit, unit)
            # 真实两后端从原输出运行。
            reference, _ = self._compare(plan)
            # 明示手算值不依赖被测数组。
            self.assertEqual(reference[0].value.value, value)
        # 已知不同单位或不支持组合必须显式处理。
        for text in ('current+voltage', 'current>voltage', 'voltage*voltage'):
            # 不猜工程量纲或隐藏转换。
            with self.assertRaises(ValueError):
                # 未校验结果unit字段不能改数值。
                compile_expression(text, bindings)
        # 两字段同物理量但mA/A未显式转换仍拒绝。
        definitions = (SignalDefinition('a', 'sensor', 'x', D.FLOAT64, 'A', 2), SignalDefinition('b', 'sensor', 'y', D.FLOAT64, 'mA', 2))
        # 原a=1A、b=1000mA不是标签相同。
        mismatch = _bindings(({'x': 1., 'y': 1000.},), definitions)
        # 必须先归一化b再运算。
        with self.assertRaises(ValueError):
            # 相同量纲不足以隐藏倍率。
            compile_expression('a==b', mismatch)

    def test_t53_chain_enum_and_three_value_table(self):
        """链式比较为三值and；枚举域和完整逻辑表保留依赖诊断。

        参数: 无；SOC92.5/93/None及9对三值输入。
        返回: None。
        异常: 差分/手算失败由unittest报告。
        """
        # 声明未知百分比标签，普通分析允许但未验证单位状态。
        definition = SignalDefinition('soc', 'sensor', 'raw', D.FLOAT64, 'test_percent', 2)
        # 点93恰好不在右半开比较值域。
        bindings = _bindings(({'raw': 92.5}, {'raw': 93.}, {'raw': None}), (definition,))
        # 编译链式比较不依赖Python ndarray bool。
        plan = compile_expression('92<=soc<93', bindings)
        # 两比较合成三值结果。
        reference, _ = self._compare(plan, (0, 1, 2))
        # 明确手算真/假/未知。
        self.assertEqual([item.value.value if item.value.valid else None for item in reference], [True, False, None])
        # 逻辑输入是原生BOOL，不以0/1当true。
        logic_bindings = _bindings(({'x': True, 'y': False},), (SignalDefinition('a', 'sensor', 'x', D.BOOL, '1', 2), SignalDefinition('b', 'sensor', 'y', D.BOOL, '1', 2)))
        # 全部9对手算三值组合。
        pairs = [(a, b) for a in (True, False, None) for b in (True, False, None)]
        # 原UNKNOWN分别带MISSING和STALE，用诊断确认保留。
        left = [ScalarValue(a, D.BOOL, a is not None, Q.NONE if a is not None else Q.MISSING) for a, _ in pairs]
        # 两个不同原因能同时追溯。
        right = [ScalarValue(b, D.BOOL, b is not None, Q.NONE if b is not None else Q.STALE) for _, b in pairs]
        # 手算表独立固定，不调用reference逻辑生成期望。
        expectations = {'and': [True, False, None, False, False, False, None, False, None], 'or': [True, True, True, True, False, None, True, None, None]}
        # 每种逻辑真正批量执行9行。
        for operation in ('and', 'or'):
            # 当前绑定不跨任务继承context。
            plan = compile_expression(f'a {operation} b', logic_bindings)
            # 数组独立三值mask求值。
            array = evaluate_numpy(plan, {'a': _column(left), 'b': _column(right)}, logic_bindings)
            # 标量逐点独立验证完整表与诊断。
            for index, (a, b) in enumerate(zip(left, right)):
                # reference输入不是被测array结果。
                result = evaluate_reference(plan, {'a': a, 'b': b}, logic_bindings)
                # 手算已知/未知真值。
                expected = expectations[operation][index]
                # 不能把Unknown普通False。
                self.assertEqual(result.value.value if result.value.valid else None, expected)
                # 数组valid应和参考/手算一致。
                self.assertEqual(bool(array.value.valid[index]), expected is not None)
                # 所有依赖原因都保留，known决断也一样。
                self.assertEqual(result.dependency_quality, a.quality | b.quality)
                # 数组诊断独立并集与原原因一致。
                self.assertEqual(int(array.dependency_quality[index]), int(a.quality | b.quality))
        # 真正enum原编码变标签后比较，不直接与任意字符串处理。
        enum = compile_expression('mode == "Run"', _bindings())
        # 手算原码1对应Run，结果true。
        self.assertTrue(self._compare(enum)[0][0].value.value)
        # 未声明标签在执行前整体拒绝。
        with self.assertRaises(ValueError):
            # 不用任意标签当unknown样本绕过域检查。
            compile_expression('mode == "Missing"', _bindings())

    def test_isclose_signature_asymmetry_and_precision(self):
        """isclose显式容差、非对称判据及整数精度严格执行。

        参数: 无；100与110、rtol=.095及大奇数。
        返回: None。
        异常: 回归/预期签名拒绝由unittest报告。
        """
        # 同单位同dtype输入，非对称判据不被改成库默认对称策略。
        defs = (SignalDefinition('a', 'sensor', 'x', D.FLOAT64, 'A', 2), SignalDefinition('b', 'sensor', 'y', D.FLOAT64, 'A', 2))
        # 手算abs(100-110)=10，阈值10.45或9.5。
        bindings = _bindings(({'x': 100., 'y': 110.},), defs)
        # 正反方向必须有不同结果。
        for expr, expected in [('isclose(a,b,atol=0,rtol=.095)', True), ('isclose(b,a,atol=0,rtol=.095)', False)]:
            # 正常固定签名实际编译。
            plan = compile_expression(expr, bindings)
            # 两后端真实float判据与手算一致。
            self.assertEqual(self._compare(plan)[0][0].value.value, expected)
        # 所有容差须明确、原literal有限非负，不允许信号容差。
        for expr in ('isclose(a,b)', 'isclose(a,b,atol=0)', 'isclose(a,b,atol=-1,rtol=0)', 'isclose(a,b,atol=a,rtol=0)', 'isclose(a,b,atol=True,rtol=0)', 'isclose(a,b,atol=0,rtol=0,extra=1)'):
            # 不默认补容差或吞未知keyword。
            with self.assertRaises(ValueError):
                # 单次AST配置整体失败。
                compile_expression(expr, bindings)
        # 正常大奇数integer需要float路径时明确PRECISION_LOSS。
        plan = compile_expression('isclose(counter,counter,atol=0,rtol=0)', _bindings())
        # 两侧即使相同也不能跳过先验float精度。
        self.assertEqual(self._compare(plan)[0][0].value.quality, Q.PRECISION_LOSS)

    def test_derived_dependency_graph_cycles_and_identity(self):
        """真实派生接线、完整依赖和循环/缺项在执行前验收。

        参数: 无；power与twice两个W派生。
        返回: None。
        异常: 回归/预期配置异常由unittest报告。
        """
        # 派生名称先与signals统一登记，不能仅类名占位。
        bindings = _bindings(derived_names=('power', 'twice'))
        # 同一物理W单位通过实际乘法和常量放大推断。
        derived = (DerivedDefinition('power', 'voltage*current', 'W'), DerivedDefinition('twice', 'power*2', 'W'))
        # 当前根实际依赖展开到原信号，不保留派生名假列。
        plan = compile_expression('twice>1000', bindings, derived=derived)
        # 依赖只含真实已解码current/voltage。
        self.assertEqual(plan.dependencies, ('current', 'voltage'))
        # 实际4800W>1000，两个后端从原行运行。
        self.assertTrue(self._compare(plan)[0][0].value.value)
        # 派生代码变化必须进入执行身份。
        changed = compile_expression('twice>1000', bindings, derived=(derived[0], replace(derived[1], expr='power*3')))
        # 相同root文本不是可复用当前执行绑定/派生证明。
        self.assertNotEqual(plan.identity, changed.identity)
        # 未提供完整已登记derived表达式是缺项。
        with self.assertRaises(ValueError):
            # 不以已声明名称冒充有实现。
            compile_expression('current>5', bindings)
        # 两个节点互相引用，完整路径可定位。
        with self.assertRaisesRegex(ValueError, '循环依赖.*power.*twice.*power'):
            # 单次编译不继承上次成功节点cache。
            compile_expression('current>5', bindings, derived=(replace(derived[0], expr='twice'), derived[1]))
        # 未被root使用的坏派生仍整体校验。
        with self.assertRaises(ValueError):
            # 阶段配置不能藏非法函数到unused节点。
            compile_expression('current>5', bindings, derived=(replace(derived[0], expr='signal("x")'), derived[1]))
        # 派生单位声明不同不能偷偷只改标签。
        with self.assertRaises(ValueError):
            # V*A输出W，不能自动缩放成kW。
            compile_expression('twice>1000', bindings, derived=(replace(derived[0], unit='kW'), derived[1]))

    def test_t42_actual_mapping_ttl_and_point_cache_isolation(self):
        """同别名重映射/有效期改变不继承旧值、转换或计划身份。

        参数: 无；同原行6A与4000mA显式映射。
        返回: None。
        异常: 回归/预期绑定冲突由unittest报告。
        """
        # 明确两个原字段代表不同实际数值。
        definition = SignalDefinition('current', 'sensor', 'first', D.FLOAT64, 'A', 2)
        # 一行输入仍有明示2ns观测，TTL可独立测试。
        original = _bindings(({'first': 6., 'second': 4000.},), (definition,))
        # 重绑定mA字段，额外scale只应用一次。
        mapped = replace(original, signals=(replace(definition, field='second', input_unit='mA', scale=.001, mapping_version='map-2'),))
        # TTL改变本身也改变实际执行身份。
        expired = replace(original, signals=(replace(definition, valid_for_ns=1),))
        # 三个计划各自真实编译/执行，不全局缓存语义名。
        plans = [compile_expression('current>5', bindings) for bindings in (original, mapped, expired)]
        # 完整身份各自唯一，即使原字符串完全相同。
        self.assertEqual(len({plan.identity for plan in plans}), 3)
        # 手算6A>true、4A>false，TTL=1ns查询1ns未知。
        self.assertTrue(self._compare(plans[0], (0, 1))[0][1].value.value)
        # 新映射不继承旧6A结果。
        self.assertFalse(self._compare(plans[1], (0, 1))[0][1].value.value)
        # 新有效期不继承旧2ns政策。
        self.assertEqual(self._compare(plans[2], (0, 1))[0][1].value.quality, Q.STALE)
        # 明确给旧计划新绑定应先拒绝，而非求值新列。
        with self.assertRaises(ValueError):
            # 不以same name证明可执行身份一致。
            evaluate_reference(plans[0], {'current': ScalarValue(4., D.FLOAT64)}, mapped)
        # 数组也同样要求当前真实绑定身份。
        with self.assertRaises(ValueError):
            # 所有列同长也不足以绕过真实身份。
            evaluate_numpy(plans[0], {'current': _column([ScalarValue(4., D.FLOAT64)])}, mapped)
        # 局部point cache不继承上次当前值。
        self.assertTrue(evaluate_reference(plans[0], {'current': ScalarValue(6., D.FLOAT64)}, original).value.value)
        # 再次执行相同计划、不同明确context应更新结果。
        self.assertFalse(evaluate_reference(plans[0], {'current': ScalarValue(4., D.FLOAT64)}, original).value.value)

    def test_integer_boundaries_static_types_and_unary_quality(self):
        """超宽比较阈值精确；混合信号/越界算术literal执行前拒绝。

        参数: 无；大整数相邻阈值及unsigned最大值。
        返回: None。
        异常: 回归/预期配置异常由unittest报告。
        """
        # 默认counter=2**53+1、unsigned_id=uint64 max。
        bindings = _bindings()
        # 阈值在原生整数域，不先转float。
        cases = [(f'counter>{2**53}', True), (f'counter<{2**100}', True),
                 (f'{-(2**100)}<counter', True), (f'unsigned_id>{2**63-1}', True),
                 (f'unsigned_id>{2**64-1}', False), (f'{2**100}<unsigned_id', False)]
        # 常量在左/右都完整手算对照。
        for text, expected in cases:
            # 大边界不会成为额外无界正常输出dtype。
            plan = compile_expression(text, bindings)
            # 两后端实际整数判定。
            self.assertEqual(self._compare(plan)[0][0].value.value, expected)
        # 不同dtype信号算术/负uint字面量/超界signed算术literal编译失败。
        for text in ('counter+unsigned_id', 'unsigned_id+-1', f'counter+{2**63}', f'isclose(counter,{2**100},atol=0,rtol=0)'):
            # 配置错误不伪装样本UNKNOWN。
            with self.assertRaises(ValueError):
                # 静态dtype先于数据有效性检查。
                compile_expression(text, bindings)
        # Float字面量是已授权路径，但大奇数参与必须精度失败。
        self.assertEqual(self._compare(compile_expression('counter+.5', bindings))[0][0].value.quality, Q.PRECISION_LOSS)
        # BUG-M1-007：纯literal相同操作数交换顺序不能改变共同dtype。
        for text in ('9223372036854775808+1', '1+9223372036854775808'):
            # 静态选择uint64且两个operand都能表示。
            plan = compile_expression(text, bindings)
            # 不借NumPy隐式promotion得到错误float。
            self.assertEqual(plan.root.dtype, D.UINT64)
            # 真实两后端得到精确手算大整数。
            self.assertEqual(self._compare(plan)[0][0].value.value, 2 ** 63 + 1)
        # abs(min)/neg(min)通过完整memory→AST运行而非只数值单测。
        min_binding = _bindings(({'raw': -(2 ** 63)},), (SignalDefinition('minimum', 'sensor', 'raw', D.INT64, '1', 2),))
        # 两种单目正常值都超signed范围。
        for text in ('abs(minimum)', '-minimum'):
            # 编译允许，实际数值失败返回质量。
            self.assertEqual(self._compare(compile_expression(text, min_binding))[0][0].value.quality, Q.OVERFLOW)

    def test_shapes_constants_not_and_atomic_memory_updates(self):
        """错误列布局执行前拒绝，常量/空轴及原子更新不制造真值。

        参数: 无；同时间V400/I0→V0/I10真实memory原子行。
        返回: None。
        异常: 回归/预期shape错误由unittest报告。
        """
        # Constant不需来源列，但batch输出shape必须明确。
        binding = _bindings()
        # not仅布尔，按手算True取反。
        self.assertFalse(self._compare(compile_expression('not True', binding))[0][0].value.value)
        # 纯常量表达式空查询可返回合法空列。
        self._compare(compile_expression('True', binding), ())
        # 不允许无依赖batch猜行数。
        with self.assertRaises(ValueError):
            # 必须显式size，不能借未用来源推断N。
            evaluate_numpy(compile_expression('True', binding), {}, binding)
        # 依赖两列仍严格验证所有shape，不broadcast。
        plan = compile_expression('voltage*current', binding)
        # 列长2与1在计算前拒绝。
        with self.assertRaises(ValueError):
            # 不重复第二列来凑shape。
            evaluate_numpy(plan, {'current': _column([ScalarValue(1., D.FLOAT64)]*2), 'voltage': _column([ScalarValue(1., D.FLOAT64)])}, binding)
        # 缺列/额外列不能从全局缓存取值。
        with self.assertRaises(ValueError):
            # 真实context键精确匹配dependencies。
            evaluate_reference(plan, {'current': ScalarValue(1., D.FLOAT64)}, binding)
        # 错dtype不是样本质量问题。
        with self.assertRaises(TypeError):
            # float信号不能接裸整型语义替代。
            evaluate_reference(compile_expression('current>5', binding), {'current': ScalarValue(6, D.INT64)}, binding)
        # 实际两个原子行都只有0功率，无遍历中间400*10假值。
        definitions = (SignalDefinition('voltage', 'sensor', 'v', D.INT64, 'V', 2), SignalDefinition('current', 'sensor', 'i', D.INT64, 'A', 2))
        # 新核心接已有同行两字段，不改变旧消息过程。
        atomic = _bindings(({'v': 400, 'i': 0}, {'v': 0, 'i': 10}), definitions)
        # expression每查询点看到整组更新后真实值。
        reference, _ = self._compare(compile_expression('voltage*current>0', atomic), (0, 1))
        # 手算两个正常False，后续TEMP rising不得产生事件。
        self.assertEqual([item.value.value for item in reference], [False, False])
