"""读取计算列中的有效标量，并按当前消息原值决定方向桶及跳过原因。

这些纯函数不访问来源、消息历史或结果仓；参考与数组执行共用相同边界语义。
无效占位不当有效数值，方向字段不应用普通信号转换，表达式失败原因优先。
"""
from math import isfinite
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q
from ..legacy.sum import LegacySkipReason


def scalar_from_column(column, index):
    """取一项实际归一化值，失效时保留原诊断而不把数组占位当正常值。

    参数: column为本批SignalSeries；index为匹配列位置。返回: ScalarValue。
    异常: 原类型/布局错误；不做第二次数值转换。
    """
    valid, quality = bool(column.valid[index]), Q(int(column.quality[index]))
    # ENUM有效值还原实际逻辑标签；其他有效值取原生标量。
    if valid:
        value = column.labels[int(column.values[index])] if column.labels else column.values[index].item()
    else:
        # 纯消息NumericArray没有展示用原值列；无效性由掩码及原因表达，不读占位。
        originals=getattr(column,'original_values',None)
        value = originals[index] if originals is not None else None
    code = getattr(column, 'code', None)
    return ScalarValue(value, column.dtype, valid, quality, column.labels,
                       None if code is None else scalar_from_column(code, index))

def direction_bucket_state(raw, bucket):
    """按同条原值判桶，既不转换单位也不把缺值或非有限当正常零。

    参数: raw为原生方向数值或None，bucket为已核positive/negative。
    返回: 方向质量及是否选中。异常: TypeError为非原生数值，不接受NumPy标量。
    """
    if raw is not None and type(raw) not in (int, float, bool):
        raise TypeError('disjunction原值需要原生int/float/bool或明确缺失None')
    if raw is None:
        return Q.MISSING, False
    if type(raw) is float and not isfinite(raw):
        return Q.NONFINITE, False
    return Q.NONE, raw > 0 if bucket == 'positive' else raw < 0

def direction_skip_reason(value, reason, direction_quality, selected):
    """保表达式失败优先，只有有效表达式才用原方向决定是否跳过。

    参数: 原数值、原因、方向质量与选择。返回: 最终LegacySkipReason或None。
    异常: 无主动异常；不修改累计器或原质量。
    """
    if value.valid:
        if direction_quality & Q.MISSING:
            return LegacySkipReason.MISSING_INPUT
        if direction_quality & Q.NONFINITE:
            return LegacySkipReason.NONFINITE_INPUT
        if not selected:
            return LegacySkipReason.CONDITION_FALSE
    return reason
