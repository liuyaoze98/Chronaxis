"""约定来源的描述、分批读取和关闭接口，并检查跨批承诺。

SourceAdapter接收ReadRequest并产生SignalBatch；BatchValidator根据
SourceDescription检查会话、投影、类型、单位、时间顺序、序号和进度。
本模块不打开来源、不排序文件，也不计算业务事件。

校验器保存各列最近时间组的序号、来源最近时间、watermark_ns进度和
结束状态。进度承诺之后不能再接收小于或等于该时间的更新；失败时不推进
已有状态。状态大小取决于信号数量和当前组规模，执行层须将容器计入预算。
"""

# Mapping和Iterator表达公开协议，不接自由object占位。
from collections.abc import Iterator
# Protocol用于实际adapter结构契约，不进行全局注册或导入任务。
from typing import Protocol, runtime_checkable

# 公共来源模型已校验单批shape/质量/时间，跨批承诺在这里核对。
from .models import ReadRequest, SignalBatch, SourceDescription


class SourceClosedError(RuntimeError):
    """表示已经关闭的来源仍被请求描述或读取；重复close本身应安全。
    """


class SourceReadError(RuntimeError):
    """表示来源读取或批次协议失败；具体适配器负责附加位置并保留原异常链。
    """


@runtime_checkable
class SourceAdapter(Protocol):
    """约束已解码来源的公共接口，不管理实现的内部资源。

    describe返回声明，iter_batches按明确请求传送更新，close由实现释放资源。
    静态描述不应推进日志输入或加载DBC。此协议不保存实例状态，具体适配器
    负责活动生成器、句柄和关闭标记；同一来源的全部文件结束才报告source_eof。
    """

    def describe(self) -> SourceDescription:
        """返回来源描述与能力声明，不推进输入读取。

        参数:
            无。由实现使用当前来源配置和已有元数据。
        返回:
            SourceDescription。未知观测端点和不可用能力保留明确状态。
        异常:
            SourceClosedError: 来源已关闭。
            描述模型校验或实现的元数据错误由具体适配器报告。
        """
        # Protocol只声明方法，实际实现必须返回typed描述。
        ...

    def iter_batches(self, request: ReadRequest) -> Iterator[SignalBatch]:
        """按请求传送指定别名的已解码更新。

        参数:
            request (ReadRequest): 会话、别名投影、分析域和每批总样本上限。
        返回:
            Iterator[SignalBatch]。允许空批和同时间组跨批，整个来源结束时报告结束标记。
        异常:
            SourceClosedError、SourceReadError或请求与协议校验错误，由具体实现报告。
        边界:
            请求范围不授权读取下推或改变旧链调用行为。
        """
        # 接口不包含额外解码回调或读取下推。
        ...

    def close(self) -> None:
        """释放适配器持有的活动资源，保留用户输入文件。

        参数:
            无。具体实现关闭自己的生成器和句柄。
        返回:
            None。重复关闭应安全。
        异常:
            清理失败由实现报告；已有读取错误时应保留原错误及清理证据。
        """
        # 所有实际实现负责各自已打开的资源。
        ...


