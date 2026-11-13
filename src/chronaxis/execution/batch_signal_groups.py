"""将已校验的解析信号批按watermark归为同刻组，不创建磁盘历史。

来源适配器负责原输入及跨批合同。本层只保尚未完整的组，最大时间组等到
后续时间或真实EOF才交付；超出预算直接失败，不拆散同刻更新。
"""

import heapq
from ..core.models import SourceRef
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .groups import DecodedTimeGroup
from .record_sample import _record_from_validated_fields
from ..core.types import SignalDType as D
from .calculation_values import _scalar_from_validated_column
from .history import _metadata_bytes


class BatchSignalGroups:
    """借用已验证批，拥有未完成样本与有限排序状态。"""

    def __init__(self, budget, definitions, session_id, consumer):
        """预付状态。参数: 预算、有限定义、会话、consumer。返回: owner。异常: 预算/取消原错。"""
        self._budget, self._consumer = budget, consumer
        self._held_cost = self._fixed_cost = self._sample_cost = self._work_cost = 0
        self._heap = None
        self._refs = None
        self._serial = 0
        self._maximum = self._last = None
        self._closed = self._failed = self._finished = False
        try:
            _reserve_owned_ram(self, 65536 + 32*_metadata_bytes(definitions), '_fixed_cost')
            self._refs = {item.name: SourceRef(session_id, item.source, item.field) for item in definitions}
            self._heap = []
        except BaseException as error:
            _cleanup_owner(self, error, 'batch_groups_cleanup_owner', '解析信号归组')
            raise

    def consume(self, batch):
        """保必要规范值，按完成进度交付组；丢弃原值/详细来源副本。

        参数: 可信适配器已校验SignalBatch。返回: None。异常: 预算/模型/回退，失败后只清理。
        """
        if self._closed or self._failed or self._finished:
            raise ResultClosedError('解析信号组已关闭、失败或结束')
        sample = value = column = None
        try:
            for column in batch.series.values():
                for index in range(len(column.time_ns)):
                    time = int(column.time_ns[index])
                    if self._last is not None and time <= self._last:
                        raise ValueError('来源在已交付同刻组之后又返回旧样本')
                    _reserve_owned_ram(self, 8192, '_sample_cost')
                    # 本批列已由适配器校验并由本次运行拥有，不再重复构造校验模型。
                    value = _scalar_from_validated_column(column, index)
                    sample = _record_from_validated_fields(column.name, time, int(column.sequence[index]),
                        value, column.unit,self._refs[column.name],
                        column.values[index].item() if value.dtype is D.ENUM else None)
                    heapq.heappush(self._heap, (time, self._serial, sample))
                    self._serial += 1
                    self._maximum = time if self._maximum is None else max(time, self._maximum)
            if batch.watermark_ns is not None:
                self._flush(batch.watermark_ns, keep_last=True)
        except BaseException:
            self._failed = True
            raise
        finally:
            batch = sample = value = column = None

    def _flush(self, watermark, *, keep_last):
        """只交付完整组，费用在consumer返回后释放。参数: 进度/是否保末组。返回: None。异常: 原错。"""
        while self._heap and (watermark is None or self._heap[0][0] <= watermark):
            time = self._heap[0][0]
            if keep_last and time == self._maximum:
                return
            samples = group = None
            count = 0
            primary = None
            try:
                # 当前组至多为已付费样本数量，先覆盖列表/tuple引用再构造。
                _reserve_owned_ram(self, 4096 + len(self._heap)*32, '_work_cost')
                samples = []
                while self._heap and self._heap[0][0] == time:
                    samples.append(heapq.heappop(self._heap)[2])
                    count += 1
                group = DecodedTimeGroup(time, tuple(samples))
                self._consumer(group)
                self._last = time
            except BaseException as error:
                primary = error
                raise
            finally:
                samples = group = None
                try:
                    _release_owned_ram(self, count*8192, '_sample_cost')
                    _release_owned_ram(self, self._work_cost, '_work_cost')
                except BaseException as cleanup:
                    self._failed = True
                    if primary is None:
                        raise
                    primary.add_note('解析同刻组清理失败：'+type(cleanup).__name__)

    def finish(self):
        """调用方确认真实EOF及关闭后交最后组。参数: 无。返回: None。异常: 失败拒绝完成。"""
        if self._closed or self._failed:
            raise ResultClosedError('解析信号组不能完成')
        if self._finished:
            return
        try:
            self._flush(None, keep_last=False)
            self._finished = True
        except BaseException:
            self._failed = True
            raise

    def close(self):
        """丢待处理组并退款，不把提前close当EOF。参数: 无。返回: None。异常: 退款失败可重试。"""
        if self._closed:
            return
        self._failed = True
        self._heap = self._consumer = self._refs = None
        for slot in ('_work_cost', '_sample_cost', '_fixed_cost'):
            _release_owned_ram(self, getattr(self, slot), slot)
        self._closed = True
