"""在既有内存适配器之外预留输入、批次与协议状态预算。

输入SourceSpec本来已完整存在于调用方内存；封装构造前核算它和信号声明，
不声称控制过去的分配或全进程RSS。输出为既有适配器实际SignalBatch，
归一化次数、backend、分批、原顺序、watermark/EOF和异常原因不改变。
每请求预留最坏两个交接批次及来源pending状态，再创建/推进内部生成器；
NumPy字符串按最大原宽度×N核算Unicode数组/临时副本，不能只计原字符串总长。
超限明确失败，不偷偷减小batch_rows、切换后端或丢样本。所有预算至EOF/close释放，
外部长期保存owned批次不在本封装内部预算保证内；不读取CSV、旧日志或DBC。
"""

# 原适配器和结构模型负责输入契约，资源账本仅控制新执行层开销。
from collections.abc import Iterator
from ..core.binding import SignalDefinition
from ..core.models import SourceSpec
from ..results.budget import ResourceBudget
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.memory import MemorySourceAdapter
from ..sources.models import ReadRequest, SignalBatch, SourceDescription
from ..sources.protocol import SourceClosedError
from .history import _metadata_bytes


class BudgetedMemorySourceAdapter:
    """共享一个输入预留，为各读取请求保留独立批次/协议最坏预算。

adapter只在预留成功后建立；info存每别名实际投影总数与最大原字符串字符数。
active登记活动请求，close尝试关闭全部并释放输入引用，原SourceSpec不修改。
_uninstalled_read保构造或登记未返回的真实请求；_closing先拒绝新读，closed仅在
所有子请求、原适配器及本层_input_cost实际释放后成立。
"""

    def __init__(self, budget: ResourceBudget, source: SourceSpec, session_id: str,
                 signals: tuple[SignalDefinition, ...], *, backend: str = 'numpy', clock_only=(), retain_original=True):
        """核算已有完整输入后建立原适配器，不提前生成数组。

        参数: budget为共享账本；source/session_id/signals/backend与既有内存入口相同。
            clock_only只取时间；retain_original=False不生成原值列，默认仍保留旧行为。
        返回: 新封装。异常: 配置/预算/原适配器初始化原错；持续清理失败附
            memory_source_cleanup_owner，恢复后从该真实owner重试close。
        """
        if not isinstance(budget, ResourceBudget) or not isinstance(source, SourceSpec) or type(signals) is not tuple or any(not isinstance(item, SignalDefinition) for item in signals):
            raise TypeError('预算内存来源需要账本/SourceSpec/typed信号tuple')
        # 所有保留输入和固定描述保守计数，未知对象不参与任意序列化。
        cost = 16384 + _metadata_bytes((source, session_id, signals)) * 16
        self.budget = self._budget = budget
        self.closed = self._closing = False
        self._input_cost = self._held_cost = 0
        self._adapter = self._uninstalled_read = None
        self.active: set[_BudgetedBatches] = set()
        self.info = {}
        try:
            # 直接申请返回途中取消也由同一槽登记；不靠子调用后的共享余额补账。
            _reserve_owned_ram(self, cost, '_input_cost')
            self._adapter = MemorySourceAdapter(source, session_id, signals, backend=backend,
                clock_only=clock_only,retain_original=retain_original)
            self.info = {item.name: [0, 0] for item in signals}
            # 只遍历已经提供的memory原行，不重新读取旧输入或进行归一化。
            for row in source.rows if signals else ():
                for item in signals:
                    if item.field in row.values:
                        self.info[item.name][0] += 1
                        value = None if item.name in clock_only else row.values[item.field]
                        if type(value) is str:
                            self.info[item.name][1] = max(self.info[item.name][1], len(value))
        except BaseException as exc:
            _cleanup_owner(self, exc, 'memory_source_cleanup_owner', '预算内存来源构造')
            raise

    def _ensure_open(self) -> None:
        """拒绝已关闭来源，不以空批掩盖错误。

        参数: 无。返回: None。异常: SourceClosedError为已关闭。
        """
        if self.closed or self._closing:
            raise SourceClosedError('预算内存来源已关闭或正在清理')

    def describe(self) -> SourceDescription:
        """直接返回原适配器静态描述，不提升来源能力或观测证据状态。

        参数: 无。返回: SourceDescription。异常: 关闭/原描述错误传播。
        """
        self._ensure_open()
        return self._adapter.describe()

    def _request_cost(self, request: ReadRequest) -> int:
        """计算一个读取请求在全部next期间持有的最坏预留。

        参数: request为当前会话/投影/批次上限。返回: 保守bytes，非RSS。
        异常: ValueError为请求会话/别名错误，其他预算错误由申请点报告。
        """
        self._ensure_open()
        if not isinstance(request, ReadRequest) or request.session_id != self._adapter.session_id or any(name not in self.info for name in request.signal_names):
            raise ValueError('预算内存来源请求会话/投影错误')
        total = sum(self.info[name][0] for name in request.signal_names)
        size = min(total, request.batch_rows)
        max_chars = max((self.info[name][1] for name in request.signal_names), default=0)
        # nbytes至多time/sequence各8、values8、valid1、quality2；4096覆盖复制、装箱/分组。
        per_batch = 65536 + len(request.signal_names) * 8192 + size * 4096
        if self._adapter.backend == 'numpy':
            # 原str可能形成(N,) UTF32定宽列，八倍覆盖原列/转换及模型验证临时副本。
            per_batch += size * max_chars * 4 * 8
        # yield时原生成器仍保留当前批，next构造下一批存在交接重叠，不只申请一套数组。
        # 协议pending最坏保留全部原投影身份并复制set；memory总样本数是已知有限事实。
        return per_batch * 2 + total * 512 + len(request.signal_names) * 2048

    def iter_batches(self, request: ReadRequest) -> Iterator[SignalBatch]:
        """预留整次请求的最坏缓冲/状态，再创建实际批次生成器。

        参数: request为既有读取请求，不改变batch_rows。返回: 独立预算游标。
        异常: 请求/预算/原来源错误传播；超限在数组归一化之前失败，持续清理
            失败附memory_read_cleanup_owner，来源也保留未返回read槽。
        """
        cost = self._request_cost(request)
        if self._uninstalled_read is not None:
            raise SourceClosedError('预算内存来源尚有未返回请求待清理')
        try:
            iterator = _BudgetedBatches(self, request, cost)
        except BaseException as exc:
            # 构造未返回的真实read先归来源，不能只保费用而遗失原生成器。
            self._uninstalled_read = getattr(exc, 'memory_read_cleanup_owner', None)
            raise
        self._uninstalled_read = iterator
        try:
            self.active.add(iterator)
        except BaseException as exc:
            # add可能在登记前或后抛错；只关当前read，原注册错误不被close取消替代。
            _cleanup_owner(iterator, exc, 'memory_read_cleanup_owner', '预算内存请求登记')
            raise
        self._uninstalled_read = None
        return iterator

    def close(self) -> None:
        """关闭所有请求及原适配器，释放本封装预留并保留调用方原输入。

        参数: 无。返回: None，幂等。异常: 首个原关闭错误附memory_source_cleanup_owner；
            其他独立read也尝试关闭，子责任未完成时保留来源合同与全部未释放槽。
        """
        if self.closed:
            return
        self._closing = True
        try:
            first_error = None
            # 未登记read仍属于本来源；显式槽与活动set可指向同对象，close幂等。
            if self._uninstalled_read is not None:
                try:
                    self._uninstalled_read.close()
                except BaseException as exc:
                    first_error = exc
            for iterator in tuple(self.active):
                try:
                    iterator.close()
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
                    else:
                        first_error.add_note(f'其他内存请求关闭失败: {type(exc).__name__}')
            if first_error is not None:
                raise first_error
            if self._adapter is not None:
                self._adapter.close()
                self._adapter = None
            # 子生成器与原来源全关后才丢输入引用；固定费逐笔确认释放前后取消。
            self.info.clear()
            _release_owned_ram(self, self._input_cost, '_input_cost')
            if self._held_cost == 0:
                self.closed = True
        except BaseException as exc:
            exc.memory_source_cleanup_owner = self
            raise


