"""为版本4表达式编译一次性单位转换，统一处理当前单位与函数规则。

输入为已校验绑定和AST，输出包含unit_convert节点的不可变表达式树。
先解释裸常量的单位，再统一兼容量的尺度，最后推导结果单位及数值类型。
编译只使用声明与常量。clip的两个边界均无信号依赖时，标量核在此判定
其顺序；编译器不读取日志或求样本值。
温度偏移、量种和整数精度规则不能通过只改单位标签绕过。
"""

# 复用白名单语法和类型规则；所有量种关系来自同一单位注册表。
import ast
from dataclasses import replace
from .expression import _SyntaxCompiler, ExprNode, _node
from .expression_math_v4 import MATH_FUNCTIONS, check_integer_leaves, compile_math
from .lookup_compiler import compile_lookup
from .expression_integer_v4 import INTEGER_FUNCTIONS, compile_integer
from .enum_codes import compile_enum_code
from .numeric import INTEGER_BOUNDS
from .types import SignalDType as D
from . import unit_registry as units


def numeric_coefficient(value):
    """将精确有理系数压为整数或float，供已选后端执行。

    参数: value为Fraction。
    返回: 分母为1时返回int，否则返回float。
    异常: 不能表示的浮点范围错误由调用者/倍率模型检查。
    """
    # 保留整数路径，不能把无损倍率1000提前变成浮点。
    return value.numerator if value.denominator == 1 else float(value)


