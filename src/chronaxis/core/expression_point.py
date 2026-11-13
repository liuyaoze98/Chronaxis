"""为流式状态上的一个时刻准备独立生产求值，不装箱成单元素数组。

PointProgram只持有当前表达式的只读节点、常量和查表视图。每次求值的缓存
由调用者创建和释放，不能跨点复用数值。内建操作由numeric_point独立计算；
reference和真正批量NumPy入口不变。宿主扩展保留所选NumPy回调和列接口，
只在该边界产生必要的单元素列，未选分支不调用宿主。
"""

from .expression import ExprNode
from .expression_reference import Evaluation
from .expression_integer_v4 import INTEGER_KERNELS
from .expression_math_v4 import MATH_KERNELS
from .numeric import result_dtype
from .numeric_point import (
    _COMPARE, affine_point, binary_point, failed, integer_point, logic_point,
    lookup_point, math_point, to_float_point, unary_point)
from .scalar import ScalarValue
from .types import QualityFlag as Q, SignalDType as D, _QUALITY_BY_MASK


def _column(value):
    """仅为NumPy宿主边界装一条列。参数: typed值。返回: NumericArray。异常: 原列模型错误。"""
    import numpy as np
    from .numeric_numpy import DTYPES, NumericArray

    physical = value.labels.index(value.value) if value.valid and value.labels else value.value if value.valid else 0
    code = None if value.code is None else _column(value.code)
    return NumericArray(value.dtype, np.array([physical], dtype=DTYPES[value.dtype]),
                        np.array([value.valid], dtype=bool),
                        np.array([int(value.quality)], dtype=np.uint16), value.labels, code)


def _scalar(column):
    """从宿主返回列恢复第一个值。参数: 已校验单行列。返回: ScalarValue。异常: 原模型错误。"""
    valid, quality = bool(column.valid[0]), Q(int(column.quality[0]))
    value = (column.labels[int(column.values[0])] if column.labels else column.values[0].item()) if valid else None
    code = None if column.code is None else _scalar(column.code)
    return ScalarValue(value, column.dtype, valid, quality, column.labels, code)


