"""从最新完整组提取 where 的反事实输入和活动更新证据，不读历史文件。

同一组可能同时替换条件与两个分支。取状态已保存的旧规范标量，在本时刻检查
TTL 和来源范围，两种后端分别解释前后条件。所需临时空间由调用侧查询预付。
"""

from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q
from ..core.where_updates import reference_updates, numpy_updates, reference_active, numpy_active


def before_context(state, names, time, *, ends=None, bounds=None, continuous=False, left_limit=False):
    """构造同刻排除最近组的点、右侧或左侧保持。

    参数: 最新状态、依赖、纳秒，ends/bounds 来源范围及视图。
    返回: 标量映射。异常: 声明或类型错误；不回退状态。
    """
    context = {}
    for name in names:
        definition = state.definitions[name]
        previous = state._before_group(name)
        start, end = bounds[definition.source] if bounds is not None else (
            None, None if ends is None else ends.get(definition.source))
        if previous is None:
            context[name] = ScalarValue(None, definition.dtype, False, Q.MISSING, state._labels.get(name, ()))
            continue
        timestamp, value = previous
        reason = Q.NONE
        elapsed = time - timestamp
        if elapsed > definition.valid_for_ns or (not left_limit and elapsed == definition.valid_for_ns):
            reason |= Q.STALE
        if ((start is not None and (time <= start if left_limit else time < start)) or
                (end is not None and (time >= end if continuous and not left_limit else time > end))):
            reason |= Q.MISSING
        from ..core.enum_codes import expire_value
        context[name] = expire_value(value, reason) if reason else value
    return context


def scalar_columns(context):
    """单点 NumPy 调用保留原 dtype/标签。

    参数: 规范标量映射。返回: 单行列映射，大整数不转 float。异常: 非法标签或列类型。
    """
    import numpy as np
    from ..core.numeric_numpy import NumericArray, DTYPES

    columns = {}
    for name, value in context.items():
        physical = value.labels.index(value.value) if value.valid and value.labels else value.value if value.valid else 0
        code = None if value.code is None else scalar_columns({name: value.code})[name]
        columns[name] = NumericArray(value.dtype, np.array([physical], dtype=DTYPES[value.dtype]),
            np.array([value.valid], dtype=bool), np.array([int(value.quality)], dtype=np.uint16), value.labels, code)
    return columns


def group_updates(root, context, previous, updates, backend):
    """计算原子组是否更新输出。参数: 根、当前/左侧值、各别名更新、后端。返回: bool。异常: 求值原错。"""
    if not any(updates.values()):
        return False
    if backend == 'reference':
        return reference_updates(root, context, previous, updates)
    import numpy as np
    return bool(numpy_updates(root, scalar_columns(context), scalar_columns(previous),
                              {name: np.array([flag], dtype=bool) for name, flag in updates.items()}, 1)[0])


def group_active(root, context, flags, backend):
    """检查标记输入是否活动。参数: 根、点值、别名标志、后端。返回: bool。异常: 求值错误。"""
    if not any(flags.values()):
        return False
    if backend == 'reference':
        return reference_active(root, context, flags)
    import numpy as np
    return bool(numpy_active(root, scalar_columns(context),
                             {name: np.array([flag], dtype=bool) for name, flag in flags.items()}, 1)[0])
