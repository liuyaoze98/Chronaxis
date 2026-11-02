"""把表达式文本和信号声明转换成经过检查的表达式树。

例如，已绑定的voltage和current可用于voltage * current；编译器检查
名称、类型、单位和依赖，输出结果类型、单位、实际信号依赖及绑定身份。
表达式使用受限语法（DSL）：仅接受明确允许的语法树节点和注册函数，
不执行Python代码，不访问任意对象，也不读取日志或加载DBC。

compile_expression接收真实SignalBindings、关联实际解码证据的DecodedBindings，
或独立消息仓MessageBindings，输出供解释器使用的CompiledExpression；实际
证据由执行层完整核实后提供。validate_expression接收DeclarationBindings或
MessageDeclarations，只产生不可执行的StaticExpression。
两者均检查完整派生声明与循环依赖；数字常量按运算上下文检查单位和定宽。
整数比较的常量边界保留精确Python整数，不因超过定宽范围而先舍入为浮点数。

标量与数组解释器共享已检查的树，数值计算各自独立。本模块只依赖标准库
及核心声明模型；编译状态每次新建，不修改输入，也没有跨计划的执行缓存。
"""

# AST只用于解析与规范身份，不用动态执行。
import ast
# 冻结节点和纯常量上下文重建，没有全局执行绑定缓存。
from dataclasses import dataclass, replace
# SHA关联实际输入绑定和编译语义版本。
from hashlib import sha256
# 数字字面量必须有限，不允许非有限容差。
from math import isfinite
# 原始派生声明只读保存，不修改调用侧映射。
from types import MappingProxyType

# 使用当前已校验绑定、类型及静态数值协议。
from .binding import SignalBindings, _identity
# 静态配置声明独立于真实输入；只由专用validate入口接收。
from .declarations import DeclarationBindings
# 已解码运行绑定不保存伪造memory行，仍与不可执行声明类型分开。
from .decoded_binding import DecodedBindings
# 当前消息的参数/运行域有独立typed入口，不伪装普通历史或TTL绑定。
from .message_binding import MessageBindings, MessageDeclarations
# 定宽/运算声明可共享，编译不调用被测数组或参考数据运算。
from .numeric import INTEGER_BOUNDS, result_dtype
# 类型与质量模型显式，不用字符串冒充dtype。
from .types import SignalDType
# 已知单位表仅检查当前显式标签，不猜物理工程含义。
from .units import UNIT_TABLE
# 文本与标识符保留安全名称和大小写。
from .validation import require_identifier, require_text

