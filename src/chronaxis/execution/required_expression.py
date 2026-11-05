"""在真实部分投影上编译结果需要的表达式，保留完整静态声明检查。

输入是原 StaticExpression、真实 DecodedBindings 和全部派生定义；输出身份
与公开 compile_expression 一致的 CompiledExpression。先在声明绑定上重新
检查所有派生，再核对原静态对象；真实绑定只解析当前根递归需要的派生，不把
未用派生变成要求输入投影的运行根。公共编译和静态校验入口保持原行为。
本模块不读取数据、不求值、不持有长期缓存。调用阶段须先为完整声明树、编译
临时对象及身份材料预付费用；失败时清理本层借用引用，原异常交给阶段处理。
"""

from ..core.decoded_binding import DecodedBindings
from ..core.expression import (
    CompiledExpression, StaticExpression, _create_compiler, expression_identity, validate_expression)


def compile_required_expression(static, bindings, *, derived=(), unit=None):
    """完整核实静态声明，再按本结果根建立真实输入表达式。

    参数:
        static: 原 StaticExpression；bindings: 当前实际 DecodedBindings。
        derived: 与绑定名称空间一致的完整 DerivedDefinition tuple。
        unit: 原表达式的显式单位，省略时使用原编译器推导，不做输出换算。
    返回:
        CompiledExpression。身份公式、依赖、类型和单位沿用公开编译规则。
    异常:
        TypeError 为对象域不符；ValueError 为静态内容被替换、未知名称、
        循环、类型/单位或实际依赖未投影；取消和内存错误原样传播。
    边界:
        未使用派生仍接受语法和单位检查，但不要求其原字段已读取。当前根需要
        的字段必须有真实投影证明。预算由调用阶段在本函数执行前承担。
    """
    checked = compiler = root = normalized = payload = identity = None
    try:
        if type(static) is not StaticExpression or not isinstance(bindings, DecodedBindings):
            raise TypeError('按需运行编译需要StaticExpression和实际DecodedBindings')
        checked = validate_expression(static.text, bindings.declarations, derived=derived, unit=unit)
        # 同时核根树和身份；仅比较别名或单位不能发现合法文本/常量被typed替换。
        if checked != static:
            raise ValueError('按需运行编译与原完整静态表达式不一致')
        compiler = _create_compiler(bindings, derived)
        root, normalized = compiler.parse(static.text, unit)
        bindings.require_synchronized(root.aliases)
        identity = expression_identity(bindings, root, normalized, derived)
        return CompiledExpression(static.text, bindings, root, root.aliases, normalized, identity)
    finally:
        # 阶段退款后，异常栈不得额外保活本层编译器及其全部声明索引。
        checked = compiler = root = normalized = payload = identity = None
        static = bindings = derived = unit = None