class _BudgetedBatches:
    """持有一请求的预留/原生成器/当前批，EOF或close时抵销一次预留。"""

    def __init__(self, owner: BudgetedMemorySourceAdapter, request: ReadRequest, cost: int):
        """先申请再创建原请求，构造失败不保留请求状态。

        参数: owner为预算来源；request为原请求；cost为最坏预留。返回: 独立游标。
        异常: 预算或原请求初始化原错，持续清理失败附memory_read_cleanup_owner；
            未实际入账不抵销，返回途中取消仍登记原cost槽。
        """
        self.owner, self.closed, self.current = owner, False, None
        self._budget, self._held_cost, self.cost = owner.budget, 0, 0
        self.iterator = None
        self._closing = False
        try:
            # 先装恢复槽再申请；旧最坏整次请求费用公式保持原数值。
            _reserve_owned_ram(self, cost, 'cost')
            self.iterator = owner._adapter.iter_batches(request)
        except BaseException as exc:
            _cleanup_owner(self, exc, 'memory_read_cleanup_owner', '预算内存请求构造')
            raise

    def __iter__(self) -> '_BudgetedBatches':
        """返回本独立游标。

        参数: 无。返回: self。异常: 无。
        """
        return self

    def __next__(self) -> SignalBatch:
        """在整次预留覆盖下推进原适配器，不重复归一化或改进度。

        参数: 无。返回: 原适配器实际批次。异常: EOF/关闭/原来源错误，故障清理保留根因。
        """
        self.owner._ensure_open()
        if self.closed:
            raise StopIteration
        if self._closing:
            raise SourceClosedError('预算内存请求正在清理')
        try:
            self.current = next(self.iterator)
            return self.current
        except StopIteration:
            # 真实耗尽后关闭失败必须传播该失败，不能用StopIteration伪报正常完成。
            self.close()
            raise
        except BaseException as exc:
            _cleanup_owner(self, exc, 'memory_read_cleanup_owner', '预算内存请求推进')
            raise

    def close(self) -> None:
        """关闭本请求原生成器，释放当前批引用和最坏预留，其他请求保持独立。

        参数: 无。返回: None，幂等。异常: 原生成器或释放错误附memory_read_cleanup_owner；
            原生成器未成功关闭时保留原对象和费用，其他请求保持独立。
        """
        if self.closed:
            return
        self._closing = True
        try:
            if self.iterator is not None:
                self.iterator.close()
                # 未开始生成器close不执行finally，只解除本read的原登记，不动平行read。
                if self.owner._adapter is not None:
                    self.owner._adapter.active.discard(self.iterator)
            self.current = self.iterator = None
            _release_owned_ram(self, self.cost, 'cost')
            # 费用真正抵销后才从父解除，释放后取消可重试而不会重复扣账。
            self.owner.active.discard(self)
            if self.owner._uninstalled_read is self:
                self.owner._uninstalled_read = None
            self.closed = True
        except BaseException as exc:
            exc.memory_read_cleanup_owner = self
            raise
