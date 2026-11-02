"""把一小批实际记录及有效截止交给既有样本统计/选择核。

只在当前批插入必要的失效边界，不保存另一条时间轴；这些边界的真实更新标志为False。
半开范围及共享右端由原CalculationSeries/CalculationDefinition处理，不把保持值当作新样本。
"""
from ..core.calculations import CalculationSeries
from ..core.models import Interval
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q


def sample_series(rows,unit,conditioned):
    """构造有界核输入。参数: 至少两点的内部行/单位/条件开关。返回: CalculationSeries。异常: 类型/时间错误。"""
    times=[];values=[];conditions=[];updates=[]
    for index,row in enumerate(rows):
        time,value,deadline,condition,condition_end=row[:5]
        end=rows[index+1][0] if index+1<len(rows) else time
        # 每对最多两个不同过期点；不插入计算所选固定周期的虚构时刻。
        points=(time,*sorted({d for d in (deadline,condition_end) if d is not None and time<d<end}))
        for point in points:
            times.append(point)
            values.append(ScalarValue(None,value.dtype,False,value.quality|Q.STALE,value.labels)
                if deadline is not None and point>=deadline and point<end else value)
            if conditioned:
                conditions.append(ScalarValue(None,condition.dtype,False,condition.quality|Q.STALE,condition.labels)
                    if condition_end is not None and point>=condition_end and point<end else condition)
            updates.append(bool(row[5]) if point==time and len(row)>5 else False)
    return CalculationSeries(Interval(times[0],times[-1]),tuple(times),tuple(values),tuple(updates),unit,
        conditions=tuple(conditions) if conditioned else None)
