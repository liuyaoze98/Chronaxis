"""检查未读取文件时能校验哪些声明，并防止静态配置被当成可执行输入。

输入为来源声明和已有真实内存夹具，输出为unittest断言。声明中的路径
即使不存在，也能检查名称、单位、表达式语法和派生环；此时字段是否存在、
文件内容是否有效仍未验证。静态表达式树及绑定必须拒绝执行，声明身份只
反映配置变化。真实内存编译仍检查实际字段，不用伪样本绕过存在性门槛。
测试不打开声明中的输入文件，NumPy结果也不作为静态校验的独立参考。
"""

# 标准测试及冻结对象变体，不创建文件。
import unittest
from dataclasses import replace
from unittest.mock import patch
# 真实核心与专用声明接口，保持类型边界。
from chronaxis.core.binding import SignalDefinition, SignalBindings, SynchronizationEvidence
from chronaxis.core.declarations import DeclarationBindings, DeclaredSource
from chronaxis.core.expression import DerivedDefinition, compile_expression, validate_expression
from chronaxis.core.expression_reference import require_context
from chronaxis.core.models import Interval, MemoryRow, SessionSpec, SourceSpec, TimebaseSpec
from chronaxis.core.types import SignalDType as D, TimeType


def _declarations(*, path='absent.csv', valid_for=10, source='table'):
    """建立显式相对来源声明，没有文件内容或实际字段存在证明。

    参数: path配置定位；valid_for正纳秒；source来源名。
    返回: DeclarationBindings，仅静态身份。
    异常: 模型结构/名称校验失败传播。
    """
    # 公共起点声明与路径身份保持独立。
    timebase = TimebaseSpec('analysis', TimeType.RELATIVE, 'declared_origin')
    # 原字段含点号合法，DSL只绑定简单current别名。
    definition = SignalDefinition('current', source, 'raw.current', D.FLOAT64, 'A', valid_for)
    # 不构造空SessionSpec或虚拟MemoryRow。
    return DeclarationBindings('session', timebase, Interval(0, 20), (DeclaredSource(source, timebase, path),), (definition,))