class UnitCompiler(_SyntaxCompiler):
    """在原受限语法上接入v4单位、常量和转换规则。

    每次编译独享状态。声明单位在裸常量适配之前保留，转换只写入树一次；
    数值执行根据节点系数转换，编译器不逐条处理数据。
    """

    def __init__(self, bindings, derived, extensions=None):
        """建立绑定并检查本版本已经开放的函数名冲突。

        参数: bindings为v4绑定，derived为完整派生声明tuple。
        返回: None。
        异常: ValueError为别名与本版本函数重名；其余声明错误沿原校验传播。
        """
        # 内置函数名称不能再作为信号、派生或参数别名。
        super().__init__(bindings, derived)
        self.extensions = extensions
        reserved = {'quantity', 'to_unit', 'where', 'enum_code', 'lookup'} | MATH_FUNCTIONS | INTEGER_FUNCTIONS
        if extensions is not None:
            reserved.update(extensions.functions)
        conflicts = reserved.intersection((*self.signals, *self.derived, *self.parameters))
        if conflicts:
            raise ValueError('v4名称与函数冲突：' + ', '.join(sorted(conflicts)))

    def _known_node(self, result):
        """按v4目录判定组合结果的单位状态，不提升未知输入的可信度。

        参数: result为已编译ExprNode。
        返回: 单位状态准确的新节点或原节点。
        异常: 非法单位文本按编译错误传播。
        """
        # name状态来自信号完整转换验证，不能用已知目标标签覆盖未验证输入。
        if result.operator == 'name':
            return result
        verified = units.resolve_unit(result.unit) is not None and all(arg.unit_status == 'verified' for arg in result.args)
        return replace(result, unit_status='verified' if verified else 'unverified')

    def _name(self, node):
        """取得信号/派生原声明尺度，附带已有输入转换的类型提升依据。

        参数: node为Name AST。
        返回: 已校验ExprNode。
        异常: 名称/循环/声明错误沿原编译器传播。
        """
        # 保留mV等声明尺度，使x>500里的500仍是mV。
        result = super()._name(node)
        definition = self.signals.get(node.id)
        if definition is not None and getattr(definition, 'unit_conversion_promoted', False):
            result = replace(result, conversion_promoted=True)
        return result

    def _convert(self, child, target, node, *, explicit=False):
        """为兼容单位生成一次仿射转换，不重复应用源层的DBC或标定系数。

        参数: child为当前数值表示；target为单位文本；node定位；explicit保留输出尺度。
        返回: 原节点或unit_convert节点，dtype在编译期确定。
        异常: ValueError为非数值转换、未知关系、量种不兼容或不可表示倍率。
        """
        # 同标签的未知单位可以继续使用，但不伪造已验证转换。
        target_unit = units.resolve_unit(target)
        label = units.output_label(target_unit, target) if target_unit is not None else target
        if child.unit == target or child.unit == label:
            return replace(child, unit=label, unit_explicit=explicit or child.unit_explicit)
        if child.dtype not in (*INTEGER_BOUNDS, D.FLOAT64):
            self._error(node, '单位转换只支持数值')
        source_unit = units.resolve_unit(child.unit)
        if source_unit is None or target_unit is None:
            self._error(node, f'未登记单位转换：{child.unit}→{target}')
        # 原子别名使用规范名；倍率为1的复合目标使用稳定名称，其他保留可解析输入。
        target = label
        try:
            scale, offset = units.conversion(source_unit, target_unit)
            factor = scale.to_float() if scale.pi_power else numeric_coefficient(scale.factor)
            # to_float还检查下溢到零，不能直接float极小Fraction。
            if type(factor) is float:
                factor = scale.to_float()
            shift = numeric_coefficient(offset)
        except (TypeError, ValueError, OverflowError) as error:
            self._error(node, str(error))
        # 整数倍且整数偏移保留原整数类型，其余必须有float容纳小数。
        promoted = child.dtype in INTEGER_BOUNDS and (type(factor) is not int or type(shift) is not int)
        dtype = D.FLOAT64 if promoted else child.dtype
        if factor == 1 and shift == 0:
            return replace(child, unit=target, unit_explicit=explicit or child.unit_explicit)
        return ExprNode('unit_convert', dtype, target, child.unit_status, (child,),
                        value=(factor, shift), aliases=child.aliases, constant=child.constant,
                        conversion_promoted=promoted or child.conversion_promoted,
                        unit_explicit=explicit, typed_constant=child.typed_constant)

    def _canonical(self, child, node):
        """把已知数值换到该量种的固定基准，未知标签保持。

        参数: child为节点，node为错误位置。
        返回: 已转换节点；逻辑/枚举不作数值换算。
        异常: 单位或转换边界错误传播。
        """
        # 不是每个结果都是数值，BOOL和枚举仍沿原协议。
        if child.dtype not in (*INTEGER_BOUNDS, D.FLOAT64):
            return child
        unit = units.resolve_unit(child.unit)
        return child if unit is None else self._convert(child, units.canonical_unit(unit).symbol, node)

    def _final_unit(self, root, unit, node):
        """在表达式输出边界同时转换目标数值和标签。

        参数: root为表达式树；unit为显式输出单位或None；node定位。
        返回: 显式目标优先，否则用规范基准。
        异常: 不兼容目标或未知转换明确报错。
        """
        # to_unit和quantity直接作为根时保留其明确尺度，复合运算再按量种规范化。
        if unit is not None:
            return self._convert(root, unit, node, explicit=True)
        return root if root.unit_explicit else self._canonical(root, node)

    def _context(self, literal, other, node, *, arithmetic):
        """复用定宽字面量检查，同时保持新单位的验证状态。

        参数: literal/other为数值节点；node定位；arithmetic区分算术和比较。
        返回: 按上下文检查过的节点。
        异常: 类型、范围或枚举域错误沿原检查传播。
        """
        # 纯常量仍需保持旧精度检查，不给BOOL或ENUM增加隐式数值转换。
        if literal.typed_constant:
            # quantity已经明确单位，只借用数值字面量的定宽/精度适配，不再重标单位。
            result = super()._context(replace(literal, constant=True), other, node, arithmetic=arithmetic)
            result = replace(result, constant=False, typed_constant=True)
        else:
            result = super()._context(literal, other, node, arithmetic=arithmetic)
        return self._known_node(result) if result.args else result

    def _units(self, operator, left, right, node, declared_unit=None):
        """先解释裸常量，再按兼容量换算，独立处理温度加减。

        参数: operator为add/sub/compare/mul/div；左右节点及错误位置；declared_unit为未知组合标签。
        返回: 已转换左右节点与结果单位。
        异常: ValueError为不兼容量种、温度组合或未登记关系。
        """
        # 单一对方的原声明单位是裸常量锚点，quantity不是裸常量。
        if operator in ('add', 'sub', 'compare'):
            if left.constant and not right.constant and left.dtype in (*INTEGER_BOUNDS, D.FLOAT64):
                left = replace(left, unit=right.unit, unit_status=right.unit_status)
            if right.constant and not left.constant and right.dtype in (*INTEGER_BOUNDS, D.FLOAT64):
                right = replace(right, unit=left.unit, unit_status=left.unit_status)
        a, b = units.resolve_unit(left.unit), units.resolve_unit(right.unit)
        if a is None or b is None:
            # 未知组合继续要求明确标签，不能借已知输出单位伪造关系证明。
            return super()._units(operator, left, right, node, declared_unit)
        try:
            if operator in ('add', 'sub', 'compare'):
                roles = (a.temperature_role, b.temperature_role)
                if operator != 'compare' and 'absolute' in roles:
                    if roles == ('absolute', 'absolute') and operator == 'sub':
                        result_unit = 'delta_K'
                    elif roles == ('absolute', 'delta') or (roles == ('delta', 'absolute') and operator == 'add'):
                        result_unit = 'K'
                    else:
                        raise ValueError('绝对温度仅允许相减得到温差，或加减温差；裸常量按当前温度单位解释')
                else:
                    units.conversion(a, b)
                    result_unit = '1' if operator == 'compare' else units.canonical_unit(a).symbol
                return self._canonical(left, node), self._canonical(right, node), result_unit
            # 必须先检查偏移单位，不能用自动转K绕过摄氏乘除限制。
            combined = units.multiply(a, b) if operator == 'mul' else units.divide(a, b)
            return self._canonical(left, node), self._canonical(right, node), units.canonical_unit(combined).symbol
        except (TypeError, ValueError) as error:
            self._error(node, str(error))

    def _binary(self, operator, left, right, node, declared_unit=None):
        """复用原定宽编译规则，并按新目录确定结果单位状态。

        参数: operator、左右节点、node及可选声明标签与基类相同。
        返回: 不可变数值/比较节点。
        异常: 原类型校验和新单位校验错误直接传播。
        """
        # 单位转换产生的float提升由基类显式标志接线，不使用NumPy隐式promotion。
        return self._known_node(super()._binary(operator, left, right, node, declared_unit))

    def _where(self, node):
        """编译只在条件已知时选取一条数值分支的节点。

        参数: node为where调用AST；三个位置参数都必须能通过静态检查。
        返回: 包含完整依赖的节点，两条分支已统一单位和dtype。
        异常: ValueError为签名、非布尔条件、类型/量种不兼容或字面量越界。
        """
        # 即使条件为常量，未选路径同样要做名称、安全、类型和单位检查。
        if len(node.args) != 3 or node.keywords:
            self._error(node, 'where需要三个位置参数：条件、真分支、假分支')
        condition, left, right = (self.visit(arg) for arg in node.args)
        if condition.dtype is not D.BOOL:
            self._error(node.args[0], 'where条件必须是BOOL')
        if any(branch.dtype not in (*INTEGER_BOUNDS, D.FLOAT64) for branch in (left, right)):
            self._error(node, 'where的两个分支都必须是数值')
        # abs(超宽整数)等子树即使永远不被选中也不能隐藏非法输入。整数比较
        # 允许的无界阈值已编译成专用节点字段，不是需要按定宽装箱的const叶。
        check_integer_leaves(self, (condition, left, right), node)

        # 使用比较所需的同量种关系：绝对温度可以互选，但不能与温差互选。
        # 它还会先把裸常量解释为另一侧原声明单位，之后才换到共同基准。
        left, right, _ = self._units('compare', left, right, node)
        if (all(b.constant or b.typed_constant for b in (left, right))
                and left.dtype in INTEGER_BOUNDS and right.dtype in INTEGER_BOUNDS):
            # 两侧纯整数字面量对称选择能容纳正大数的共同定宽。
            target = D.UINT64 if D.UINT64 in (left.dtype, right.dtype) else D.INT64
            anchor = ExprNode('const', target, '1', 'verified', value=0, constant=True)
            left, right = (self._context(b, anchor, node, arithmetic=True) for b in (left, right))
        else:
            # 常量适配不放宽一般整数/浮点信号或不同有符号性的类型约束。
            left = self._context(left, right, node, arithmetic=True)
            right = self._context(right, left, node, arithmetic=True)
        if left.dtype is not right.dtype:
            # 浮点字面量、消息参数或单位换算可要求提升另一侧；精度在活动行检查。
            allow_float = any(b.dtype is D.FLOAT64 and (b.constant or b.typed_constant or b.conversion_promoted
                              or self.message_domain and not b.aliases) for b in (left, right))
            if not allow_float:
                self._error(node, 'where数值分支dtype不兼容')
            left, right = (b if b.dtype is D.FLOAT64 else self._known_node(_node('to_float', D.FLOAT64, b.unit, (b,)))
                           for b in (left, right))
        return self._known_node(_node('where', left.dtype, left.unit, (condition, left, right)))

    def visit(self, node, declared_unit=None):
        """解析已登记的v4单位、选择与数学函数，其余受限语法沿原访问器。

        参数: node为AST节点；declared_unit为根目标标签。
        返回: 已检查类型、单位和依赖的表达式节点。
        异常: ValueError为签名、非字面量单位、非法数值或未知函数。
        """
        # 数学函数在编译期确定所有参数的单位和类型；属性调用仍由原白名单拒绝。
        if (self.extensions is not None and isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                and node.func.id in self.extensions.functions):
            from .extension_points import compile_host_function
            return compile_host_function(self,node,self.extensions.functions[node.func.id])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in MATH_FUNCTIONS:
            return compile_math(self, node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'lookup':
            return compile_lookup(self, node)
        # 原码节点只接受带来源的枚举声明；普通整数函数独立检查类型及位宽。
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'enum_code':
            return compile_enum_code(self, node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in INTEGER_FUNCTIONS:
            return compile_integer(self, node)
        # where是控制求值的专门节点。
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'where':
            return self._where(node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('quantity', 'to_unit'):
            if len(node.args) != 2 or node.keywords:
                self._error(node, f'{node.func.id}需要两个位置参数')
            unit_ast = node.args[1]
            if not isinstance(unit_ast, ast.Constant) or type(unit_ast.value) is not str:
                self._error(unit_ast, '单位必须为字符串字面量')
            target = units.resolve_unit(unit_ast.value)
            if target is None:
                self._error(unit_ast, 'quantity/to_unit需要已登记单位')
            child = self.visit(node.args[0])
            if child.dtype not in (*INTEGER_BOUNDS, D.FLOAT64):
                self._error(node, 'quantity/to_unit只支持数值')
            if node.func.id == 'quantity':
                # 带单位常量不再参与裸常量单位继承；保留原整数字面量精度。
                if child.operator != 'const' or not child.constant:
                    self._error(node, 'quantity的数值必须为有限字面量')
                if child.dtype in INTEGER_BOUNDS and not INTEGER_BOUNDS[child.dtype][0] <= child.value <= INTEGER_BOUNDS[child.dtype][1]:
                    self._error(node, 'quantity字面量超出64位范围')
                label = units.output_label(target, unit_ast.value)
                return replace(child, unit=label, constant=False, unit_explicit=True, typed_constant=True)
            converted = self._convert(child, unit_ast.value, node, explicit=True)
            # 显式选为无量纲的常量不能再被相邻信号解释为电压或电流。
            return replace(converted, constant=False, typed_constant=True) if child.constant else converted
        # 原访问器负责语法安全、逻辑、abs及isclose；新单位状态由同一目录确定。
        result = super().visit(node, declared_unit)
        return self._known_node(result) if result.args else result
