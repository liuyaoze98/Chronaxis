"""声明完整窗口变化量的输入、配置和结果，不读取文件或保存触发状态。

输入是有限ZOH已经划分好的连续片段，坐标为整数纳秒，数值保留声明dtype。
片段起点的真实点质量可以不同于连续质量，例如真实EOF样本仍有效，但不能
向EOF后保持。两个后端共用结构检查；数值、覆盖率和单调判断分别实现。
结果把数值变化量与条件真假分开，缺数据不返回零，也不在这里生成事件。
"""

from dataclasses import dataclass
from math import isfinite
from .types import QualityFlag as Q, SignalDType as D, Truth
from ..timebase.conversion import require_int64_ns


@dataclass(frozen=True)
class WindowDeltaSpec:
    """保存窗口长度、方向、阈值及单调要求；只接受完整覆盖政策。"""

    window_ns: int  # 完整回看长度，必须为正。
    threshold: int | float  # 非负门槛，单位与输入相同，包含等于门槛。
    direction: str = 'any'  # rise末减首，fall首减末，any取绝对差。
    monotonic: bool = False  # rise非降、fall非升、any二者任一。
    coverage_policy: str = 'full'  # 样本兼容口径不在本核心隐式启用。

    def __post_init__(self):
        """检查明确参数，不从名字猜时长或单位。

        参数: 无，读取冻结字段。返回: None。异常: 类型、非有限或范围错误。
        """
        object.__setattr__(self, 'window_ns', require_int64_ns(self.window_ns))
        if self.window_ns <= 0 or self.direction not in ('rise', 'fall', 'any'):
            raise ValueError('window_delta窗口须为正，方向须为rise/fall/any')
        if type(self.monotonic) is not bool or type(self.threshold) not in (int, float):
            raise TypeError('monotonic需bool，threshold需数值且不能为bool')
        if self.threshold < 0 or (type(self.threshold) is float and not isfinite(self.threshold)):
            raise ValueError('threshold须为非负有限数值')
        if self.coverage_policy != 'full':
            raise ValueError('当前window_delta仅支持full覆盖政策')


@dataclass(frozen=True)
class DeltaSpan:
    """保存一段常值和起点点值；零长度仅用于真实末点。

    quality适用于[start_ns,end_ns)，point_quality适用于start_ns。
    值为None时两种质量都须说明无效原因。时间到期不能通过延长end_ns补齐。
    """

    start_ns: int  # 当前更新或有效性边界。
    end_ns: int  # 连续值排除的右端。
    value: int | float | None  # 规范后的原生数值，未知可为None。
    quality: Q = Q.NONE  # 连续区间无效原因。
    point_quality: Q | None = None  # 默认与连续质量相同。

    def __post_init__(self):
        """规范纳秒和点质量，并检查有值证据。

        参数: 无。返回: None。异常: 类型、倒序或未知无原因。
        """
        object.__setattr__(self, 'start_ns', require_int64_ns(self.start_ns))
        object.__setattr__(self, 'end_ns', require_int64_ns(self.end_ns))
        if self.end_ns < self.start_ns:
            raise ValueError('DeltaSpan终点不得早于起点')
        if not isinstance(self.quality, Q):
            raise TypeError('DeltaSpan质量需QualityFlag')
        if self.point_quality is None:
            object.__setattr__(self, 'point_quality', self.quality)
        if not isinstance(self.point_quality, Q):
            raise TypeError('DeltaSpan点质量需QualityFlag')
        if self.value is None:
            if self.quality == Q.NONE or self.point_quality == Q.NONE:
                raise ValueError('没有数值必须注明未知原因')
        elif type(self.value) not in (int, float):
            raise TypeError('DeltaSpan值需原生int/float或None')


@dataclass(frozen=True)
class WindowDeltaResult:
    """保存一次窗口结果；value与方向一致，condition额外考虑单调要求。

    valid_duration_ns只计完整窗口内已知连续时间；端点无效也会令条件UNKNOWN，
    即使连续覆盖率恰好为1。monotonic是对应方向的实测结果，未知时为None。
    """

    time_ns: int  # 当前判断时刻。
    window_start_ns: int  # 精确Python整数，不因回看低于int64下限回绕。
    value: int | float | None  # 定宽差值或None，绝不以0替代未知。
    condition: Truth  # TRUE/FALSE/UNKNOWN。
    quality: Q  # UNKNOWN原因；已知为NONE。
    valid_duration_ns: int  # 已知连续时间长度。
    coverage: float  # 已知时间/完整窗口时长。
    monotonic: bool | None  # 对应方向是否单调。


def validate_delta_input(spec, spans, time_ns, dtype):
    """检查两个数值核共用的结构及dtype，不计算变化量或单调性。

    参数: spec配置，spans不可变有序片段，time_ns判断时间，dtype声明类型。
    返回: 规范int判断时间。异常: 类型、重叠、非法值或dtype范围错误。
    """
    time_ns = require_int64_ns(time_ns)
    if not isinstance(spec, WindowDeltaSpec) or type(spans) is not tuple:
        raise TypeError('窗口需要WindowDeltaSpec及DeltaSpan tuple')
    if dtype not in (D.INT64, D.UINT64, D.FLOAT64):
        raise TypeError('window_delta只支持数值信号')
    previous = None
    for item in spans:
        # 重叠输入会重复计算覆盖率，不能在核中悄悄排序或合并。
        if not isinstance(item, DeltaSpan):
            raise TypeError('窗口输入需DeltaSpan')
        if previous is not None and (item.start_ns < previous.end_ns or item.start_ns <= previous.start_ns):
            raise ValueError('窗口片段必须严格有序且不重叠')
        previous = item
        if item.value is None or (item.quality != Q.NONE and item.point_quality != Q.NONE):
            continue
        if dtype is D.FLOAT64:
            if type(item.value) is not float or not isfinite(item.value):
                raise ValueError('有效float64输入须为有限原生float')
        elif type(item.value) is not int:
            raise TypeError('有效整数信号不能隐式转浮点')
        elif not (-(2**63) <= item.value < 2**63 if dtype is D.INT64 else 0 <= item.value < 2**64):
            raise ValueError('有效数值超出声明dtype')
    return time_ns
