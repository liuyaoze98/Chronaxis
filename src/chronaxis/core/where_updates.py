"""按 where 当前选择判断某一组是否更新输出，独立于输出的数值是否改变。

输入是原子提交后的输入、同一时刻排除该组的旧输入，以及各别名的真实更新标志。
只在条件实际更新时比较前后选择；因此仅刷新有效条件不会采样，失效后恢复会采样。
普通算子取各参数更新并集，嵌套选择递归套用同一协议；不保存时间历史。
"""


def contains_where(root):
    """检查已编译 DAG 是否需要分支更新口径。参数: 根节点。返回: bool。异常: 非法节点。"""
    pending, seen = [root], set()
    while pending:
        node = pending.pop()
        if node.operator == 'where':
            return True
        if id(node) not in seen:
            seen.add(id(node))
            pending.extend(node.args)
    return False


def reference_updates(root, current, before, updates):
    """按原子组计算标量更新标志。

    参数: 根节点、当前/组前标量映射和真实更新标志；内部传 before=None 仅判断活动性。
    返回: 是否存在活动更新。异常: 输入/节点与绑定不符时沿用标量表达式核错误。
    """
    from .expression_reference import _evaluate

    now_cache, old_cache, flags = {}, {}, {}

    def visit(node):
        """判断当前活动路径。参数: 子树节点。返回: bool。异常: 同外层求值。"""
        if node not in flags:
            if node.operator == 'name':
                flag = updates[node.name]
            elif node.operator == 'where':
                condition, when_true, when_false = node.args
                now = _evaluate(condition, current, now_cache).value
                changed = visit(condition)
                if before is None:
                    flag = changed or (now.valid and visit(when_true if now.value else when_false))
                elif not now.valid:
                    flag = changed
                else:
                    # 当前分支即使数值相同也采样；条件刷新则须有切换或恢复。
                    flag = visit(when_true if now.value else when_false)
                    if changed and not flag:
                        old = _evaluate(condition, before, old_cache).value
                        flag = not old.valid or old.value != now.value
            else:
                flag = any(visit(arg) for arg in node.args)
            flags[node] = flag
        return flags[node]

    return bool(visit(root))


def numpy_updates(root, current, before, updates, size):
    """以 NumPy 活动子批检查整列更新证据，不逐点解释。

    参数: 根节点、当前/组前列映射、别名的更新列、行数；内部 before=None 时仅判断活动性。
    返回: 一维布尔列。异常: 原数组布局/求值错误传播。
    """
    import numpy as np
    from .expression_numpy import _evaluate
    from .numeric_numpy import NumericArray

    def condition_at(node, inputs, indices):
        """按活动行解释。参数: 条件子树、输入列及行号。返回: BOOL 列。异常: 数组求值错误。"""
        columns = {}
        for name in node.aliases:
            col = inputs[name]
            columns[name] = col.take(indices)
        return _evaluate(node, columns, len(indices), {}).value

    def visit(node, indices, cache):
        """同一活动行集内复用证据。参数: 子树、行号、局部缓存。返回: 布尔列。异常: 数组错误。"""
        if node in cache:
            return cache[node]
        flag = np.zeros(len(indices), dtype=bool)
        if node.operator == 'name':
            flag = updates[node.name][indices]
        elif node.operator == 'where' and len(indices):
            condition, when_true, when_false = node.args
            now = condition_at(condition, current, indices)
            changed = visit(condition, indices, cache)
            flag |= changed if before is None else changed & ~now.valid
            for selected, branch in ((now.values, when_true), (~now.values, when_false)):
                rows = now.valid & selected
                if np.any(rows):
                    flag[rows] |= visit(branch, indices[rows], {})
            # 仅比较有效条件刷新且未被活动分支更新证明的剩余行。
            rows = changed & now.valid & ~flag
            if before is not None and np.any(rows):
                old = condition_at(condition, before, indices[rows])
                flag[rows] |= ~old.valid | (old.values != now.values[rows])
        else:
            for arg in node.args:
                flag |= visit(arg, indices, cache)
        cache[node] = flag
        return flag

    return visit(root, np.arange(size), {})


def reference_active(root, current, flags):
    """只检查活动输入。参数: 根节点、当前标量、别名标志。返回: bool。异常: 标量求值错误。"""
    return reference_updates(root, current, None, flags)


def numpy_active(root, current, flags, size):
    """按活动子批检查输入。参数: 根节点、当前列、标志列、长度。返回: 布尔列。异常: 数组错误。"""
    return numpy_updates(root, current, None, flags, size)