class PointProgram:
    """持有单个已核表达式的准备数据，不拥有输入状态或跨点值缓存。

    构造费用由DriverExpression的固定预算预付；查表只持有打包数据的只读视图。
    实例使用期间表达式和注册保持冻结，调用者在关闭时释放整个实例。
    """

    def __init__(self, root):
        """一次准备常量、节点索引和所需查表。

        参数: 已通过声明/绑定核对的ExprNode。返回: 新准备对象。
        异常: 内部未支持节点、结构或分配错误；不执行任何宿主回调。
        """
        if type(root) is not ExprNode:
            raise TypeError('逐点准备需要已编译表达式节点')
        self.root = root
        self._constants, self._tables, self._names, self._nodes = {}, {}, {}, {}
        pending = [root]
        known = {'const', 'name', 'where', 'enum_code', 'and', 'or', 'not',
                 'abs', 'neg', 'to_float', 'unit_convert', 'lookup', 'host_function',
                 'isclose', 'add', 'sub', 'mul', 'div', *_COMPARE,
                 *MATH_KERNELS, *INTEGER_KERNELS}
        while pending:
            node = pending.pop()
            key = id(node)
            if key in self._nodes:
                continue
            if node.operator not in known and not (
                    node.operator.startswith('int_literal_') and node.operator[12:] in _COMPARE):
                raise ValueError('未登记的生产逐点操作：' + node.operator)
            # 混合浮点字面量的许可只影响静态类型关系；在准备时核实一次，
            # 每个有效值仍须通过独立数值核的无损float转换，不能据许可放宽精度。
            if node.operator in {'add', 'sub', 'mul', 'div', *_COMPARE}:
                expected = result_dtype(node.operator, node.args[0].dtype, node.args[1].dtype,
                                        node.allow_float_literal)
                if expected is not node.dtype:
                    raise ValueError('逐点运算结果类型与已编译节点不同')
            self._nodes[key] = node
            if node.operator == 'const':
                self._constants[key] = ScalarValue(node.value, node.dtype, labels=node.labels)
            elif node.operator == 'name':
                self._names[key] = node.name
            elif node.operator == 'lookup':
                import numpy as np
                from .numeric_numpy import DTYPES
                table = node.value.packed()
                self._tables[key] = (
                    table, np.frombuffer(table.axis, dtype='<f8'),
                    np.frombuffer(table.values, dtype=DTYPES[table.dtype].newbyteorder('<')))
            pending.extend(node.args)

    def used_names(self, cache):
        """遍历本点实际访问的别名。参数: 本实例本次缓存。返回: 名称迭代器。异常: 非法缓存键。"""
        for key in cache:
            if key in self._names:
                yield self._names[key]

    def evaluate(self, context, cache):
        """求根节点。参数: 当前规范标量映射、本点空缓存。返回: Evaluation。异常: 计算/宿主错误。"""
        return self._evaluate(self.root, context, cache)

    def _evaluate(self, node, context, cache):
        """解释一个活动子树，身份缓存只属于本次点。

        参数: 本程序节点、当前typed值、局部缓存。返回: Evaluation。
        异常: 内部节点/输入合同错误及宿主异常原样传播。
        """
        key = id(node)
        if key in cache:
            return cache[key]
        if self._nodes.get(key) is not node:
            raise ValueError('逐点节点不属于当前准备对象')
        op = node.operator
        if op == 'const':
            result = Evaluation(self._constants[key], Q.NONE)
        elif op == 'name':
            value = context[node.name]
            result = Evaluation(value, value.quality)
        elif op == 'where':
            condition = self._evaluate(node.args[0], context, cache)
            if not condition.value.valid:
                result = Evaluation(failed(node.dtype, condition.value.quality, node.labels),
                                    condition.dependency_quality)
            else:
                branch = self._evaluate(node.args[1 if condition.value.value else 2], context, cache)
                result = Evaluation(branch.value, _QUALITY_BY_MASK[
                    int(condition.dependency_quality) | int(branch.dependency_quality)])
        elif op == 'enum_code':
            value = self._evaluate(node.args[0], context, cache).value
            if value.code is not None and value.code.dtype is node.dtype:
                code = value.code
            elif value.code is None and value.quality & (Q.MISSING | Q.STALE):
                code = failed(node.dtype, value.quality)
            else:
                raise ValueError('枚举缺少与声明一致的原码投影，无法从标签还原代码')
            result = Evaluation(code, code.quality)
        else:
            children = tuple(self._evaluate(arg, context, cache) for arg in node.args)
            values = tuple(child.value for child in children)
            # 子值已由数值核/宿主边界验证；先合并整数位，返回时恢复同一公开枚举。
            diagnostic = 0
            for child in children:
                diagnostic |= int(child.dependency_quality)
            if op in ('and', 'or', 'not'):
                value = logic_point(op, values)
            elif op in ('abs', 'neg'):
                value = unary_point(op, values[0])
            elif op == 'to_float':
                value = to_float_point(values[0])
            elif op == 'unit_convert':
                value = affine_point(values[0], *node.value, node.dtype)
            elif op == 'lookup':
                value = lookup_point(*self._tables[key], values[0])
            elif op == 'host_function':
                from ..extension_runtime import point_call
                value = _scalar(point_call(node.host_function, 'numpy', tuple(_column(v) for v in values)))
            elif op in MATH_KERNELS:
                value = math_point(op, values)
            elif op in INTEGER_KERNELS:
                value = integer_point(node, values)
            elif op.startswith('int_literal_'):
                first = values[0]
                value = (ScalarValue(_COMPARE[op[12:]](first.value, node.value), D.BOOL)
                         if first.valid else failed(D.BOOL, first.quality))
            elif op == 'isclose':
                a, b, atol, rtol = tuple(to_float_point(item) for item in values)
                distance = unary_point('abs', binary_point('sub', a, b, D.FLOAT64))
                relative = binary_point('mul', rtol, unary_point('abs', b), D.FLOAT64)
                tolerance = binary_point('add', atol, relative, D.FLOAT64)
                value = binary_point('le', distance, tolerance, D.BOOL)
                for item in (a, b, atol, rtol, distance, tolerance):
                    diagnostic |= int(item.quality)
            else:
                value = binary_point(op, values[0], values[1], node.dtype)
            result = Evaluation(value, _QUALITY_BY_MASK[diagnostic | int(value.quality)])
        cache[key] = result
        return result

    def updates(self, root, current, before, updates):
        """按活动分支判断原子组是否产生更新，不用数值相等替代更新证据。

        参数: 本程序子树、当前/组前标量、真实更新标志；before=None仅判断活动性。
        返回: bool。异常: 条件求值或内部节点错误。
        """
        now_cache, old_cache, memo = {}, {}, {}

        def changed(node):
            """检查子树的活动更新。参数: 子树。返回: bool。异常: 原条件求值错误。"""
            key = id(node)
            if key in memo:
                return memo[key]
            if node.operator == 'name':
                result = updates[node.name]
            elif node.operator == 'where':
                condition, positive, negative = node.args
                now = self._evaluate(condition, current, now_cache).value
                condition_updated = changed(condition)
                if before is None:
                    result = condition_updated or (now.valid and changed(positive if now.value else negative))
                elif not now.valid:
                    result = condition_updated
                else:
                    result = changed(positive if now.value else negative)
                    if condition_updated and not result:
                        old = self._evaluate(condition, before, old_cache).value
                        result = not old.valid or now.value != old.value
            else:
                result = any(changed(child) for child in node.args)
            memo[key] = result
            return result

        return bool(changed(root))

    def active(self, root, context, flags):
        """判断被标记的依赖是否活动。参数: 根、当前值和别名标志。返回: bool。异常: 条件错误。"""
        return self.updates(root, context, None, flags)