class PlanBindingTests(unittest.TestCase):
    """核对声明静态校验与真实可执行编译的严格边界。

    六组断言覆盖读入副作用、白名单、派生、来源同步和T42身份隔离。
    """

    def test_static_without_io_and_forbidden_execution(self):
        """不存在的输入也可静态校验，但树与绑定禁止执行。

        参数: 无，手写显式声明。
        返回: None，静态依赖/类型和执行拒绝均通过。
        异常: 任何输入open或边界放宽使测试失败。
        """
        # 文件系统open一律抛错，证明静态路径未读取输入。
        with patch('builtins.open', side_effect=AssertionError('不允许输入I/O')):
            # 校验只使用声明的单位与别名。
            bindings = _declarations()
            # 点号原字段不进入DSL属性访问。
            result = validate_expression('current > 5', bindings)
        # 结果明确为BOOL且实际依赖已展开。
        self.assertEqual((result.root.dtype, result.dependencies), (D.BOOL, ('current',)))
        # 执行编译不能接静态声明。
        with self.assertRaisesRegex(TypeError, '真实SignalBindings'):
            # 不为满足实际字段验证造假行。
            compile_expression('current > 5', bindings)
        # 标量和NumPy共用的执行context门槛拒绝静态树。
        with self.assertRaisesRegex(TypeError, 'CompiledExpression'):
            # 即使空列映射也不把声明当可执行绑定。
            require_context(result, {}, bindings)

    def test_dsl_names_units_and_cycles(self):
        """白名单与派生环使用真实编译器同一政策。

        参数: 无，非法表达式和派生构造。
        返回: None，位置/别名/循环错误被报告。
        异常: 放宽DSL或隐藏未引用环使测试失败。
        """
        # 静态绑定不含sample值，也不会影响类型判定。
        bindings = _declarations()
        # 所有非法表达式走同一白名单入口。
        for text in ('battery.current > 5', 'signal("battery.current")', 'current[0]', 'current ** 2', 'unknown > 5'):
            # 每例有独立错误定位。
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, '行1列'):
                # 不做自动名称替换。
                validate_expression(text, bindings)
        # 已知单位冲突不因静态模式免除。
        with self.assertRaises(ValueError):
            # A表达式不能直接声称V。
            validate_expression('current', bindings, unit='V')
        # 未被根用到的派生环也必须拒绝。
        cyclic = replace(bindings, derived_names=('first', 'second'))
        # 显式两节点环，不依赖执行数据发现。
        derived = (DerivedDefinition('first', 'second', 'A'), DerivedDefinition('second', 'first', 'A'))
        # 原信号根也不能隐藏坏配置。
        with self.assertRaises(ValueError):
            # 所有派生统一校验。
            validate_expression('current', cyclic, derived=derived)

    def test_declared_identity_changes_and_original_mapping(self):
        """路径、TTL、来源和转换改变静态身份，不误称实际输入SHA。

        参数: 无，独立配置变体。
        返回: None，声明身份不同且相同配置稳定。
        异常: 缓存串用或丢失定位使断言失败。
        """
        # 基线静态配置没有访问不存在的文件。
        base = _declarations()
        # 相同内容获得确定身份。
        self.assertEqual(base.identity, _declarations().identity)
        # 不同来源/路径/TTL都不能复用旧声明身份。
        variants = (_declarations(path='another.csv'), _declarations(valid_for=11), _declarations(source='other'), replace(base, signals=(replace(base.signals[0], input_unit='mA', scale=.001),)))
        # 完整表达式身份也包含绑定差异。
        identities = {validate_expression('current > 5', item).identity for item in (base, *variants)}
        # 五份不同声明全部隔离。
        self.assertEqual(len(identities), 5)
        # 原始字段保持完整点号，无隐式替换。
        self.assertEqual(base.resolve('current').field, 'raw.current')

    def test_name_and_source_conflicts(self):
        """静态名称空间和来源定位一样严格，字段存在状态保持未验证。

        参数: 无，声明变体。
        返回: None，重名/关键字/未知来源都拒绝。
        异常: 配置冲突未报告使断言失败。
        """
        # 模型已经校验全部单项类型。
        base = _declarations()
        # 来源重复不能取第一个。
        with self.assertRaises(ValueError):
            # 原顺序保留但拒绝重复ID。
            replace(base, sources=base.sources * 2)
        # 信号/派生同名拒绝。
        with self.assertRaises(ValueError):
            # 不自动添加派生后缀。
            replace(base, derived_names=('current',))
        # 未登记来源也不能静态通过。
        with self.assertRaises(ValueError):
            # 真实字段内容不是本接口的存在证明。
            replace(base, signals=(replace(base.signals[0], source='unknown'),))
        # Python关键字也属于名称错误。
        with self.assertRaises(ValueError):
            # 不通过DSL替换绕过。
            replace(base, derived_names=('class',))

    def test_cross_source_sync_only_when_jointly_used(self):
        """联合来源需要公共起点或显式依据，单来源不被无关缺项阻塞。

        参数: 无，两不同相对起点声明。
        返回: None，独立/联合/明示校准行为符合设计。
        异常: 擅自推断同步使断言失败。
        """
        # 基线公共分析时基来自一个已声明来源。
        base = _declarations()
        # 另一个来源有不同origin，offset0不能证明同步。
        other = DeclaredSource('other', TimebaseSpec('other_clock', TimeType.RELATIVE, 'different_origin'), 'other.csv')
        # 第二信号保持明确单位，没有数值输入。
        signal = replace(base.signals[0], name='second', source='other')
        # 模型先允许独立分析不同来源。
        joint = replace(base, sources=(*base.sources, other), signals=(*base.signals, signal))
        # 单来源根正常静态通过。
        self.assertEqual(validate_expression('current > 5', joint).dependencies, ('current',))
        # 真正联合根在执行前拒绝缺少同步依据。
        with self.assertRaisesRegex(ValueError, '缺少同步依据'):
            # 不因为时间数值相同而通过。
            validate_expression('current + second', joint)
        # 调用者核实固定映射说明，不自动生成工程依据。
        proof = SynchronizationEvidence('other', base.timebase, '合成夹具明确固定offset=0，共同实验起点')
        # 显式声明之后同一联合根通过。
        self.assertEqual(validate_expression('current + second', replace(joint, synchronization=(proof,))).dependencies, ('current', 'second'))

    def test_actual_memory_gate_remains(self):
        """静态扩展没有放松原字段存在及真实输入编译身份。

        参数: 无，真实memory行与空来源对照。
        返回: None，实际执行树可编译、缺实际字段仍失败。
        异常: 原门槛回归使断言失败。
        """
        # 与静态声明共享契约，数据只在真实来源中提供。
        base = _declarations()
        # 所有MemoryRow用显式关键字避免参数顺序误传。
        source = SourceSpec('table', base.timebase, (MemoryRow(time_ns=0, values={'raw.current': 6.0}, sequence=0),))
        # 请求域与实际观测域分开。
        session = SessionSpec('session', base.timebase, 0, 20, (source,))
        # 真实绑定生成实际内容身份。
        actual = SignalBindings(session, base.signals)
        # 当前根可执行编译正常。
        compiled = compile_expression('current > 5', actual)
        # 相同声明也不与实际内容身份合并。
        self.assertNotEqual(compiled.identity, validate_expression('current > 5', base).identity)
        # 空实际来源不能冒充已经存在的字段。
        with self.assertRaisesRegex(ValueError, '原字段不存在'):
            # 不改原SignalBindings契约来适配静态配置。
            SignalBindings(replace(session, sources=(replace(source, rows=()),)), base.signals)
