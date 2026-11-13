"""定义现役记录流一次交付的完整同刻组，不执行磁盘回放或排序。"""
from dataclasses import dataclass
from ..timebase.conversion import require_int64_ns
from .record_sample import RecordSample
from .history_records import HistorySample

@dataclass(frozen=True)
class DecodedTimeGroup:
    """保存一个session在同一整数ns的全部更新；来源和原sequence仍独立。"""

    time_ns: int  # 完整组的共同纳秒坐标。
    samples: tuple[HistorySample | RecordSample, ...]  # 同组全部原观测，不套用last_by_sequence策略。

    def __post_init__(self) -> None:
        """检查同刻、同会话和唯一原身份，不执行绑定或表达式。

        参数: 无；读取time_ns/samples。返回: None。
        异常: TypeError/ValueError/OverflowError为结构或身份错误。
        """
        require_int64_ns(self.time_ns)
        if type(self.samples) is not tuple or not self.samples or any(type(item) not in (HistorySample,RecordSample) for item in self.samples):
            raise TypeError('完整时间组需要非空的HistorySample或RecordSample tuple')
        if any(item.time_ns != self.time_ns for item in self.samples) or len({item.source_ref.session_id for item in self.samples}) != 1:
            raise ValueError('时间组不能混用时间或session')
        # 每别名原来源/sequence定位唯一，同原行不同列仍各自保留。
        identities = {(item.source_ref, item.name, item.sequence) for item in self.samples}
        if len(identities) != len(self.samples):
            raise ValueError('完整时间组重复原观测')
