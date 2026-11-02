"""把三格式共用的已解码更新交给实时完整同刻组消费者，不写历史文件。

只归一化当前声明需要的字段；同刻组跨读取批/连续文件保持，看到下一个相关
时间后才交付上一组，EOF显式finish交付末组。每条待交付样本预付有限预算，
大同刻组超预算明确失败。跨来源调用方必须先按实际时间合并；本组件不重排
原文件、不解码DBC、不查询完整性证明，不把单个来源EOF当整个会话EOF。
"""

from ..core.models import SourceRef
from ..legacy.updates import LegacyDecodedUpdate
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from ..sources.can_spec import can_field_from_key
from ..sources.packing import pack_message_values
from .groups import DecodedTimeGroup
from .history import _metadata_bytes
from .record_sample import RecordSample
from .calculation_values import scalar_from_column
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q,SignalDType as D


class RawSignalGroups:
    """保存当前同刻的必要更新；组交付后立即释放，消费方另行承担最新值状态。"""

    def __init__(self, budget, definitions, session_id, consumer, *, backend='numpy',clock_only=()):
        """建立所需帧/信号索引和固定来源引用，不打开原始文件。

        参数: budget共享账本；definitions仅本次所需信号tuple；session_id会话；
            consumer同步借用完整DecodedTimeGroup；backend选择原归一化内核。
            clock_only只使用对应报文的更新时间，共用无效占位而不逐帧归一化无关值。
        返回: owner。异常: 配置、预算或取消；构造恢复句柄raw_groups_cleanup_owner。
        """
        if not isinstance(budget, ResourceBudget) or type(definitions) is not tuple or not callable(consumer):
            raise TypeError('实时原始信号组需要预算、定义tuple及消费者')
        if backend not in ('reference', 'numpy'):
            raise ValueError('实时原始信号组后端错误')
        self._budget, self._backend, self._session = budget, backend, session_id
        self._held_cost = self._fixed_cost = self._group_cost = self._work_cost = 0
        self._closed = self._closing = self._failed = self._finished = False
        self._consumer = self._fields = self._samples = None
        self._time = None
        self._clock_values=None
        self._clock_candidates={}
        self._automatic_names=set()
        try:
            _reserve_owned_ram(self, 65536 + 32 * _metadata_bytes((definitions, session_id)), '_fixed_cost')
            if len({item.name for item in definitions}) != len(definitions):
                raise ValueError('实时原始信号组不能重复声明别名')
            self._fields = {}
            if not set(clock_only)<={item.name for item in definitions}:
                raise ValueError('纯时钟字段必须属于当前组定义')
            self._clock_values={item.name:ScalarValue(None,item.dtype,False,Q.MISSING,
                tuple(dict.fromkeys(label for _,label in item.choices)) if item.dtype is D.ENUM else ())
                for item in definitions if item.name in clock_only}
            for definition in definitions:
                field = can_field_from_key(definition.field)
                # 自动类型需辨别“不是本帧字段”；显式类型的低层缺键仍表示缺值。
                if field.is_extended is None or field.is_fd is None:
                    self._automatic_names.add(definition.name)
                key = (definition.source, field.channel, field.frame_id, field.is_extended, field.is_fd)
                ref = SourceRef(session_id, definition.source, definition.field)
                self._fields.setdefault(key, []).append((definition, field.signal, ref))
            self._fields = {key: tuple(items) for key, items in self._fields.items()}
            self._samples, self._consumer = [], consumer
        except BaseException as exc:
            _cleanup_owner(self, exc, 'raw_groups_cleanup_owner', '实时原始信号组')
            raise
        finally:
            definitions = definition = field = ref = consumer = None

    def _require_open(self):
        """拒绝失败/关闭后的输入。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('实时原始信号组已失败或关闭')

    def configure_metadata(self, facts):
        """借用同次DBC候选识别纯时钟字段，不解码或读取额外记录。

        参数: facts为已加载字段事实。返回: None。异常: 定位结构错误。
        副作用: 仅保存当前纯时钟字段的有限候选，费用包含在定义固定预算中。
        """
        self._require_open()
        from ..legacy.records import field_from_dict
        # 同物理字段可能有多个时钟别名，按别名共享候选，不把后一别名覆盖掉。
        by_field={field_from_dict(dict(fact['locator'])).key: fact['dbc_frames']
                  for fact in facts if 'dbc_frames' in fact}
        self._clock_candidates={definition.name: by_field[definition.field]
            for items in self._fields.values() for definition, _, _ in items
            if definition.name in self._clock_values and definition.field in by_field}

    def consume(self, update):
        """接收一条已投影更新，仅所需帧参与时间检查与同刻归组。

        参数: update为LegacyDecodedUpdate；缺失的匹配字段仍生成无效更新覆盖旧值。
        返回: None。异常: 身份/时间回退、预算、归一化或消费者错误；失败后禁止finish。
        """
        self._require_open()
        if self._finished:
            raise ResultClosedError('实时原始信号组已经结束')
        column = sample = value = fields = None
        primary = None
        try:
            if not isinstance(update, LegacyDecodedUpdate) or update.source_ref.session_id != self._session:
                raise ValueError('更新不属于当前会话')
            # 每种选择器只有一个键；最多查询四种明确/省略类型组合，不扫描全部信号。
            prefix = (update.source, update.channel, update.frame_id)
            fields = tuple(item for extended in (update.is_extended, None) for fd in (update.is_fd, None)
                           for item in self._fields.get((*prefix, extended, fd), ()))
            # 投影会为属于本帧但解码失败的字段保留None；未出现的键才是另一帧的字段。
            # 纯时钟不要求解码值，使用初始化时已有的DBC候选判定所属帧。
            fields = tuple(item for item in fields if
                (item[0].name not in self._clock_values and
                    (item[0].name not in self._automatic_names or item[1] in update.values))
                or (item[0].name in self._clock_values and
                    (item[0].name not in self._clock_candidates or any(
                        extended == update.is_extended and (fd == update.is_fd or fd and not update.is_fd)
                        for extended, fd in self._clock_candidates[item[0].name]))))
            if not fields or update.is_remote or update.is_error:
                return
            if update.time_ns is None:
                raise ValueError('驱动表达式需要相关报文的实际时间')
            if self._time is not None and update.time_ns < self._time:
                raise ValueError('相关报文回退；多来源须先按实际时间有界归并')
            if self._time is not None and update.time_ns > self._time:
                self._flush()
            self._time = update.time_ns
            _reserve_owned_ram(self, 16384 + 4096 * len(fields), '_work_cost')
            for definition, name, ref in fields:
                # 本条缺字段同样归一化为无效；不保原值副本或逐条原帧定位。
                _reserve_owned_ram(self, 8192, '_group_cost')
                if definition.name in self._clock_values:
                    value=self._clock_values[definition.name]
                    array_value=False if definition.dtype is D.BOOL else 0. if definition.dtype is D.FLOAT64 else 0
                else:
                    column = pack_message_values(definition, (update.values.get(name),), self._backend)
                    value = scalar_from_column(column, 0)
                    array_value=column.values[0].item() if definition.dtype is D.ENUM else None
                sample = RecordSample(definition.name, update.time_ns, update.sequence,
                    value, definition.unit, ref, array_value if definition.dtype is D.ENUM else None)
                self._samples.append(sample)
        except BaseException as exc:
            primary = exc
            self._failed = True
            raise
        finally:
            column = sample = value = update = fields = None
            try:
                _release_owned_ram(self, self._work_cost, '_work_cost')
            except BaseException as cleanup:
                self._failed = True
                if primary is None:
                    raise
                primary.add_note('实时原始信号组临时费用清理失败：' + type(cleanup).__name__)

    def _flush(self):
        """同步借出完整组后释放本组，不保输出副本。参数: 无。返回: None。异常: 消费/清理错误。"""
        if not self._samples:
            return
        group = None
        try:
            group = DecodedTimeGroup(self._time, tuple(self._samples))
            self._consumer(group)
        finally:
            group = None
        self._samples.clear()
        _release_owned_ram(self, self._group_cost, '_group_cost')

    def finish(self):
        """所有输入EOF并成功关闭后交付末组，不创建末尾周期。参数: 无。返回: None。异常: 消费/清理错误。"""
        self._require_open()
        if self._finished:
            return
        try:
            self._flush()
            self._finished = True
        except BaseException:
            self._failed = True
            raise

    def close(self):
        """仅退自有费用，不替调用方完成剩余组。参数: 无。返回: None。异常: 释放失败可重试。"""
        if self._closed:
            return
        self._closing = True
        self._samples = self._fields = self._consumer = self._clock_values = None
        self._clock_candidates={}
        self._automatic_names.clear()
        _release_owned_ram(self, self._work_cost, '_work_cost')
        _release_owned_ram(self, self._group_cost, '_group_cost')
        _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        self._closed = True
