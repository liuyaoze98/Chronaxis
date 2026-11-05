"""保留一个变换所需的有限真实记录区间，按原端点裁剪滚动窗口。

actual 以实际纳秒度量历史。fixed/dbc 每对真实驱动贡献一个周期，网格
在该对内部按实际经过比例取权重。只存原起止、值和有效截止，不存第二条
累计时间轴，也不为整个观测域预生成网格。缓存由执行者的共享预算预付。
"""

from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from ..results.budget import _reserve_owned_ram, _release_owned_ram


@dataclass(frozen=True, slots=True)
class TransformSpan:
    """保存一个已确定右端的保持区间；更新标志区分真实输入点与普通调度边界。"""
    start: int
    end: int
    value: object
    deadline: int | None
    update: bool
    point: object
    pair_width: int | None = None  # 异步实测间隔所属原驱动对的实际跨度，不是第二个时间坐标。


def first_grid(start, origin, step):
    """找不早于起点的首个原点网格。参数: 三个整数ns。返回: 整数ns。异常: 步长非正。"""
    if step <= 0:
        raise ValueError('网格步长须为正')
    return origin + ((start-origin+step-1)//step)*step


class TransformWindow:
    """仅持有最近窗口及其左边界所在原区间。按实际容量付费，关闭可重复。"""

    def __init__(self,budget,window_ns,period_ns):
        """参数: 共享预算、历史窗口和可选原记录周期。返回: owner。异常: 非法窗口。"""
        self._budget,self.window,self.period=budget,window_ns,period_ns
        self._held_cost=self._span_cost=0
        self.spans=deque()
        self.weight=0

    def append(self,span):
        """记录已确定的真实区间。参数: TransformSpan。返回: 无。异常: 端点不连续或预算不足。"""
        if span.end<=span.start or self.spans and span.start!=self.spans[-1].end:
            raise ValueError('变换历史必须由连续正区间组成')
        _reserve_owned_ram(self,1024,'_span_cost')
        self.spans.append(span)
        self.weight+=self._weight(span)

    def _weight(self,span):
        """将真实子段按原驱动对比例折算。参数: 原子段。返回: 有理数纳秒。异常: 非正驱动跨度。"""
        length=span.end-span.start
        return Fraction(self.period*length,span.pair_width or length) if self.period is not None else length

    def trim(self):
        """全部不晚于最新区间右端的网格均消费后逐出旧历史。参数: 无。返回: 无。异常: 退款失败。"""
        while self.spans:
            first=self.spans[0]
            weight=self._weight(first)
            if self.weight-weight<self.window:
                break
            self.spans.popleft()
            self.weight-=weight
            _release_owned_ram(self,1024,'_span_cost')

    def slices(self,time):
        """倒序遍历网格左侧窗口。参数: 实际整数ns。返回: (原区间,裁剪左/右,权重倍率)流。异常: 结构错误。"""
        remaining=Fraction(self.window)
        for span in reversed(self.spans):
            right=min(time,span.end)
            if right<=span.start:
                continue
            ratio=self._weight(span)/Fraction(span.end-span.start)
            amount=min(remaining,(right-span.start)*ratio)
            yield span, right-amount/ratio, right, ratio
            remaining-=amount
            if not remaining:
                break

    def close(self):
        """丢弃窗口与预算。参数: 无。返回: 无。异常: 退款失败可重试。"""
        self.spans.clear()
        _release_owned_ram(self,self._span_cost,'_span_cost')
