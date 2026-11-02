"""从相邻两次相关更新取得计算间隔，不创建另一套时间坐标。

调用者先按已解析的驱动选择相关更新，再逐条调用advance，包括值无效的更新。
首条只建立前序；actual取实际时间差，固定周期每次后续更新返回同一个间隔。
本模块不依赖CAN、DBC、文件边界或信号值，不保存消息历史、累计总数或输出证明。
DBC周期由接入层初始化核实后作为step_ns传入，不能在这里猜默认周期。
"""

from ..timebase.conversion import require_int64_ns
from .models import Interval


def require_record_step(step_ns, actual_updates):
    """核实记录对周期入口，禁止把合成边界当成驱动更新。

    参数: step_ns为None或正整数ns；actual_updates为已经校验的真实更新标志。
    返回: None。异常: 非法周期或非真实更新报错；不读取或保存记录。
    """
    if step_ns is not None:
        require_int64_ns(step_ns, 'interval.step_ns')
        if step_ns <= 0:
            raise ValueError('计算周期必须为正整数纳秒')
        if not all(actual_updates):
            raise ValueError('固定/DBC计算块只能包含所选驱动的真实更新，不能包含合成边界')


def clipped_record_seconds(start_ns: int, end_ns: int, window: Interval, *,
                           step_ns: int | None = None) -> float:
    """按实际交集折算一对记录用于积分或加权的秒数，不生成时间坐标。

    参数: start_ns/end_ns为相关记录对的实际整数纳秒；window为真实请求Interval；
        step_ns=None取实际差，正整数取固定或已核实DBC周期。
    返回: float秒数。固定模式使用step_ns×实际交集/实际跨度，最后才换为秒；
        不取整到纳秒，无交集或零跨度返回0。普通连续统计的同刻更新由上层按
        same_time_policy归组，零跨度不形成连续面积；旧逐消息N次累计不调用本函数。
    异常: 类型、int64边界、倒退或非法周期错误；无状态、I/O或持久化副作用。
    """
    start = require_int64_ns(start_ns, 'interval.start_ns')
    end = require_int64_ns(end_ns, 'interval.end_ns')
    if end < start:
        raise ValueError('记录对时间回退')
    if not isinstance(window, Interval):
        raise TypeError('记录对裁剪需要实际时间Interval')
    if step_ns is not None:
        step_ns = require_int64_ns(step_ns, 'interval.step_ns')
        if step_ns <= 0:
            raise ValueError('计算间隔必须为正整数纳秒')
    overlap = min(end, window.end_ns) - max(start, window.start_ns)
    if overlap <= 0:
        return 0.0
    if step_ns is None:
        # 不把绝对坐标转float，避免大时间戳吃掉细小间隔。
        return require_int64_ns(overlap, 'interval.overlap_ns') / 1_000_000_000
    # Python整数乘法和除法避免int64乘积溢出；只在最终秒数处舍入一次。
    return (step_ns * overlap) / ((end - start) * 1_000_000_000)


class RecordIntervals:
    """一个消费者的一份前序状态，跨文件/批次复用，独立任务使用独立实例。

    只保存必要的上一条实际时间及可选固定周期。即使选择固定周期，也用上一条
    实际时间拒绝倒退；不将累计周期伪装为实际时间，不保留第二列时间。
    """

    __slots__ = ('_step_ns', '_previous_ns')

    def __init__(self, step_ns: int | None = None):
        """创建相邻更新状态，不读取输入或分配历史容器。

        参数: step_ns=None表示实际间隔；正整数表示已选固定或已核实的DBC周期。
        返回: 新状态。异常: TypeError、ValueError或TimeOverflowError为非法周期。
        """
        if step_ns is not None:
            step_ns = require_int64_ns(step_ns, 'interval.step_ns')
            if step_ns <= 0:
                raise ValueError('计算间隔必须为正整数纳秒')
        self._step_ns = step_ns
        self._previous_ns = None

    def advance(self, time_ns: int) -> int | None:
        """接收一条相关更新，返回此前一对记录的间隔。

        参数: time_ns为当前记录实际整数纳秒，已按所需驱动筛选；无效值不能跳过调用。
        返回: 首条None，随后actual为非负实际差，固定周期为正step_ns。同刻记录不去重。
        异常: 类型、int64溢出或时间倒退；失败前不修改前序状态。
        边界: 不接收文件/EOF通知，不补尾段；既有actual期限、裁剪和TTL由消费者处理。
        """
        current = require_int64_ns(time_ns, 'interval.time_ns')
        previous = self._previous_ns
        if previous is None:
            self._previous_ns = current
            return None
        if current < previous:
            raise ValueError('相关记录时间回退，不能重排或跨过该记录')
        # 固定周期无需计算实际差；跨度溢出只对确实使用actual差值的消费者有意义。
        step = (require_int64_ns(current - previous, 'interval.actual_ns')
                if self._step_ns is None else self._step_ns)
        self._previous_ns = current
        return step

    def advance_seconds(self, time_ns: int, window: Interval) -> float | None:
        """接收相关更新并返回裁剪后的计算秒数，只保同一份前序状态。

        参数: time_ns为当前实际时间；window为当前消费者实际请求范围。
        返回: 首条None，之后为交集折算秒数；窗口外更新仍推进前序，不能跳过。
        异常: 时间、窗口或裁剪错误；失败不修改前序。无文件边界重置或EOF补周期。
        """
        current = require_int64_ns(time_ns, 'interval.time_ns')
        if not isinstance(window, Interval):
            raise TypeError('记录对裁剪需要实际时间Interval')
        previous = self._previous_ns
        seconds = (None if previous is None else
                   clipped_record_seconds(previous, current, window, step_ns=self._step_ns))
        self._previous_ns = current
        return seconds
