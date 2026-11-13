"""按实际对象身份估算一次运行借用的静态声明，不展开重复引用。

输入只限已经校验的声明模型；返回浅对象及其独有子对象的字节估计。
此函数用于计划、编译树的固定费用，不改变样本、历史或动态工作区的计费。
已有父资源持有的对象可显式排除；这里只计算费用，不接管它们的生命周期。
"""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from sys import getsizeof

from ..core.expression import ExprNode
from ..extensions import ExtensionRegistry, FunctionSpec, ReductionSpec, TransformSpec
from ..results.errors import ResultFormatError


def static_metadata_bytes(value, *, borrowed=()):
    """遍历不可变声明图，一次调用内每个实际对象只计一次。

    参数: value为已校验声明，borrowed为仍由父资源计费的实际对象。
    返回: 对象、容器和实例属性字典的保守字节数；只读映射另计背后字典槽。
    异常: ResultFormatError为循环、未知结构或普通容器超过32层。
    表达式args用显式栈处理，不将合法表达式长度当成外部协议深度。
    """
    seen = set()
    if borrowed:
        # 真正新建的定义可能仍借用旧choices/单位字符串，父声明的共享子对象同样排除。
        _static_metadata_cost(borrowed, seen)
    return _static_metadata_cost(value, seen)


def _static_metadata_cost(value, seen):
    """累加尚未登记的对象并更新本次身份集合。

    参数: value为冻结声明；seen包含仍由父声明持有或本次已计费的对象身份。
    返回: 新增费用。异常: 循环、深度或类型错误。集合只活在本次估算调用内。
    """
    active, pending, total = set(), [(value, 0, False)], 0
    while pending:
        item, depth, leaving = pending.pop()
        identity = id(item)
        if leaving:
            active.remove(identity)
            seen.add(identity)
            continue
        if identity in active:
            raise ResultFormatError('静态声明存在循环引用')
        if identity in seen:
            continue
        if depth > 32:
            raise ResultFormatError('静态声明容器超过32层')
        # 回调与注册表由宿主持有，不遍历任意Python函数及其全局环境。
        if type(item) in (ExtensionRegistry, FunctionSpec, ReductionSpec, TransformSpec):
            total += 256
            seen.add(identity)
            continue
        if isinstance(item, Enum) or item is None or type(item) in (str, int, bool, float, bytes):
            total += getsizeof(item)
            seen.add(identity)
            continue
        if is_dataclass(item) and not isinstance(item, type):
            # slots实例的字段槽已在实例本体中；普通实例还持有自己的属性字典。
            attributes = getattr(item, '__dict__', None)
            total += getsizeof(item) + (0 if attributes is None else getsizeof(attributes))
            children = []
            for field in fields(item):
                member = getattr(item, field.name)
                if type(item) is ExprNode and field.name == 'args':
                    if type(member) is not tuple or any(type(child) is not ExprNode for child in member):
                        raise ResultFormatError('静态表达式参数结构错误')
                    # args容器本身独立计费，子节点延续表达式外的普通深度。
                    if id(member) not in seen:
                        total += getsizeof(member)
                        seen.add(id(member))
                    children.extend((child, depth, False) for child in member)
                else:
                    children.append((member, depth + 1, False))
        elif isinstance(item, Mapping):
            total += getsizeof(item)
            if type(item) is not dict:
                # 冻结模型使用只读proxy，getsizeof只含代理，不含紧凑背后dict。
                # 单独覆盖其桶和引用槽；键值对象随后按身份计费，不再复制整棵树。
                total += 256 + 64 * len(item)
            children = [(member, depth + 1, False) for pair in item.items() for member in pair]
        elif type(item) is tuple:
            total += getsizeof(item)
            children = [(member, depth + 1, False) for member in item]
        else:
            raise ResultFormatError('静态声明类型无法估算')
        # DFS离开时才登记seen，保证共享子树去重不会掩盖环。
        active.add(identity)
        pending.append((item, depth, True))
        pending.extend(reversed(children))
    return total
