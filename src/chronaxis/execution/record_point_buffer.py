"""共享有限驱动点的接收与失效处理，不执行数值统计或创建历史。

积分和时间统计沿用同一同刻/递增/条件门槛，具体owner负责预付缓冲费用并实现_flush。
该内部基类不能独立构造使用；没有独立预算或第二份输入缓冲。
"""

from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D
from ..results.errors import ResultClosedError
from ..timebase.conversion import require_int64_ns


class RecordPointBuffer:
    """复用一份有限点缓冲，子类初始化字段并拥有数值状态及关闭过程。"""

    def _require_open(self):
        """失败/清理/关闭后拒绝读取与推进。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('记录流统计已关闭、失败或正在清理')

    def consume(self, rows, *, conditions=None, condition_valid_until_ns=None, actual_value_updates=None):
        """接收已按所选驱动求值的有限点，不先截掉窗口两侧记录。

        参数: rows为不超过batch_intervals+1的tuple，每项(time_ns, ScalarValue)，
            或附第三项实际有效截止valid_until_ns；到截止即失效，None表示本点无额外截止。
            conditioned时另传同长conditions及可选实际条件截止tuple；TRUE/FALSE/UNKNOWN分开处理。
            actual_value_updates仅样本统计/选择使用，明确区分真实值更新与条件更新，不提供时保持原五字段缓冲。
        返回: None。异常: 类型、时间倒退/同刻、预算/取消；任何错误后不交付前缀结果。
        约束: 上游处理同刻、条件及TTL；无效值必须传入，不能跳过后连接有效值。
        """
        self._require_open()
        if self._finished:
            raise ResultClosedError('记录流统计已结束，不能继续追加')
        item = value = None
        try:
            if type(rows) is not tuple or len(rows) > self._limit + 1:
                raise ValueError('驱动点需要不超批上限的tuple')
            if actual_value_updates is not None and (type(actual_value_updates) is not tuple
                    or len(actual_value_updates)!=len(rows) or any(type(flag) is not bool for flag in actual_value_updates)):
                raise ValueError('真实更新标志需要同长bool tuple')
            if self._conditioned:
                if type(conditions) is not tuple or len(conditions) != len(rows):
                    raise ValueError('条件统计需要同长BOOL条件tuple')
                if condition_valid_until_ns is not None and (type(condition_valid_until_ns) is not tuple
                        or len(condition_valid_until_ns) != len(rows)):
                    raise ValueError('条件截止需要同长tuple')
            elif conditions is not None or condition_valid_until_ns is not None:
                raise ValueError('无条件统计不能隐式接入条件')
            for index, item in enumerate(rows):
                if type(item) is not tuple or len(item) not in (2, 3):
                    raise TypeError('驱动点需要时间、数值及可选实际有效截止')
                time, value = item[:2]
                deadline = item[2] if len(item) == 3 else None
                if deadline is not None:
                    deadline = require_int64_ns(deadline, 'record_calculation.valid_until_ns')
                time = require_int64_ns(time, 'record_calculation.time_ns')
                if not isinstance(value, ScalarValue) or value.dtype is not self._dtype:
                    raise TypeError('驱动点数值与声明dtype不同')
                if self._last_time is not None and time <= self._last_time:
                    raise ValueError('驱动点必须严格递增；同刻更新应先按既有政策归组')
                condition = conditions[index] if self._conditioned else None
                condition_deadline = None if condition_valid_until_ns is None else condition_valid_until_ns[index]
                if self._conditioned and (not isinstance(condition, ScalarValue) or condition.dtype is not D.BOOL):
                    raise TypeError('统计选择条件需要BOOL ScalarValue')
                if condition_deadline is not None:
                    condition_deadline = require_int64_ns(condition_deadline, 'record_calculation.condition_valid_until_ns')
                # 只保计算必需的冻结数值与实际时间，不留下原消息或来源对象。
                self._rows.append((time, value, deadline, condition, condition_deadline)
                    +(() if actual_value_updates is None else (actual_value_updates[index],)))
                self._last_time = time
                if len(self._rows) == self._limit + 1:
                    self._flush()
        except BaseException:
            self._failed = True
            raise
        finally:
            rows = item = value = conditions = condition = condition_valid_until_ns = None

    def expire_at(self, time_ns, *, condition=False):
        """依赖中途失效时截断最后待结算驱动点，不新增驱动点或补计周期。

        参数: time_ns为已按序处理的失效实际时刻；condition=True只截断选择条件。返回: None。
        异常: 非法/回退时间或对象关闭失败；调用方必须在下一驱动点进入前通知。
        """
        self._require_open()
        if self._finished:
            raise ResultClosedError('记录流统计已结束，不能修改有效截止')
        try:
            if type(condition) is not bool or condition and not self._conditioned:
                raise ValueError('条件失效通知只能用于条件统计')
            time = require_int64_ns(time_ns, 'record_calculation.expire_at')
            if self._last_time is not None and time < self._last_time:
                raise ValueError('失效通知不能回退到已处理驱动点之前')
            if self._rows:
                index = 4 if condition else 2
                previous = self._rows[-1]
                deadline = previous[index]
                self._rows[-1] = previous[:index] + (time if deadline is None else min(time, deadline),) + previous[index+1:]
        except BaseException:
            self._failed = True
            raise
