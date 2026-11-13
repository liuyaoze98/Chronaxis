"""估算现役来源/表达式元数据和未完成批协议状态，不保存或回放历史。

保留现有内部导入路径；费用公式与异常边界不因旧历史仓退出而改变。
"""
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from sys import getsizeof
from ..extensions import ExtensionRegistry, FunctionSpec, ReductionSpec, TransformSpec
from ..core.binding import SignalDefinition
from ..core.expression import ExprNode
from ..results.errors import ResultFormatError
from ..sources.protocol import BatchValidator

def _metadata_bytes(value, depth: int = 0) -> int:
    """估算已校验来源/请求的冻结元数据，不改变结果层封闭类型注册。

    参数: value为typed描述树，depth为普通容器的递归深度。返回: 基础bytes。
    异常: ResultFormatError为普通元数据超过32层、存在环或未支持结构。
    已编译表达式的子节点用显式栈遍历，不把每层args元组算作额外数据协议层级。
    费用仍按每个引用位置累计，缓存只避免重新遍历相同子树，不减少预算费用。
    """
    return _metadata_cost(value, depth, set(), {})


def _metadata_cost(value, depth, active, expression_costs):
    """按原费用公式估算一个元数据位置，并检测当前容器路径上的环。

    参数: value为元数据、depth为普通嵌套层级、active为当前路径身份集合，
        expression_costs为本次调用的表达式子树费用缓存。
    返回: 此引用位置的完整费用。异常: 深度、环或未知结构的ResultFormatError。
    副作用: 临时登记当前路径；返回或异常时移除，不修改调用方元数据。
    """
    # 仅计数，不执行序列化或调用任意对象方法；所有描述先经typed模型检查。
    if depth > 32:
        raise ResultFormatError('历史元数据超过32层')
    # 已注册的宿主实现由调用方持有，本次计划仅借不可变描述/身份。不遍历或
    # 序列化任意Python回调；实际被请求的状态和工作区在其生命周期单独预约。
    if type(value) in (ExtensionRegistry,FunctionSpec,ReductionSpec,TransformSpec):
        return 256
    if type(value) is ExprNode:
        return _expression_metadata_cost(value, depth, active, expression_costs)
    container = is_dataclass(value) and not isinstance(value, type) or isinstance(value, Mapping) or type(value) is tuple
    if container:
        identity = id(value)
        if identity in active:
            raise ResultFormatError('历史元数据存在循环引用')
        active.add(identity)
        try:
            if type(value) is SignalDefinition:
                # 四个默认字段仍只收引用槽；实际非默认声明继续按完整字段计费。
                shared_defaults={'input_dtype','code_dtype','capture_code','config_version'}
                return getsizeof(value)+sum(16 if f.name in shared_defaults and getattr(value,f.name) is f.default
                    else 256+_metadata_cost(getattr(value,f.name),depth+1,active,expression_costs) for f in fields(value))
            if is_dataclass(value) and not isinstance(value, type):
                return getsizeof(value) + sum(256 + _metadata_cost(getattr(value, field.name), depth + 1,
                    active, expression_costs) for field in fields(value))
            if isinstance(value, Mapping):
                return getsizeof(value) + sum(128 + _metadata_cost(key, depth + 1, active, expression_costs)
                    + _metadata_cost(item, depth + 1, active, expression_costs) for key, item in value.items())
            return getsizeof(value) + sum(32 + _metadata_cost(item, depth + 1, active, expression_costs) for item in value)
        finally:
            active.remove(identity)
    if isinstance(value, Enum):
        return 512
    # 已校验查表节点的冻结字节列按真实长度计入固定元数据成本。
    if value is None or type(value) in (str, int, bool, float, bytes):
        return getsizeof(value) + 64
    raise ResultFormatError('历史元数据类型无法估算')


def _expression_metadata_cost(root, depth, active, costs):
    """非递归估算已编译表达式，同时保留原节点、字段和重复引用槽费用。

    参数: root为ExprNode；depth为表达式之外的普通容器深度；active为当前路径；
        costs缓存本次调用同一节点及普通深度下的完整费用。
    返回: 根的完整费用，重复子树每出现一次仍收一次原费用。
    异常: 子节点不是ExprNode、args不是tuple、环或字段结构错误的ResultFormatError。
    副作用: 缓存只活到本次_metadata_bytes返回，不持有样本或跨任务状态。
    """
    pending = [(root, False)]
    entered = []
    try:
        while pending:
            node, complete = pending.pop()
            identity = id(node)
            key = identity, depth
            if complete:
                total = getsizeof(node)
                for field in fields(node):
                    if field.name == 'args':
                        # 子树费用可复用，但每个参数槽的32字节和完整子树费用都保留。
                        total += 256 + getsizeof(node.args) + sum(32 + costs[(id(child), depth)][1]
                                                                 for child in node.args)
                    else:
                        # 非子树字段仍走普通元数据检查，不让表达式包装绕过32层限制。
                        total += 256 + _metadata_cost(getattr(node, field.name), depth + 1, active, costs)
                costs[key] = node, total
                active.remove(identity)
                continue
            if identity in active:
                raise ResultFormatError('历史元数据存在循环引用')
            cached = costs.get(key)
            if cached is not None and cached[0] is node:
                continue
            if type(node) is not ExprNode or type(node.args) is not tuple or any(type(child) is not ExprNode for child in node.args):
                raise ResultFormatError('历史表达式元数据结构无法估算')
            active.add(identity)
            entered.append(identity)
            pending.append((node, True))
            pending.extend((child, False) for child in reversed(node.args))
        return costs[(id(root), depth)][1]
    finally:
        # 失败后的异常栈不能把这次路径登记带进其他元数据位置。
        active.difference_update(entered)


def _pending_bytes(validator: BatchValidator) -> int:
    """估算当前组去重状态，不保留历史所有sequence。

    参数: validator为一个来源协议状态。返回: 保守bytes。
    异常: 已校验状态不主动抛错。
    """
    # set每身份计256bytes，覆盖槽位、整数与局部复制；列固定项单独计。
    return sum(512 + len(sequences) * 256 for _, sequences in validator.pending.values())