class BatchValidator:
    """为一次读取请求核对跨批身份、时间顺序和结束状态。

    description和request保存本请求声明，catalog按别名索引字段契约。
    watermark_ns记录已完整传送的时间进度，last_time_ns记录最近真实样本。
    pending保存每列最近时间组的序号集合；进度越过该组后释放集合。
    ended为True后不能再接收任何批次，包括空批。accept先在局部副本检查，
    全部通过才替换状态，因此失败批次不会污染已有进度。
    """

    def __init__(self, description: SourceDescription, request: ReadRequest) -> None:
        """为当前来源及请求建立独立的跨批校验状态。

        参数:
            description (SourceDescription): 当前来源的字段、类型、单位和观测声明。
            request (ReadRequest): 本次会话、信号别名和批次上限。
        返回:
            None。保存字段目录，并初始化时间、序号和结束状态；不读取来源。
        异常:
            TypeError: 输入不是规定的模型类型。
            ValueError: 请求别名在来源描述中不存在。
        """
        # 输入类型先验，不能从样本反推配置。
        if not isinstance(description, SourceDescription) or not isinstance(request, ReadRequest):
            # 描述和请求必须使用规定的类型化模型。
            raise TypeError('BatchValidator需要typed描述/请求')
        # catalog按本次绑定别名索引字段，不继承全局来源对象。
        catalog = {item.name: item for item in description.fields}
        # 所有请求必须在已知字段中，能力未知不猜测。
        if any(name not in catalog for name in request.signal_names):
            # 失败指出来源和具体投影。
            raise ValueError(f'{description.name}:未知signal_names')
        # 当前模型与请求不可变，后续只存本次状态。
        self.description, self.request, self.catalog = description, request, catalog
        # watermark是完整组的进度，初始尚未承诺。
        self.watermark_ns = None
        # 最近真实样本时间确保批次整体不会倒退。
        self.last_time_ns = None
        # 每个列的最近时间组/序号集合，用于跨批重复检查。
        self.pending = {}
        # EOF后即使空批也不能继续读。
        self.ended = False

    def accept(self, batch: SignalBatch) -> None:
        """检查一批的身份和进度，全部通过后才更新请求状态。

        参数:
            batch (SignalBatch): 已通过单批结构检查的批次。
        返回:
            None。更新最近时间、未完成组序号、进度承诺和来源结束标记。
        异常:
            ValueError: 批次类型或归属错误、超过样本上限、列契约变化、时间回退、
                重复观测、违反进度承诺或观测终点冲突；结束后任何批次也被拒绝。
        副作用:
            只在全部检查成功后改变本校验器；输入批次不被修改。
        边界:
            样本时间等于旧watermark_ns也被拒绝，因为该时间组已经承诺完整。
            真实点可以等于观测终点；分析开始前的保持样本仍可早于请求起点。
        """
        # 已结束的来源或错误批次类型都不能推进校验状态。
        if not isinstance(batch, SignalBatch) or self.ended:
            # EOF不是普通空batch，不能跨请求复用状态。
            raise ValueError(f'{self.description.name}:错误批次或EOF后继续')
        # 会话/来源与初始化契约完全一致。
        if batch.source != self.description.name or batch.session_id != self.request.session_id:
            # 值相同也不能借用他源/他会话定位。
            raise ValueError(f'{self.description.name}:批次归属冲突')
        # 所有series样本总数限额，而不是仅数不同时间点。
        if batch.sample_count > self.request.batch_rows:
            # 大同时间组应合法分批，不能放行超限。
            raise ValueError(f'{batch.source}:超过batch_rows样本总数')
        # watermark可重复但不能回退或撤销为None。
        if self.watermark_ns is not None and (batch.watermark_ns is None or batch.watermark_ns < self.watermark_ns):
            # 承诺不能因空批或下一文件而reset。
            raise ValueError(f'{batch.source}:watermark回退')
        # 在局部副本校验，失败不把坏批写进执行状态。
        pending = {name: (time, set(sequences)) for name, (time, sequences) in self.pending.items()}
        # 最大真实时间按上一批保存，空批不会清空它。
        latest = self.last_time_ns
        # 各列分别验证dtype/单位/原定位与投影。
        for name, column in batch.series.items():
            # 公共请求不接受额外列，避免绑定泄漏。
            if name not in self.request.signal_names:
                # 未知列不是忽略后继续的普通数据。
                raise ValueError(f'{batch.source}:非请求列{name}')
            # 描述中已经校验字段实际归属。
            definition = self.catalog[name]
            # 输出类型和单位不能在batch间静默改变。
            if column.dtype is not definition.dtype or column.unit != definition.unit or column.labels != definition.metadata.get('labels', ()) or any(ref.field != definition.field.field for ref in column.source_ref):
                # 表字段与别名分开，不从semantic_id猜定位。
                raise ValueError(f'{batch.source}:列{name}契约/原定位变化')
            # 单批数组已经有序；本列首点不能早于上一批任意列的真实末点。
            if len(column.time_ns) and self.last_time_ns is not None and int(column.time_ns[0]) < self.last_time_ns:
                # 不重排解析结果消除来源内乱序。
                raise ValueError(f'{batch.source}:跨batch时间回退')
            # 已完整的时间组不能再收到同刻更新。
            if len(column.time_ns) and self.watermark_ns is not None and int(column.time_ns[0]) <= self.watermark_ns:
                # 恰好等于旧进度也被拒绝，因为已承诺该时间及更早的更新完整传送。
                raise ValueError(f'{batch.source}:样本不晚于已承诺watermark')
            # 观测边界若有明确事实，真实点可以等于end但不能越界。
            if len(column.time_ns) and ((self.description.observation_start_ns is not None and int(column.time_ns[0]) < self.description.observation_start_ns) or (self.description.observation_end_ns is not None and int(column.time_ns[-1]) > self.description.observation_end_ns)):
                # domain不同于观测事实，前置保持样本仍可在request.start之前。
                raise ValueError(f'{batch.source}:样本超出来源观测声明')
            # 逐样本序号检查用于协议身份去重，不进行数值计算。
            for time_value, sequence_value in zip(column.time_ns, column.sequence):
                # 只转精确整数，禁止大时间先转float。
                time, sequence = int(time_value), int(sequence_value)
                # 新时间组替换该列pending，不保留无界历史身份集合。
                previous_time, sequences = pending.get(name, (None, set()))
                # 列时间推进后旧组不可能合法回来。
                if previous_time != time:
                    # 当前组的去重集合仍须计入执行层预算。
                    sequences = set()
                # 跨batch重复同一观测必须失败，不重复计入事件/面积。
                if sequence in sequences:
                    # 不是正常同时间不同原行。
                    raise ValueError(f'{batch.source}:同组重复sequence/{name}')
                # 仅登记当前组序号，其他列同原行可以各自存在。
                sequences.add(sequence)
                # 每列pending独立，异步列不互相覆盖。
                pending[name] = (time, sequences)
                # 保存整来源最新真实末点。
                latest = time if latest is None else max(latest, time)
        # 真实末点不能超过已知来源观测终点，即使当前批为空。
        if batch.observed_end_ns is not None and latest is not None and batch.observed_end_ns < latest:
            # 不用更早的终点悄悄截断已传输数据。
            raise ValueError(f'{batch.source}:observed_end早于真实末点')
        # 静态已声明终点与EOF实际观测必须保持相同事实。
        if batch.source_eof and self.description.observation_end_ns is not None and batch.observed_end_ns != self.description.observation_end_ns:
            # unknown描述不能在这里反向提升为verified。
            raise ValueError(f'{batch.source}:EOF观测终点与声明冲突')
        # 完整组以后不能再到达，立即释放其身份集合，不保留历史全量。
        pending = {name: state for name, state in pending.items() if batch.watermark_ns is None or state[0] > batch.watermark_ns}
        # 检查全部成功后才原子替换协议状态。
        self.pending, self.last_time_ns = pending, latest
        # 不从样本最大时间猜watermark，只采用adapter明确承诺。
        self.watermark_ns = batch.watermark_ns
        # EOF保证之后不再接收任意更新/空批。
        self.ended = batch.source_eof
