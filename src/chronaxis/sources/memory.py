"""把调用者已经提供的内存信号按有限批次交给分析层。

输入是冻结的SourceSpec、当前会话名称和SignalDefinition信号定义。
构造时检查来源归属与字段是否存在；describe只返回这些内存声明。
iter_batches按原行顺序取得已解码值，调用选定的归一化后端，输出SignalBatch。
这里没有日志读取、DBC解码或全历史保持序列的构建。

batch_rows限制所有信号列的样本总数，同一时间的更新可以分在多批。
watermark_ns表示已经完整传送的时间进度：后续不会再出现小于或等于
该坐标的更新。只有看见更晚原行或整个来源结束，才能推进这个承诺。
source_eof只在整个内存来源结束时为True，不把普通分批当作来源结束。

请求时间范围不用于裁剪原行，分析开始前的保持样本仍会传送。
close关闭活动生成器并拒绝后续操作，保留原输入。各次请求的缓冲和
跨批校验状态独立；原输入可以是全量内存数据，有限批次不代表它已释放。
"""

# Iterator表达真实流式接口，生成器持有最多一个有限原批次。
from collections.abc import Iterator
# 转换声明只作用于已解码值。
from ..core.binding import SignalDefinition
# 内存模型是已经验收的显式输入，不重建旧链。
from ..core.models import SourceRef, SourceSpec
# 设备/来源不从路径猜测，当前会话另明确验证。
from ..core.validation import require_identifier
# offset保持精确整数，不靠float时间。
from ..timebase.conversion import checked_add_ns
# 公共输出使用已定义的来源描述、信号列和批次模型。
from .models import ReadRequest, SignalBatch, SourceCapabilities, SourceDescription
# 静态字段身份与CSV使用同一描述协议，不额外扫描文件。
from .descriptions import describe_fields, source_timebase_identity
# 两后端归一化接线，不构造全历史SignalBindings。
from .packing import pack_decoded
# 生命周期错误与批次协议独立于业务事件。
from .protocol import BatchValidator, SourceClosedError, SourceReadError


