"""把宿主已经明确注册的纯函数调用编译进白名单表达式树。

固定参数及其声明尺度由FunctionSpec提供。此层只检查类型、解释裸常量并
编译必要的单位转换；静态编译从不实例化宿主状态或执行用户的逐点回调。
"""
from dataclasses import replace
from .expression import _node, ExprNode
from .expression_math_v4 import check_integer_leaves
from .numeric import INTEGER_BOUNDS
from .types import SignalDType as D


def compile_host_function(compiler,call,spec):
    """检查固定位置端口，将显式可信实现绑定到当前不可变树。

    参数: 当前v4编译器、调用AST及注册描述符。返回: typed ExprNode。
    异常: ValueError为位置数量、类型、单位或整数字面量非法；不加载配置路径。
    """
    if call.keywords or len(call.args) != len(spec.inputs):
        compiler._error(call,f'{spec.name}需要{len(spec.inputs)}个显式位置参数')
    operands = []
    for raw,port in zip(call.args,spec.inputs):
        value = compiler.visit(raw)
        check_integer_leaves(compiler,(value,),raw)
        if value.dtype not in (*INTEGER_BOUNDS,D.FLOAT64) and value.dtype is not port.dtype:
            compiler._error(raw,'扩展输入dtype与固定端口不符')
        if value.constant and value.dtype is not D.BOOL:
            # 裸常量的物理含义由对应位置唯一确定；quantity不再获得新的单位锚点。
            value = replace(value,unit=port.unit,unit_status='verified')
        value = compiler._convert(value,port.unit,raw)
        value = compiler._context(value,ExprNode('port',port.dtype,port.unit,'verified'),raw,arithmetic=True)
        if value.dtype is not port.dtype:
            compiler._error(raw,'扩展输入dtype与固定端口不符，请先显式转换数值类型')
        operands.append(value)
    # 即使实参全部是常量，也不能把宿主调用当作静态范围参数偷偷执行；
    # 节点dtype与单位由宿主明确声明，不能被外侧裸常量上下文重新解释。
    node = _node('host_function',spec.output.dtype,spec.output.unit,tuple(operands),name=spec.name,host_function=spec)
    return compiler._known_node(replace(node,constant=False,typed_constant=False,conversion_promoted=False))