# 运算符映射固定，禁止幂/取模/位运算等未支持语法。
BINOPS = MappingProxyType({ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul', ast.Div: 'div'})
# 首版比较白名单，链式比较另展开为三值and。
CMP = MappingProxyType({ast.Eq: 'eq', ast.NotEq: 'ne', ast.Lt: 'lt', ast.LtE: 'le', ast.Gt: 'gt', ast.GtE: 'ge'})
# 常量在左侧时反向精确整数比较，不能转float。
REVERSE_CMP = MappingProxyType({'eq': 'eq', 'ne': 'ne', 'lt': 'gt', 'le': 'ge', 'gt': 'lt', 'ge': 'le'})


@dataclass(frozen=True)
class DerivedDefinition:
    """声明一个由现有信号计算得到的新名称、表达式和结果单位。

    name与原信号共用名称空间，需在bindings.derived_names中预先登记。
    构造本类只检查文本和名称；表达式编译时才检查单位、依赖和循环引用。
    unit省略时由表达式支持的单位关系推导；显式标签不授权猜测物理量纲，未知单位组合仍保留unverified状态，
    表示关系未验证。实例不可重新赋值，不保存信号值或运行中的状态。
    """

    name: str  # 已在bindings.derived_names登记的简单别名。
    expr: str  # 白名单DSL文本，不是任意Python。
    unit: str | None = None  # 缺省使用表达式已支持的单位关系。

    def __post_init__(self) -> None:
        """验证派生声明结构，不解析或加载来源。

        参数: 无；读取name/expr/unit。
        返回: None，不改用户声明。
        异常: TypeError/ValueError为标识符/空文本问题。
        """
        # 派生与signal名称采用同一规则。
        require_identifier(self.name, 'derived.name')
        # 不允许空表达式占位。
        require_text(self.expr, 'derived.expr')
        # 未知标签可以显式声明，但不能假称单位已验证。
        if self.unit is not None:
            require_text(self.unit, 'derived.unit')


@dataclass(frozen=True)
class ExprNode:
    """保存表达式编译器已检查的一个内部节点。

    operator给出注册操作，args保存不可变子节点，dtype和unit说明结果类型与单位。
    aliases记录展开后的原信号依赖，运行时只按简单别名取值，不访问属性路径。
    constant说明整棵子树只由字面量组成；编译器可据此赋予常量上下文单位和
    整数类型，不能借此改变信号本身的类型。unit_status保留单位是否已验证。
    节点不保存样本值缓存，解释器的计算结果仅在当前一次求值中保存。
    """

    operator: str  # const/name/add等固定执行分派。
    dtype: SignalDType  # 静态目标类型。
    unit: str  # 结果单位标签。
    unit_status: str  # verified或unverified，不能借未知标签过预设。
    args: tuple = ()  # 子节点，isclose含四节点。
    value: int | float | bool | str | None = None  # 纯常量或精确比较边界。
    name: str | None = None  # name仅简单已绑定别名。
    labels: tuple[str, ...] = ()  # enum逻辑域。
    aliases: tuple[str, ...] = ()  # 原信号依赖，不包含派生占位。
    constant: bool = False  # 纯常量静态上下文标志。
    allow_float_literal: bool = False  # 由本编译器证明的浮点字面量路径。


@dataclass(frozen=True)
class CompiledExpression:
    """保存可供求值器使用的表达式树及其真实输入绑定。

    root已检查语法、类型与单位；dependencies只包含展开后的原信号别名。
    identity关联绑定、派生定义、规范语法树和编译版本。改变会话、字段映射、
    有效期或转换声明都会影响身份，解释器要求调用时bindings与编译时一致。
    实例不可重新赋值，没有全局执行缓存；创建本对象并不执行数值计算。
    """

    text: str  # 原表达式仅供定位，不动态执行。
    bindings: SignalBindings | DecodedBindings | MessageBindings  # 各自真实输入域的运行身份。
    root: ExprNode  # 实际白名单typed树。
    dependencies: tuple[str, ...]  # 实际需要的已解码信号列。
    normalized_ast: str  # 不含位置的AST规范结构。
    identity: str  # 完整执行身份SHA。


@dataclass(frozen=True)
class StaticExpression:
    """保存只经声明校验的DSL树，不能交给数值解释器执行。

    identity证明配置/语法/转换声明，尚未证明输入内容、字段和观测。
    与CompiledExpression类型分开，运行时必须核实来源后重新绑定。
    """

    text: str  # 原DSL，仅用于定位。
    bindings: DeclarationBindings | MessageDeclarations  # 声明身份，没有实际读入证明。
    root: ExprNode  # 白名单类型/单位已经校验。
    dependencies: tuple[str, ...]  # 展开后的原信号依赖。
    normalized_ast: str  # 规范语法，仅供静态身份。
    identity: str  # 独立静态版本前缀的SHA。


def _node(operator, dtype, unit, args=(), **kwargs) -> ExprNode:
    """从已验证子节点汇总局部依赖及单位状态。

    参数: operator/dtype/unit及args；kwargs为已验证内部字段。
    返回: 冻结ExprNode；不进行样本计算。
    异常: 内部参数冲突传播，配置由编译器先验证。
    """
    # 当前表达式所有真实依赖，不继承全局绑定。
    aliases = tuple(sorted({name for arg in args for name in arg.aliases}))
    # 任何未知关系都保留unverified，不能仅看输出单位是已知标签。
    status = 'verified' if unit in UNIT_TABLE and all(arg.unit_status == 'verified' for arg in args) else 'unverified'
    # 所有参数均由编译器产生，执行器不接用户自由operator。
    return ExprNode(operator, dtype, unit, status, args, aliases=aliases, constant=all(arg.constant for arg in args), **kwargs)


class _Compiler:
    """在一次编译中检查名称、语法、单位与派生依赖。

    signals和derived来自当前绑定，不读取数据来源。消息域另有显式参数表，
    参数按const执行但保constant=False，不随对方改变单位。nodes仅在本实例
    内复用已编译的派生树；visiting记录当前递归路径，用于指出循环依赖。
    根表达式的declared_unit可给未知组合提供显式标签，但不证明该量纲正确。
    状态不跨编译调用共享，不缓存信号值，也不扩大受限表达式语法。
    """

    def __init__(self, bindings, derived):
        """建立当前声明表并校验完整派生输入。

        参数: bindings为明确typed普通/消息运行绑定或各自静态声明；
            derived为tuple DerivedDefinition，数值执行仍由公开入口的类型门槛控制。
        返回: None，仅局部解析状态。
        异常: TypeError/ValueError为类型/缺项/重复/名称空间不一致。
        """
        # 不接无类型计划或可变派生列表。
        if not isinstance(bindings, (SignalBindings, DecodedBindings, DeclarationBindings, MessageBindings, MessageDeclarations)) or not isinstance(derived, tuple) or any(not isinstance(item, DerivedDefinition) for item in derived):
            # 结构错误先于解析/执行。
            raise TypeError('解析需要typed真实/声明绑定及tuple DerivedDefinition')
        # bindings已校验signals唯一/安全别名。
        self.bindings = bindings
        # 当前真实信号声明，不读取原日志。
        self.signals = {item.name: item for item in bindings.signals}
        # 只有消息域具有显式配置参数；原普通表达式不增加名称或混合dtype权限。
        self.message_domain = isinstance(bindings, (MessageBindings, MessageDeclarations))
        self.parameters = {item.name: item for item in bindings.parameters} if self.message_domain else {}
        # 重复派生声明不能靠字典覆盖隐藏。
        if len({item.name for item in derived}) != len(derived) or set(item.name for item in derived) != set(bindings.derived_names):
            # 登记名称不等于表达式已经接线。
            raise ValueError('derived声明与bindings名称不一致或重复')
        # 显式派生表自有副本，只读保存。
        self.derived = MappingProxyType({item.name: item for item in derived})
        # 本次缓存没有上次任务的节点/值。
        self.nodes = {}
        # 栈只用于完整依赖环诊断。
        self.visiting = []

    def _error(self, node, message):
        """给出语法位置、拒绝原因与可用别名。

        参数: node为AST节点，message为具体失败原因。
        返回: 不返回，抛ValueError。
        异常: ValueError定位行/列，不自动点号改名。
        """
        # AST位置从0列转用户可读1列；别名只来自当前计划。
        raise ValueError(f'行{getattr(node, "lineno", 1)}列{getattr(node, "col_offset", 0)+1}：{message}；可用别名：{", ".join((*self.signals, *self.derived, *self.parameters))}')

    def parse(self, text, unit=None):
        """解析一个表达式并验证根结果单位/枚举域。

        参数: text为非空DSL；unit为可选显式结果单位。
        返回: typed ExprNode和规范AST。
        异常: ValueError为语法/白名单/类型/单位/环；不吞I/O异常。
        """
        # 文本不可空，也不接受任意对象str隐式转换。
        require_text(text, 'expression')
        # 显式单位保留原标签。
        if unit is not None:
            # unknown可以声明，但状态仍unverified。
            require_text(unit, 'expression.unit')
        # Python仅解析eval模式，赋值/多条语句自然失败。
        try:
            # 不执行解析所得对象。
            tree = ast.parse(text, mode='eval')
        except SyntaxError as error:
            # 用户语法错是执行前配置错误。
            raise ValueError(f'表达式语法错误：行{error.lineno}列{error.offset} {error.msg}') from error
        # 根声明单位只用于当前层，嵌套未知组合需独立派生声明。
        root = self.visit(tree.body, declared_unit=unit)
        # 原始字符串literal不能作为任意字符串表达式执行。
        if root.dtype is SignalDType.ENUM and not root.labels:
            # 字符串只有显式枚举比较才能获得合法域。
            self._error(tree.body, '字符串仅允许声明枚举域内的eq/ne')
        # 纯整数根也必须属于64位类型，不定义额外无界输出。
        if root.operator == 'const' and root.dtype in INTEGER_BOUNDS and not INTEGER_BOUNDS[root.dtype][0] <= root.value <= INTEGER_BOUNDS[root.dtype][1]:
            # 超大比较边界已通过特殊节点实现，正常输出不放行。
            self._error(tree.body, '整数字面量超出结果dtype')
        # 有单位结果不能靠unit字段自动做隐式转换。
        if unit is not None and root.unit != unit:
            # mA→A需要绑定显式转换，而非只改输出标签。
            self._error(tree.body, f'结果单位{root.unit}与声明{unit}不一致，须显式转换')
        # AST仅作为身份结构，不作为运行时eval输入。
        return root, ast.dump(tree, annotate_fields=True, include_attributes=False)

    def _name(self, node):
        """解析真实别名、消息参数或本计划派生，并拒绝环/未知名称。

        参数: node为Name AST。
        返回: 已绑定name节点或已编译派生树。
        异常: ValueError为未知别名/环/派生表达式错误。
        """
        # 普通分析只按当前显式别名查找，不读取semantic属性。
        if node.id in self.signals:
            # 原始定义含dtype/unit及固定enum域。
            definition = self.signals[node.id]
            # 多码同标签保留首次域顺序。
            labels = tuple(dict.fromkeys(value for _, value in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
            # 未知标签/关系仍unverified，name不是常量。
            return ExprNode('name', definition.dtype, definition.unit, definition.unit_status, name=node.id, labels=labels, aliases=(node.id,))
        # 有单位参数按const执行，但不是裸literal；不可继承对方单位，也不是原信号依赖。
        if node.id in self.parameters:
            parameter = self.parameters[node.id]
            return ExprNode('const', parameter.dtype, parameter.unit, parameter.unit_status,
                            value=parameter.value, name=node.id, constant=False)
        # 派生节点只在当前输入声明下复用。
        if node.id in self.nodes:
            # 不使用其他计划同名缓存。
            return self.nodes[node.id]
        # 访问栈包含同名证明环，须执行前拒绝。
        if node.id in self.visiting:
            # 保留完整依赖路径便于配置修正。
            self._error(node, '派生循环依赖：'+' -> '.join((*self.visiting, node.id)))
        # 未知名字不能推测原字段或语义名称。
        if node.id not in self.derived:
            # 错误提供当前可用名称。
            self._error(node, f'未知别名{node.id}')
        # 开始解析当前派生节点的依赖。
        self.visiting.append(node.id)
        # 派生表达式和明确单位必须真正接线。
        definition = self.derived[node.id]
        # 根单位校验由parse统一实施。
        result, _ = self.parse(definition.expr, definition.unit)
        # 成功后移除递归栈当前节点。
        self.visiting.pop()
        # 本次节点缓存仅存静态树，无信号值。
        self.nodes[node.id] = result
        # 派生实际依赖展开到已解码信号。
        return result

    def _context(self, literal, other, node, *, arithmetic):
        """把纯数字/enum常量按另一侧明确类型及单位校验。

        参数: literal为纯常量子树；other为typed对方；node定位；arithmetic
            表示算术字面量必须能在目标整数类型表示。
        返回: 合法常量子树；含浮点常量的整型运算保持float路径。
        异常: ValueError为字面量类型/定宽/枚举域冲突。
        """
        # 仅纯常量获得上下文，不能把信号强行改dtype/unit。
        if not literal.constant:
            # 输入依赖不允许隐藏转换。
            return literal
        # 枚举字符串常量严格匹配当前逻辑域。
        if literal.dtype is SignalDType.ENUM:
            # 仅裸字符串可进入指定枚举域。
            if other.dtype is not SignalDType.ENUM or literal.operator != 'const' or literal.value not in other.labels:
                # 未声明标签不自动取第一项。
                self._error(node, '枚举字面量不在声明域')
            # 字符串不作一般单位转换，只保留同域比较。
            return replace(literal, labels=other.labels, unit=other.unit, unit_status=other.unit_status)
        # 数字常量与bool不能混用，bool不是隐式0/1。
        if literal.dtype is SignalDType.BOOL or other.dtype in (SignalDType.BOOL, SignalDType.ENUM):
            # bool同型eq/ne/logic仍由静态协议允许。
            return literal
        # 整数算术字面量按对方整数dtype，递归纯常量子树同样校验。
        if other.dtype in INTEGER_BOUNDS and literal.dtype in INTEGER_BOUNDS and arithmetic:
            # 对const递归重建，以免uint64+常量子树隐藏signed promotion。
            if literal.operator == 'const':
                # 目标整数字面量必须可表示，而非算术runtime缺失。
                if not INTEGER_BOUNDS[other.dtype][0] <= literal.value <= INTEGER_BOUNDS[other.dtype][1]:
                    # 包含uint信号加负整数字面量的配置拒绝。
                    self._error(node, '整数字面量无法在算术dtype中表示')
                # 原整数值保持精确，不先变float。
                return replace(literal, dtype=other.dtype)
            # 纯整数子树只含定宽算术/abs/neg，逐节点重建静态目标dtype。
            args = tuple(self._context(arg, other, node, arithmetic=True) for arg in literal.args)
            # 除法已经静态为float，不会进入此分支。
            return replace(literal, dtype=other.dtype, args=args)
        # float信号与整数常量先显式转换常量，不放开任意混合信号promotion。
        if other.dtype is SignalDType.FLOAT64 and literal.dtype in INTEGER_BOUNDS:
            # 原整数constant域仍需64位，超宽只允许整数精确比较专用节点。
            if literal.operator == 'const' and not INTEGER_BOUNDS[literal.dtype][0] <= literal.value <= INTEGER_BOUNDS[literal.dtype][1]:
                # 字面量越界是执行前错误。
                self._error(node, '数值字面量超出64位原类型')
            # to_float由两个独立数值后端在runtime检查精确表示。
            return _node('to_float', SignalDType.FLOAT64, literal.unit, (literal,))
        # 显式float字面量对整数保持float，后续有精度mask。
        return literal

    def _units(self, operator, left, right, node, declared_unit=None):
        """按首版表推断单位，裸常量加减/比较采用对方单位。

        参数: operator及两typed子树；node定位；declared_unit为根显式未知组合标签。
        返回: 上下文单位子树及输出单位。
        异常: ValueError为未转换单位或未支持组合。
        """
        # 加减/比较包括isclose使用相同裸数字常量规则。
        if operator in ('add', 'sub', 'compare'):
            # 一边纯数值常量可以继承另一侧单位；纯常量对纯常量仍1。
            if left.constant and not right.constant and left.dtype not in (SignalDType.BOOL, SignalDType.ENUM):
                # 改静态单位不执行数值缩放。
                left = replace(left, unit=right.unit, unit_status=right.unit_status)
            # 另一侧常量同理，不能改有依赖的信号单位。
            if right.constant and not left.constant and right.dtype not in (SignalDType.BOOL, SignalDType.ENUM):
                # 当前裸常量采用对方原单位。
                right = replace(right, unit=left.unit, unit_status=left.unit_status)
            # 已知不同标签也必须额外显式转换，不根据同量纲猜倍率。
            if left.unit != right.unit:
                # 未知不同标签同样不能假设等价。
                self._error(node, f'单位{left.unit}/{right.unit}不一致，须显式转换')
            # 比较结果unit1，算术保留操作数单位。
            return left, right, '1' if operator == 'compare' else left.unit
        # 无量纲乘除不会引入新工程量纲。
        if operator == 'mul' and '1' in (left.unit, right.unit):
            # 两边都1也得到1。
            return left, right, right.unit if left.unit == '1' else left.unit
        # 相同单位相除得到1，除无量纲保留分子单位。
        if operator == 'div' and (left.unit == right.unit or right.unit == '1'):
            # 无额外值换算。
            return left, right, '1' if left.unit == right.unit else left.unit
        # 固定支持乘法组合，避免完整量纲猜测。
        products = {frozenset(('V', 'A')): 'W', frozenset(('W', 's')): 'J', frozenset(('A', 's')): 'A·s'}
        # 仅当前已确认单位关系可以verified输出。
        if operator == 'mul' and frozenset((left.unit, right.unit)) in products:
            # 已知单位的显式规范化必须先于这里。
            return left, right, products[frozenset((left.unit, right.unit))]
        # 普通分析可显式声明未知组合，但不得假称已知量纲验证。
        if declared_unit is not None and (left.unit not in UNIT_TABLE or right.unit not in UNIT_TABLE):
            # 任意结果标签仍unverified，即使用户标成W。
            return replace(left, unit_status='unverified'), right, declared_unit
        # 已知未支持组合不能用标签覆盖当证明。
        self._error(node, f'未支持单位组合{left.unit} {operator} {right.unit}，需显式规范化/派生声明')

    def _binary(self, operator, left, right, node, declared_unit=None):
        """静态编译数值/比较，整数常量比较保留精确边界。

        参数: operator及已编译左右节点，node定位，declared_unit根声明。
        返回: typed ExprNode；绝不运行用户代码。
        异常: ValueError为单位/类型/常量配置错误。
        """
        # 先校验单位，比较也不能隐藏mA与A混用。
        left, right, unit = self._units('compare' if operator in CMP.values() else operator, left, right, node, declared_unit)
        # 纯整数常量没有signal dtype上下文，先对称选共同定宽。
        if operator not in CMP.values() and left.constant and right.constant and left.dtype in INTEGER_BOUNDS and right.dtype in INTEGER_BOUNDS:
            # 有超signed正整数literal时选uint64；所有operand仍须可表示。
            dtype = SignalDType.UINT64 if SignalDType.UINT64 in (left.dtype, right.dtype) else SignalDType.INT64
            # 只是编译器类型上下文，不产生运行时信号或新binding。
            target = ExprNode('const', dtype, '1', 'verified', value=0, constant=True)
            # 两側独立同一目标，不以遍历顺序决定政策。
            left, right = self._context(left, target, node, arithmetic=True), self._context(right, target, node, arithmetic=True)
        # 整数信号与任意精确整数字面量比较无需把边界塞入定宽结果。
        if operator in CMP.values() and left.dtype in INTEGER_BOUNDS and right.dtype in INTEGER_BOUNDS:
            # 常量在左，统一反向比较当前正常信号值。
            if left.operator == 'const' and right.operator != 'const':
                # 特殊节点value保留完整Python整数边界。
                return _node('int_literal_'+REVERSE_CMP[operator], SignalDType.BOOL, unit, (right,), value=left.value)
            # 常量在右直接按原运算方向比较。
            if right.operator == 'const' and left.operator != 'const':
                # 超uint64边界只是精确比较阈值，不是新数值输出dtype。
                return _node('int_literal_'+operator, SignalDType.BOOL, unit, (left,), value=right.value)
        # 常量与实际另一侧的类型上下文明确处理。
        left = self._context(left, right, node, arithmetic=operator not in CMP.values())
        # 使用已经校验左側dtype，再处理右側常量。
        right = self._context(right, left, node, arithmetic=operator not in CMP.values())
        # 先保持原普通规则：只有float纯常量证明允许混合，不能放行任意信号。
        float_literal = left.dtype is not right.dtype and ((left.constant and left.dtype is SignalDType.FLOAT64) or (right.constant and right.dtype is SignalDType.FLOAT64))
        # 消息域的无信号依赖配置子树是显式FLOAT64值；仍由现数值核检查整数精度。
        if self.message_domain and left.dtype is not right.dtype:
            float_literal |= ((left.dtype is SignalDType.FLOAT64 and not left.aliases)
                              or (right.dtype is SignalDType.FLOAT64 and not right.aliases))
        # bool/enum及不同信号dtype在静态协议中拒绝。
        try:
            # 仅共享静态规则，没有共享数值执行。
            dtype = result_dtype(operator, left.dtype, right.dtype, float_literal)
        except (TypeError, ValueError) as error:
            # 补充用户位置而非runtime UNKNOWN。
            self._error(node, str(error))
        # enum比较必须同域，不能直接比较同编码不同标签。
        if left.dtype is SignalDType.ENUM and left.labels != right.labels:
            # 当前首版没有枚举跨域自动归一化。
            self._error(node, '枚举比较需要相同声明域')
        # 正常算术const叶仍必须在其静态类型内，即使两側都是常量。
        for operand in (left, right):
            # 巨大整数仅在前述特殊比较节点允许。
            if operand.operator == 'const' and operand.dtype in INTEGER_BOUNDS and not INTEGER_BOUNDS[operand.dtype][0] <= operand.value <= INTEGER_BOUNDS[operand.dtype][1]:
                # 不能在runtime模型构造时才失败。
                self._error(node, '整数字面量超出运算dtype')
        # 真实依赖/constant状态由统一节点模型汇总。
        return _node(operator, dtype, unit, (left, right), allow_float_literal=float_literal)

    def visit(self, node, declared_unit=None):
        """逐AST节点执行首版白名单，不递归放行未知语法。

        参数: node为解析节点；declared_unit仅根静态单位上下文。
        返回: 完整typed内部节点。
        异常: ValueError定位未注册语法/函数/类型/单位。
        """
        # 纯literal仅数字、bool和待枚举上下文的str。
        if isinstance(node, ast.Constant):
            # bool必须先于int分类，因为Python bool是int子类。
            value = node.value
            # 不接受None、bytes、complex或任意对象。
            if type(value) not in (bool, int, float, str) or type(value) is float and not isfinite(value):
                # 非有限literal同样是配置错误。
                self._error(node, '仅支持有限数字/bool及枚举字符串literal')
            # 字符串暂存为ENUM，只有后续明确域比较才合法。
            dtype = SignalDType.BOOL if type(value) is bool else SignalDType.ENUM if type(value) is str else SignalDType.FLOAT64 if type(value) is float else SignalDType.INT64 if value <= 2 ** 63 - 1 else SignalDType.UINT64
            # 纯literal无单位、无来源依赖。
            return ExprNode('const', dtype, '1', 'verified', value=value, constant=True)
        # Name只访问已注册别名，绝不反射对象。
        if isinstance(node, ast.Name):
            # 未注册名称也在此精确定位。
            return self._name(node)
        # 一元±常量保留完整精确整数，供算术/比较上下文校验。
        if isinstance(node, ast.UnaryOp):
            # 常量负号不先包装成uint64再运行下溢。
            if isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant) and type(node.operand.value) in (int, float):
                # Python只计算编译器已识别的原生纯literal符号。
                value = -node.operand.value if isinstance(node.op, ast.USub) else node.operand.value
                # 返回仍须经过Constant合法性检查。
                return self.visit(ast.copy_location(ast.Constant(value=value), node))
            # 一元操作数先完成静态校验。
            child = self.visit(node.operand)
            # not仅bool，不使用Python truthiness。
            if isinstance(node.op, ast.Not) and child.dtype is SignalDType.BOOL:
                # 运行时not UNKNOWN仍UNKNOWN。
                return _node('not', SignalDType.BOOL, '1', (child,))
            # 数值一元±不允许bool/enum。
            if isinstance(node.op, (ast.USub, ast.UAdd)) and child.dtype in (*INTEGER_BOUNDS, SignalDType.FLOAT64):
                # unary+保留原typed树，neg由独立数值核处理。
                return child if isinstance(node.op, ast.UAdd) else _node('neg', child.dtype, child.unit, (child,))
            # 位取反等未支持形式拒绝。
            self._error(node, '未支持一元语法或类型')
        # 数值运算仅固定四种。
        if isinstance(node, ast.BinOp) and type(node.op) in BINOPS:
            # 不使用任意Python运算方法。
            return self._binary(BINOPS[type(node.op)], self.visit(node.left), self.visit(node.right), node, declared_unit)
        # 链式比较逐对生成比较节点，再用保留UNKNOWN（未知）的三值and组合。
        if isinstance(node, ast.Compare):
            # 比较类型逐项注册，is/in等均拒绝。
            if any(type(operator) not in CMP for operator in node.ops):
                # 不能让Python对象身份或容器访问进入DSL。
                self._error(node, '未支持比较运算')
            # 中间操作数静态树只编译一次，不执行求值副作用。
            operands = tuple(self.visit(item) for item in (node.left, *node.comparators))
            # 单个比较的类型/单位都先校验。
            comparisons = tuple(self._binary(CMP[type(operator)], operands[index], operands[index+1], node) for index, operator in enumerate(node.ops))
            # chain输出同一BOOL，不依赖对数组作bool。
            return comparisons[0] if len(comparisons) == 1 else _node('and', SignalDType.BOOL, '1', comparisons)
        # 逻辑and/or仅bool，不能把数值当TRUE。
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            # 逐子树类型/名称/单位均静态检查，未知值留runtime。
            args = tuple(self.visit(item) for item in node.values)
            # 已知False能决定and但不能绕过静态配置错误。
            if any(arg.dtype is not SignalDType.BOOL for arg in args):
                # 不采用Python返回任意操作数的逻辑语义。
                self._error(node, 'and/or仅支持bool表达式')
            # TRUE、FALSE和UNKNOWN三种结果的组合规则，由两个解释器各自实现。
            return _node('and' if isinstance(node.op, ast.And) else 'or', SignalDType.BOOL, '1', args)
        # 函数调用必须裸Name且固定注册。
        if isinstance(node, ast.Call):
            # 属性调用、未注册signal/任意函数禁止。
            if not isinstance(node.func, ast.Name) or node.func.id not in ('abs', 'isclose'):
                # 不访问用户函数对象，也不隐藏注册自由插件。
                self._error(node, '函数仅允许注册abs/isclose，属性访问及任意调用禁止')
            # abs固定一个位置参数，无任意keywords/*args。
            if node.func.id == 'abs':
                # unpack等AST形式不会满足固定签名。
                if len(node.args) != 1 or node.keywords:
                    # 不使用库默认自由签名。
                    self._error(node, 'abs必须为abs(x)')
                # 正常数值类型才能abs。
                child = self.visit(node.args[0])
                # bool/enum不可隐式数字化。
                if child.dtype not in (*INTEGER_BOUNDS, SignalDType.FLOAT64):
                    # 字符串abs拒绝在执行前。
                    self._error(node, 'abs只支持数值')
                # signed最小值的runtime质量由数值核处理。
                return _node('abs', child.dtype, child.unit, (child,))
            # isclose固定两位置参数及完整两个具名容差。
            if len(node.args) != 2 or len(node.keywords) != 2 or {item.arg for item in node.keywords} != {'atol', 'rtol'}:
                # 不能默默采用NumPy默认容差。
                self._error(node, 'isclose必须显式atol、rtol及两个位置参数')
            # 输入只限数值，不让bool/enum通过float转换。
            a, b = (self.visit(item) for item in node.args)
            # isclose不能通过bool等值合法这一事实绕过数值类型要求。
            if any(item.dtype not in (*INTEGER_BOUNDS, SignalDType.FLOAT64) for item in (a, b)):
                # 逻辑/枚举不是该函数的数值实参。
                self._error(node, 'isclose只支持数值实参')
            # isclose需要真正数值常量，不能使用超宽整数比较边界。
            for item in (a, b):
                # 信号正常值已经由typed模型保证定宽。
                if item.operator == 'const' and item.dtype in INTEGER_BOUNDS and not INTEGER_BOUNDS[item.dtype][0] <= item.value <= INTEGER_BOUNDS[item.dtype][1]:
                    # 不能把超宽配置literal拖到runtime失败。
                    self._error(node, 'isclose实参字面量超出64位类型')
            # 裸常量首先完成比较单位上下文。
            a, b, _ = self._units('compare', a, b, node)
            # 混合真实int/float信号须先显式归一化，即使isclose也不隐藏放行。
            self._binary('eq', a, b, node)
            # 容差仍须裸literal；参数虽operator=const但constant=False，不能被偷偷重标单位。
            tolerances = {}
            # 固定两个keywords，AST表达式不动态执行。
            for keyword in node.keywords:
                # 一元±数字literal通过同一静态解析。
                tolerance = self.visit(keyword.value)
                # 大整数只能原64位literal，转换精度仍runtime核查。
                if tolerance.operator != 'const' or not tolerance.constant or tolerance.dtype not in (*INTEGER_BOUNDS, SignalDType.FLOAT64) or tolerance.value < 0 or tolerance.dtype in INTEGER_BOUNDS and not INTEGER_BOUNDS[tolerance.dtype][0] <= tolerance.value <= INTEGER_BOUNDS[tolerance.dtype][1]:
                    # 表达式/不完整容差直接配置失败。
                    self._error(keyword.value, 'isclose容差须有限非负数字字面量')
                # atol采用比较单位，rtol无量纲。
                tolerances[keyword.arg] = replace(tolerance, unit=a.unit if keyword.arg == 'atol' else '1')
            # 数值输入a/b和参数都通过独立float精度核计算判据。
            return _node('isclose', SignalDType.BOOL, '1', (a, b, tolerances['atol'], tolerances['rtol']))
        # 点号语法提供位置/原因/别名，而非静默替换下划线。
        if isinstance(node, ast.Attribute):
            # 禁止所有对象访问，不把semantic字符串当属性路径。
            self._error(node, '禁止ast.Attribute/点号属性访问，请使用已绑定简单别名')
        # pow/subscript/comprehension/lambda/starred等统一本白名单拒绝。
        self._error(node, f'禁止语法{type(node).__name__}')


def compile_expression(text: str, bindings: SignalBindings | DecodedBindings | MessageBindings, *, derived: tuple[DerivedDefinition, ...] = (), unit: str | None = None) -> CompiledExpression:
    """检查表达式及全部派生声明，关联当前真实输入绑定。

    参数:
        text: 非空文本；bindings为真实SignalBindings、DecodedBindings或MessageBindings。
        derived: 完整且不可变的DerivedDefinition元组，需与已登记名称一致。
        unit: 可选的显式结果单位；不执行自动单位换算。
    返回:
        CompiledExpression，保存表达式树、实际依赖别名和完整绑定身份。
    异常:
        TypeError、ValueError: 输入结构、语法、名称、类型、单位、循环依赖
        或多来源同步依据不满足要求。
    流程:
        每次新建编译状态，先检查所有派生声明，再编译根表达式与同步依赖。
        此时不计算数值，也不读取日志或加载DBC；数值精度失败由求值器报告。
    """
    # 只放行明确可执行绑定；普通或消息声明均不能替代各自实际输入证据。
    if not isinstance(bindings, (SignalBindings, DecodedBindings, MessageBindings)):
        # 静态声明必须走validate_expression，不能生成可执行树。
        raise TypeError('可执行编译需要真实SignalBindings、DecodedBindings或MessageBindings')
    # 每次使用全新编译状态，隔离绑定和派生节点。
    compiler = _Compiler(bindings, derived)
    # 即使派生未被当前根使用也检查配置循环/未知名称。
    for definition in derived:
        # Name只作为内部解析入口，位置未提供时错误默认行1列1。
        compiler._name(ast.Name(id=definition.name, ctx=ast.Load()))
    # 根和声明单位完成所有静态语义检查。
    root, normalized = compiler.parse(text, unit)
    # 多源只有当前根实际共同依赖才需要同步依据。
    bindings.require_synchronized(root.aliases)
    # 身份包含来源、显式转换、值有效期、质量政策、全部派生定义和编译版本。
    payload = ('expression-v1', 'reference+numpy-v1', bindings.identity, normalized, repr(root), tuple((item.name, item.expr, item.unit) for item in derived))
    # 不仅以语法文本/semantic声明作为执行缓存证明。
    identity = sha256(_identity(payload).encode('utf-8')).hexdigest()
    # 返回编译后的表达式及其依赖。
    return CompiledExpression(text, bindings, root, root.aliases, normalized, identity)


def validate_expression(text: str, bindings: DeclarationBindings | MessageDeclarations, *, derived: tuple[DerivedDefinition, ...] = (), unit: str | None = None) -> StaticExpression:
    """只根据来源声明检查表达式，不读取真实输入。

    参数:
        text: 非空表达式文本；bindings为DeclarationBindings或MessageDeclarations。
        derived: 完整DerivedDefinition元组；unit为可选显式结果单位。
    返回:
        StaticExpression，说明名称、语法、类型、单位和同步声明已检查。
        该类型不能交给数值解释器执行，也不证明实际字段或数据内容已核实。
    异常:
        TypeError、ValueError: 声明结构、语法、名称、单位、循环依赖或同步缺项。
    边界:
        未被根引用的派生表达式也要检查；读取真实输入后需要重新建立运行绑定。
    """
    # 接口明确拒绝把真实绑定混为纯静态声明。
    if not isinstance(bindings, (DeclarationBindings, MessageDeclarations)):
        # 避免调用侧误把声明身份当执行缓存身份。
        raise TypeError('静态校验需要DeclarationBindings或MessageDeclarations')
    # 白名单及类型政策共用编译器，不复制另一套宽松DSL。
    compiler = _Compiler(bindings, derived)
    # 未被根引用的派生也要检查环和单位。
    for definition in derived:
        # 只用受限内部Name入口，无动态属性访问。
        compiler._name(ast.Name(id=definition.name, ctx=ast.Load()))
    # 根解析保留错误行列与可用别名。
    root, normalized = compiler.parse(text, unit)
    # 声明联合依赖必须已有明确同步条件。
    bindings.require_synchronized(root.aliases)
    # 独立版本前缀确保不能与真实可执行身份混用。
    payload = ('static-expression-v1', bindings.identity, normalized, repr(root), tuple((item.name, item.expr, item.unit) for item in derived))
    # SHA只包含受控typed树，不读取文件内容或旧DBC。
    identity = sha256(_identity(payload).encode('utf-8')).hexdigest()
    # 返回类型与CompiledExpression分开，解释器结构门槛仍然有效。
    return StaticExpression(text, bindings, root, root.aliases, normalized, identity)