class MemorySourceAdapter:
    """按原顺序传送一个内存来源的已解码字段。

    source保存只读原行，session_id标明所属会话，signals保存字段到别名的
    显式转换，backend选择reference标量实现或numpy数组实现。
    closed记录实例是否关闭，active登记本实例创建的请求生成器。
    每次读取另建缓冲和BatchValidator，不继承其他请求的信号值或进度。
    本类没有文件句柄；close释放生成器引用，不删除source中的原行。
    """

    def __init__(self, source: SourceSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str = 'numpy', clock_only=(), retain_original=True) -> None:
        """检查内存来源与信号定义，建立实例的读取生命周期。

        参数:
            source (SourceSpec): 已冻结的原行、时钟和偏移声明。
            session_id (str): 本来源所属的明确会话名称。
            signals (tuple[SignalDefinition, ...]): 仅属于source的信号定义，别名须唯一。
            backend (str): 默认'numpy'；也接受'reference'，不自动回退。
            clock_only: 只取更新时间的别名，不访问这些字段的数值。
            retain_original: 默认True保留旧诊断；False从生成处省去原值副本。
        返回:
            None。保存输入定义，并初始化关闭状态和活动请求集合。
        异常:
            TypeError: 来源或信号容器类型错误，或backend不受支持。
            ValueError: 会话名称非法、信号归属或别名冲突，或非空来源缺少声明字段。
        副作用:
            遍历已有原行核对字段；不修改输入，也不预先归一化全部历史。
        """
        # 不接受无类型配置，I/O plan层后续负责解析。
        if not isinstance(source, SourceSpec) or not isinstance(signals, tuple) or backend not in ('reference', 'numpy'):
            # 不静默切换数值后端。
            raise TypeError('memory adapter需要SourceSpec/signals tuple/backend')
        # 当前会话不是上一个请求的隐式状态。
        require_identifier(session_id, 'adapter.session_id')
        # 只允许绑定当前来源，重复别名禁止。
        if any(not isinstance(item, SignalDefinition) or item.source != source.name for item in signals) or len({item.name for item in signals}) != len(signals):
            # 来源投影不能借用另一个任务。
            raise ValueError('memory signals来源/名称冲突')
        if type(retain_original) is not bool or not set(clock_only)<={item.name for item in signals}:
            raise ValueError('纯时钟字段必须是当前投影，原值保留需要bool')
        self._clock_only,self._retain_original=frozenset(clock_only),retain_original
        # 字段存在性在已给memory上核实，空来源允许声明无观测。
        fields = {key for row in source.rows for key in row.values} if signals else set()
        # 非空输入缺失整个原字段属于绑定错误，单行不更新仍合法。
        if source.rows and any(item.field not in fields for item in signals):
            # 不把无法定位字段变成全未知正常任务。
            raise ValueError('memory字段无法定位')
        # 共享只读原输入；输出列另行分配，避免调用者修改原数组影响批次。
        self.source, self.session_id, self.signals, self.backend = source, session_id, signals, backend
        # 关闭状态只属于此实例，不使用全局adapter缓存。
        self.closed = False
        # 活跃生成器用于close时及时释放本批局部容器。
        self.active = set()

    def _ensure_open(self) -> None:
        """检查生命周期，关闭后连静态describe也不接受。

        参数: 无额外参数；读取closed。
        返回: None；开放时没有副作用。
        异常: SourceClosedError包含来源名称。
        """
        # 已close来源不能被复用来延续另一段任务。
        if self.closed:
            # 重复close仍在close自身处理为安全。
            raise SourceClosedError(f'{self.source.name}:source已关闭')

    def describe(self) -> SourceDescription:
        """返回已有内存声明及字段转换信息，保持未知观测边界。

        参数:
            无。读取source和signals，不取得新的样本。
        返回:
            SourceDescription。明确声明的观测端点加上来源偏移，未知端点保留None；
            metadata_status为'declared'，字段元数据不被自动提升为核实结果。
        异常:
            SourceClosedError: 实例已经关闭。
            TypeError或ValueError: 字段描述不符合公共模型要求。
            OverflowError: 端点加偏移后超出整数纳秒范围。
        副作用:
            无文件读取，不从投影样本的首末时间猜测完整观测范围。
        """
        # 静态查询同样尊重实例生命周期。
        self._ensure_open()
        # 转换身份保留输入单位/scale/offset，semantic只是可选声明。
        fields = describe_fields(self.source.name, self.signals,
                                 {'offset_ns': self.source.offset_ns,
                                  'source_timebase_sha256': source_timebase_identity(self.source.timebase, self.source.offset_ns)})
        # 只把明确声明的来源边界映射到当前会话坐标，不补周期。
        start = None if self.source.observation_start_ns is None else checked_add_ns(self.source.observation_start_ns, self.source.offset_ns)
        # start/end可各自unknown，不从投影首末猜完整范围。
        end = None if self.source.observation_end_ns is None else checked_add_ns(self.source.observation_end_ns, self.source.offset_ns)
        # 已解析memory可以重复遍历，但不授权旧报文重扫。
        return SourceDescription(self.source.name, fields, self.source.timebase.timebase_id, start, end,
                                 SourceCapabilities(True, False, True, False, ('declared memory质量/原值',), ('无原始报文导出',)), metadata_status='declared')

    def iter_batches(self, request: ReadRequest) -> Iterator[SignalBatch]:
        """为一次读取请求创建独立生成器，并登记其清理责任。

        参数:
            request (ReadRequest): 当前会话、请求信号别名、分析范围及batch_rows上限。
        返回:
            Iterator[SignalBatch]。每批所有列的样本总数不超过batch_rows；
            最后一批标记整个来源结束，允许没有样本。
        异常:
            SourceClosedError: 实例已经关闭。
            ValueError: 请求类型或会话不符，或请求了描述中没有的别名。
            SourceReadError: 实际迭代时读取或批次校验失败，原异常保存在异常链中。
        副作用:
            立即检查请求并登记生成器；取得样本的工作在迭代时执行。
        """
        # 非生成器入口立即检查已关闭状态，避免延迟到next才失败。
        self._ensure_open()
        # 请求类型和会话显式一致。
        if not isinstance(request, ReadRequest) or request.session_id != self.session_id:
            # 不能悄悄把当前来源搬到其他会话。
            raise ValueError(f'{self.source.name}:请求会话错误')
        # 初始化跨batch验证，未知列在读取前拒绝。
        validator = BatchValidator(self.describe(), request)
        # wrapper保证正常结束/中止都移除自身，不用反射定位活动frame。
        def iterate() -> Iterator[SignalBatch]:
            """转发本次请求的批次，并在退出时移除活动登记。

            参数:
                无。闭包使用本次request、validator及iterator引用。
            返回:
                每次产生一个SignalBatch，顺序和进度与内部生成器一致。
            异常:
                内部读取或协议异常原样传播；finally仅移除本请求的登记。
            """
            # try/finally负责正常/异常/显式close生命周期。
            try:
                # 直接转发，不增加采样或改动watermark。
                yield from self._iterate(request, validator)
            finally:
                # 集合discard幂等，保留其他独立请求。
                self.active.discard(iterator)
        # 私有generator只持有有限pending样本，不预建全历史输出。
        iterator = iterate()
        # close可以统一释放所有已创建的活动请求。
        self.active.add(iterator)
        # 返回负责本请求读取与清理的生成器。
        return iterator

    def _iterate(self, request: ReadRequest, validator: BatchValidator) -> Iterator[SignalBatch]:
        """逐行传送更新，完整时间组结束后才推进跨批进度。

        参数:
            request (ReadRequest): 本次请求；signal_names确定列顺序和样本计数。
            validator (BatchValidator): 本请求独立的来源、身份和进度校验状态。
        返回:
            每次产生SignalBatch；最后一批source_eof为True。
        异常:
            SourceReadError: 转换、生命周期或协议校验失败，保留来源名和原异常链。
        处理流程:
            按原行加偏移后收集请求字段，缓冲满时先发布已有样本。
            字段未出现在原行中表示没有更新；显式None则是覆盖旧值的缺失更新。
            更晚原行证明上一时间组完整，整个来源耗尽后确认最后一组。
            退出时清空本次缓冲，不修改输入或已经返回的独立数组。
        """
        # 按调用者明确投影顺序组织同一原行的信号样本。
        selected = tuple(next(item for item in self.signals if item.name == name) for name in request.signal_names)
        # pending是本批原生记录，尚未创建数值列，最多batch_rows条。
        pending, count, watermark, previous = {}, 0, None, None
        # try/finally保证正常或close/异常时释放活动登记。
        try:
            # 原rows顺序只读，不按时间重新排序或插入假样本。
            for row in self.source.rows:
                # close中止之后不能继续工作。
                self._ensure_open()
                # 原坐标按声明offset映射，仍为精确纳秒。
                time = checked_add_ns(row.time_ns, self.source.offset_ns)
                # 只有下一原行更晚，上一时间组才真正完整。
                if previous is not None and time > previous:
                    # 进度允许跨无投影更新的原行，区别于观测范围。
                    watermark = previous
                # 一行可多个别名，同刻超大组可在别名之间分批。
                for definition in selected:
                    # 缺字段表示没有更新，而显式None仍传送MISSING覆盖。
                    if definition.field not in row.values:
                        # 不用缺列伪造新无效样本。
                        continue
                    # 新记录不能令当前批超限；先发布已取得有限pending。
                    if count == request.batch_rows:
                        # 若新原行更晚，watermark可以包含刚完成的上一组。
                        batch = self._make_batch(pending, watermark, False, None)
                        # 独立协议校验完成后才交给消费者。
                        validator.accept(batch)
                        # 返回后消费者持有owned列，下一批清空原记录缓冲。
                        yield batch
                        # 只清空本批传输缓冲；时间进度和来源结束状态继续保留。
                        pending, count = {}, 0
                    # 保留原行的稳定sequence序号，区分同时间的不同观测。
                    pending.setdefault(definition.name, []).append((time, row.sequence,
                        None if definition.name in self._clock_only else row.values[definition.field]))
                    # 行数上限按所有列样本和，不按宽表行计。
                    count += 1
                # 来源所有原行都推进时间，即使该行没有投影字段。
                previous = time
            # 整个配置来源已耗尽，最后真实时间组完整。
            watermark = previous if previous is not None else watermark
            # 已声明来源终点保留；未知只报告实际最后原行，无额外周期。
            observed_end = checked_add_ns(self.source.observation_end_ns, self.source.offset_ns) if self.source.observation_end_ns is not None else previous
            # 空来源/空投影仍有合法EOF，观测未知可以None。
            batch = self._make_batch(pending, watermark, True, observed_end)
            # 不让终点/声明矛盾隐藏到公共执行层。
            validator.accept(batch)
            # 仅整个来源结束才发送EOF。
            yield batch
        except Exception as error:
            # 读取/协议根因带来源名报告，GeneratorExit不被包装。
            raise SourceReadError(f'{self.source.name}:memory批次失败：{error}') from error
        finally:
            # 释放最后的原记录缓冲，不删除输入或改动外部已返回owned列。
            pending.clear()

    def _make_batch(self, pending, watermark: int | None, eof: bool, observed_end: int | None) -> SignalBatch:
        """将当前缓冲中的已解码原值归一化，生成独立信号列。

        参数:
            pending (dict): 别名对应的(time_ns, sequence, 原值)记录列表。
            watermark (int | None): 已完整传送的时间组坐标，单位为纳秒。
            eof (bool): 是否已经耗尽整个配置来源。
            observed_end (int | None): 已知观测终点，单位为纳秒；未知时为None。
        返回:
            SignalBatch。各列保留本会话、来源及原字段引用；转换对每值应用一次。
        异常:
            TypeError、ValueError或OverflowError: 归一化或列模型校验失败。
        副作用:
            分配独立数组，不保留上一批的值，也不修改原行。
        """
        # 当前定义按显式别名映射，不继承上一批值。
        definitions = {item.name: item for item in self.signals}
        # 各列独立异步，不拼成混dtype稠密宽表。
        columns = {name: pack_decoded(definitions[name], tuple(records), SourceRef(self.session_id, self.source.name, definitions[name].field), self.backend,
            retain_original=self._retain_original,clock_only=name in self._clock_only) for name, records in pending.items()}
        # batch模型严格保存会话/进度/观测事实。
        return SignalBatch(self.source.name, self.session_id, columns, watermark, eof, observed_end)

    def close(self) -> None:
        """关闭本实例的全部活动生成器，保留原内存输入。

        参数:
            无。使用closed状态和active生成器集合。
        返回:
            None。重复调用直接返回；后续描述和读取操作被拒绝。
        异常:
            活动生成器的清理异常会传播。
        副作用:
            先标记关闭，再关闭活动生成器并清空登记；没有文件删除操作。
        """
        # 已close不重复清理或改变输入。
        if self.closed:
            # 幂等生命周期供AnalysisRunner正常/异常共用。
            return
        # 先阻止后续调用，再释放当前请求资源。
        self.closed = True
        # 关闭副本集合，生成器finally可能移除自身登记。
        for iterator in tuple(self.active):
            # generator.close会执行finally并释放本批局部输入。
            iterator.close()
        # 清除所有已经完成或尚未启动的请求引用。
        self.active.clear()
