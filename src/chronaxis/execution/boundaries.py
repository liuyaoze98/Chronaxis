"""从当前保持状态选择下一分析边界，合并同刻原因而不推进事件状态。

输入为已经登记实际解码表达式的ExpressionQueries、已处理的整数纳秒游标、
下一完整更新组时刻和当前未确认duration的冻结截止快照。输出须关闭的
BoundaryResult，只保存一个时刻、全部并列原因以及绑定和表达式身份。
查询先预留依赖、规则、来源及字符串空间，再扫描当前TTL、依赖来源EOF与
domain结束；每次重新计算，不积累过期timer，也不保存样本或完整更新组。
原因按固定顺序展示，该顺序不代表消费顺序；本模块不求值表达式、不提交
state、不推进Detector，不据EOF原因决定事件的closed/interrupted/truncated。
调用方负责先处理domain起点；这里不以start-1初始化，因此INT64_MIN可用。
owner只关闭自有结果和固定申请，上游关闭后已有结果仍独立可读。RAM为新
分析层保守计账，不代表整个进程RSS或外部另存引用的强制回收。device_label: home。
"""

# 冻结边界协议只使用标准模型；保持和表达式资源由调用方负责关闭。
from dataclasses import dataclass
from sys import getsizeof
from types import MappingProxyType

from ..core.expression import CompiledExpression
from ..core.models import Interval
from ..core.validation import require_identifier
from ..results.errors import ResultClosedError
from ..timebase.conversion import require_int64_ns
from .expressions import ExpressionQueries


# 这里只规定可重复展示的排序，不编码实际更新、TTL或EOF的执行优先级。
_REASON_ORDER = MappingProxyType({
    'ttl': 0, 'duration': 1, 'update': 2, 'source_eof': 3, 'domain_end': 4,
})


def _require_native_ns(value, field):
    """要求原生int的精确有符号64位纳秒，拒绝隐式类型转换。

    参数:
        value: 待检查坐标，必须是原生int，不能为bool或NumPy整数标量。
        field: 错误定位字段名称。
    返回:
        原int坐标，单位为纳秒，不舍入或取模。
    异常:
        TypeError: 输入不是原生int。
        TimeOverflowError: 坐标超出有符号64位范围。
    副作用:
        无，不读取状态或申请查询预算。
    """
    # 通用时间转换允许Integral；本内部快照接口明确采用原生int，先收紧类型。
    if type(value) is not int:
        raise TypeError(f'{field}需要原生int纳秒')
    # 范围检查复用整数协议，超界直接拒绝，不能生成回绕后的早期截止。
    return require_int64_ns(value, field)


@dataclass(frozen=True)
class RuleDeadline:
    """保存调用方当前未确认duration的一份截止快照，不持有Detector。

    rule_id是当前规则的简单标识，time_ns是原生int64纳秒的精确截止时刻。
    快照不证明某个候选仍存在；调用方须在每次规则或信号更新后重新取得快照。
    本模型不相加duration，不生成零门槛timer，也不改变规则配置或检测状态。
    """

    rule_id: str  # 当前duration规则标识，不能用表达式文本替代身份。
    time_ns: int  # 已检查的原生int64纳秒；查询再检查必须严格晚于游标。

    def __post_init__(self):
        """校验冻结规则标识和整数截止，不读取候选状态。

        参数:
            无显式参数，读取rule_id与time_ns。
        返回:
            None，字段保持原值，不隐式改名或转换时间类型。
        异常:
            TypeError: 标识不是原生str或时间不是原生int。
            ValueError: 标识为空、含点号、关键字或保留名称。
            TimeOverflowError: 时间超出int64。
        副作用:
            无，不注册timer或打开资源。
        """
        # 固定字符串不携带自定义比较行为；项目标识规则保持大小写和完整原文。
        if type(self.rule_id) is not str:
            raise TypeError('deadline.rule_id需要原生str')
        require_identifier(self.rule_id, 'deadline.rule_id')
        # 超int64直接拒绝，不返回饱和值；合法但超过domain的截止由query_next忽略。
        _require_native_ns(self.time_ns, 'deadline.time_ns')


@dataclass(frozen=True)
class BoundaryReason:
    """描述选中时刻的一项事实原因，不能直接解释为事件结束状态。

    ttl的target为信号别名，duration为规则标识，source_eof为来源标识；
    update与domain_end的target固定为空串，不保存更新组或会话对象。
    所有字段冻结；相同reason_type的多个目标可同时出现，同来源EOF只输出一次。
    """

    reason_type: str  # ttl/duration/update/source_eof/domain_end中的一种。
    target: str  # 目标简单标识，update与domain_end固定为空串。

    def __post_init__(self):
        """校验原因种类及对应目标格式，不推断数据有效性。

        参数:
            无显式参数，读取reason_type与target。
        返回:
            None，保留固定协议中的字符串。
        异常:
            TypeError: reason_type或target不是原生str。
            ValueError: 原因未注册、标识不合法或无目标原因携带非空target。
        副作用:
            无，不求值条件或改变来源状态。
        """
        # 原因分派仅接受固定文本，不执行任意对象或扩展字符串协议。
        if type(self.reason_type) is not str or type(self.target) is not str:
            raise TypeError('边界原因kind/target需要原生str')
        if self.reason_type not in _REASON_ORDER:
            raise ValueError('边界原因kind未注册')
        # 三种有目标原因使用项目简单标识规则，避免混入字段文本或表达式路径。
        if self.reason_type in ('ttl', 'duration', 'source_eof'):
            require_identifier(self.target, 'boundary.target')
        # 更新原因只证明下一完整组同刻，不用字符串冒充尚未消费的组对象。
        elif self.target != '':
            raise ValueError('update/domain_end的target必须为空串')


def _reason_key(reason):
    """提供原因展示顺序，不改变时间或状态消费顺序。

    参数:
        reason: 已校验BoundaryReason。
    返回:
        (种类序号, target)，同种类按保留大小写的目标字典序排列。
    异常:
        KeyError: 内部原因种类与固定协议不一致。
    副作用:
        无，只作为当前查询中已预留排序空间的key函数。
    """
    # 固定种类顺序仅为了两个后端和不同输入排列得到相同可检查输出。
    return _REASON_ORDER[reason.reason_type], reason.target


class BoundaryResult:
    """持有单一边界的独立预算快照，关闭后拒绝读取内容。

    time、原因tuple和两个身份不借用上游可变状态；上游资源关闭不清除此结果。
    owner登记全部存活结果并负责最终关闭。调用方若另存已取得的原因或身份引用，
    须自行负责关闭以后仍保留的外部引用，不把释放预算解释为强制销毁对象。
    """

    def __init__(self, owner, cost, time_ns, reasons, binding_identity, compiled_identity):
        """在已预留空间中包装边界事实，不复制样本或重新扫描TTL。

        参数:
            owner: 本结果所属BoundaryQueries。
            cost: 本查询成功申请的非负字节金额。
            time_ns: 已选中的原生int64纳秒时刻。
            reasons: 已校验、已排序的BoundaryReason tuple。
            binding_identity、compiled_identity: 当前实际绑定与登记表达式的身份字符串。
        返回:
            新BoundaryResult，待owner登记后交给调用方。
        异常:
            MemoryError: 构造分配失败，由查询完整抵销申请。
        副作用:
            只建立结果自有字段；不追加owner登记或改动caller资源。
        """
        # 已构造的冻结事实在完整申请中移交；两个身份是字符串，不保留compiled对象。
        self._owner, self._cost, self._closed = owner, cost, False
        self._time, self._reasons = time_ns, reasons
        self._binding_identity, self._compiled_identity = binding_identity, compiled_identity

    def _ensure_open(self):
        """拒绝关闭后读取，已有结果不再检查上游生命周期。

        参数:
            无。
        返回:
            None，打开结果可继续读取独立快照。
        异常:
            ResultClosedError: 本结果已关闭。
        """
        # 本结果拥有独立申请；caller关闭不会使仍存活的快照提前失效。
        if self._closed:
            raise ResultClosedError('下一边界结果已关闭')

    @property
    def closed(self):
        """读取本结果是否关闭。

        参数:
            无。
        返回:
            bool；关闭后仍可检查此状态。
        异常:
            无。
        """
        # 生命周期状态不需要访问已被清理的边界内容。
        return self._closed

    @property
    def time_ns(self):
        """读取选中的精确纳秒时刻。

        参数:
            无。
        返回:
            原生int，严格晚于查询游标且不超过domain_end。
        异常:
            ResultClosedError: 结果已关闭。
        """
        # 先检查自有申请仍存活，再提供不可变整数，不对其作float转换。
        self._ensure_open()
        return self._time

    @property
    def reasons(self):
        """读取同刻全部并列原因。

        参数:
            无。
        返回:
            BoundaryReason tuple，固定种类顺序及target字典序；不表示消费优先级。
        异常:
            ResultClosedError: 结果已关闭。
        """
        # 输出为冻结tuple，不借由属性读取再次扫描更新或来源。
        self._ensure_open()
        return self._reasons

    @property
    def binding_identity(self):
        """读取查询时实际解码绑定身份。

        参数:
            无。
        返回:
            SHA字符串，与当前登记表达式所属绑定一致。
        异常:
            ResultClosedError: 结果已关闭。
        """
        # 已保存字符串不需要上游lease或表达式owner继续打开。
        self._ensure_open()
        return self._binding_identity

    @property
    def compiled_identity(self):
        """读取本次登记表达式的完整身份。

        参数:
            无。
        返回:
            SHA字符串，不以同名表达式或同文本替代登记关系。
        异常:
            ResultClosedError: 结果已关闭。
        """
        # 身份是独立快照的一部分，不保留表达式树及其ENUM域。
        self._ensure_open()
        return self._compiled_identity

    def close(self):
        """抵销一次查询申请并解除owner登记，不关闭任何上游资源。

        参数:
            无。
        返回:
            None；重复关闭安全。
        异常:
            ValueError: 内部预算账本不一致，不能吞掉重复释放或漏计错误。
            KeyboardInterrupt: 未释放金额可重试；已释放时最小关闭后传播取消。
        副作用:
            清除本结果持有的原因、身份及owner引用。
        """
        # 已关闭结果不能再次抵销金额，closed属性仍保留可检查状态。
        if self._closed:
            return
        # 单线程快照覆盖释放成功后的返回取消；未扣账时仍可重试。
        budget, cost = self._owner._budget, self._cost
        before, released = budget.ram_bytes, False
        try:
            budget.release_ram(cost)
            released = True
        finally:
            if released or budget.ram_bytes == before - cost:
                self._discard()

    def _discard(self):
        """无扣账地移除登记并关闭字段，供查询撤销或释放后最小收尾。

        参数: 无。返回: None；本方法不再次释放申请。
        异常: 脱离取消传播，finally仍关闭，owner随后只移除残留登记。
        """
        try:
            self._owner._results.discard(self)
        finally:
            # 即使登记移除取消，也不能保留可再次扣账的结果或已释放大字符串。
            self._closed, self._cost = True, 0
            self._time = self._reasons = self._binding_identity = self._compiled_identity = self._owner = None


class BoundaryQueries:
    """借用表达式owner选择下一边界，所有存活结果各自计账。

    固定申请只持本owner和登记容器；不复制表达式树、绑定、描述或ENUM域。
    表达式owner继续拥有这些元数据，其关闭会丢弃内部引用并拒绝后续查询。
    每次查询重新取得当前TTL，来源EOF仅按实际依赖去重；不持累积timer heap。
    after必须已处理domain起点且不早于state最后提交时刻，caller负责该前提。
    """

    def __init__(self, expressions: ExpressionQueries, *, observation=None):
        """先申请固定容器，再借用打开的表达式owner。

        参数:
            expressions: 当前实际解码绑定的ExpressionQueries，不能为空或关闭。
            observation: 原请求范围内的实际Interval，None保持原HoldContext.domain。
        返回:
            新BoundaryQueries，未创建查询结果。
        异常:
            TypeError: 参数不是ExpressionQueries。
            ResultClosedError: 表达式owner、保持owner或state已关闭。
            BudgetExceededError、MemoryError: 固定申请或容器构造失败，抵销本次申请。
            原异常身份保留；持续清理失败时从boundary_queries_cleanup_owner恢复close。
        副作用:
            只拥有固定预算及自有结果登记；不关闭、复制或推进caller资源。
        """
        # 类型和上游生命周期先成立，不能借同名对象或关闭对象继续选边界。
        if not isinstance(expressions, ExpressionQueries):
            raise TypeError('边界查询需要ExpressionQueries')
        expressions._ensure_open()
        # 独立推进范围必须来自显式实际观测，不通过克隆保持上下文改变绑定身份。
        domain = expressions._holds._context.domain
        if observation is not None:
            if not isinstance(observation, Interval):
                raise TypeError('边界查询实际观测范围需要Interval或None')
            if observation.start_ns < domain.start_ns or observation.end_ns > domain.end_ns:
                raise ValueError('边界查询实际观测范围必须完全位于原domain内')
            domain = observation
        # 清理字段在分配前准备，失败关闭允许处理尚未建立的结果登记容器。
        self._budget, self._fixed_cost, self._closed = expressions._budget, 0, False
        self._expressions = self._results = None
        self._domain = None
        before = self._budget.ram_bytes
        try:
            # 申请在保护块内，返回取消仍要记录真实已申请金额。
            self._budget.reserve_ram(32768)
            self._fixed_cost = 32768
            # 只有轻量owner引用及set容器属于本固定申请，不保存额外模型快照。
            self._expressions, self._results = expressions, set()
            self._domain = domain
        except BaseException as exc:
            if self._fixed_cost == 0 and self._budget.ram_bytes == before + 32768:
                self._fixed_cost = 32768
            # 构造失败或取消只清理本owner，不越权关闭已打开的表达式owner。
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'边界查询初始化清理附加失败: {type(cleanup).__name__}')
                if not self._closed:
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'边界查询初始化清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.boundary_queries_cleanup_owner = self
                            exc.add_note('释放恢复后调用boundary_queries_cleanup_owner.close()')
            raise

    @property
    def closed(self):
        """读取边界owner是否关闭。

        参数:
            无。
        返回:
            bool，独立于caller是否已经关闭。
        异常:
            无。
        """
        # 自身生命周期保留到重复close和恢复核对，无需查询caller。
        return self._closed

    def _ensure_open(self):
        """检查本owner及全部借用上游仍可创建新查询。

        参数:
            无。
        返回:
            None。
        异常:
            ResultClosedError: 本owner、表达式owner、保持owner或state已关闭。
        """
        # 本owner关闭后借用引用被清理，先检查自身避免访问None。
        if self._closed:
            raise ResultClosedError('下一边界owner已关闭')
        # 上游逐层检查生命周期；已有BoundaryResult只检查其自身，不受此限制。
        self._expressions._ensure_open()

    def _query_cost(self, compiled, deadlines):
        """只读取固定元数据大小，估算扫描、排序和结果独立持有空间。

        参数:
            compiled: 已登记表达式，依赖及实际绑定冻结。
            deadlines: 已检查元素类型的RuleDeadline tuple，可含很长的rule_id。
        返回:
            原生int字节数，随依赖、规则、来源上界和字符串长度增长。
        异常:
            KeyError: 内部实际绑定不能解析已登记依赖。
        边界:
            本步骤不访问当前样本、不调用next_expiry、不创建依赖或来源集合。
        """
        # 来源数至多等于依赖数；浅字符串成本按每次保留引用及临时排序保守放大。
        strings = sum(getsizeof(name) + getsizeof(compiled.bindings.resolve(name).source)
                      for name in compiled.dependencies)
        strings += sum(getsizeof(deadline.rule_id) for deadline in deadlines)
        # 两个身份最终由结果独立持有，上游关闭不会使这些引用退出本次计账。
        strings += getsizeof(compiled.bindings.identity) + getsizeof(compiled.identity)
        # 槽位上界覆盖至多每依赖两候选、每规则一候选、update及domain_end与排序key。
        return 32768 + 8192 * (len(compiled.dependencies) + len(deadlines) + 2) + strings * 16

    def _register(self, cost, time_ns, reasons, compiled):
        """仅构造完整结果，查询外层拿到对象后再登记。

        参数:
            cost: 已成功预留的本次字节数。
            time_ns、reasons: 已选出的精确时刻和冻结原因tuple。
            compiled: 当前owner登记对象，用于取得两个身份字符串。
        返回:
            BoundaryResult，尚未登记，外层保有局部清理句柄。
        异常:
            MemoryError、KeyboardInterrupt: 构造或登记失败/取消，查询清理原申请。
        副作用:
            不建立登记归属；不改变caller状态。
        """
        # 结果只保存必要字符串，不保留compiled、样本或Detector来延长其寿命。
        return BoundaryResult(self, cost, time_ns, reasons, compiled.bindings.identity, compiled.identity)

    def query_next(self, compiled, *, after_ns: int, next_group_ns: int | None = None,
                   duration_deadlines: tuple[RuleDeadline, ...] = ()) -> BoundaryResult | None:
        """选择严格晚于已处理游标的下一边界，保留该时刻全部并列原因。

        参数:
            compiled: 当前表达式owner登记的CompiledExpression原对象。
            after_ns: 原生int64纳秒，位于闭区间domain内且不早于state最后提交时刻。
            next_group_ns: 下一完整更新组的原生int64时刻或None，必须严格晚于after。
            duration_deadlines: RuleDeadline tuple；rule_id唯一，每个截止严格晚于after。
        返回:
            须close的BoundaryResult；after等于domain_end时返回None。
            合法未来更新或截止超过domain_end时忽略，domain_end自身仍为候选。
        异常:
            TypeError、TimeOverflowError: 计划、tuple、快照或时间类型/范围错误。
            ValueError: 未登记对象、域外或回溯游标、过期截止、重复rule_id。
            ResultClosedError: 本owner或借用上游关闭。
            BudgetExceededError、MemoryError、KeyboardInterrupt: 预留、扫描、构造或取消错误。
        副作用:
            只登记本次结果；失败或取消抵销申请，不提交state或推进Detector。
        边界:
            起点初始化由caller完成，不使用start-1；原因排序不决定结束分类。
            after到域末时仍完整校验入参，不用结束状态掩盖错误截止或重复规则。
        """
        # 先核对当前可用上游及登记对象本身，SHA或表达式文本相同不能替代对象登记。
        self._ensure_open()
        expressions = self._expressions
        if (not isinstance(compiled, CompiledExpression) or id(compiled) not in expressions._stats
                or not any(item is compiled for item in expressions._expressions)):
            raise ValueError('只能查询当前表达式owner登记的CompiledExpression对象')
        # 所有入口坐标保持原生int64，下一组不得回退；检查只读取冻结协议，不扫描TTL。
        after = _require_native_ns(after_ns, 'boundary.after_ns')
        if next_group_ns is not None:
            _require_native_ns(next_group_ns, 'boundary.next_group_ns')
            if next_group_ns <= after:
                raise ValueError('下一完整更新时间必须严格晚于已处理游标')
        if type(duration_deadlines) is not tuple or any(type(item) is not RuleDeadline for item in duration_deadlines):
            raise TypeError('duration_deadlines需要RuleDeadline tuple')
        # domain闭区间允许最后真实点，但state只支持从已提交组向未来查询。
        holds, domain = expressions._holds, self._domain
        if not domain.start_ns <= after <= domain.end_ns:
            raise ValueError('边界游标超出当前domain')
        last = holds._state.last_time_ns
        if last is not None and after < last:
            raise ValueError('边界游标不能早于最新已提交组')
        # 申请覆盖查询所有容器、长字符串与输出；预算不足时尚未扫描当前TTL或EOF。
        cost = self._query_cost(compiled, duration_deadlines)
        before, owned, result = self._budget.ram_bytes, False, None
        try:
            # 申请完成后的返回取消也处于清理边界内，不留下未交付预算。
            self._budget.reserve_ram(cost)
            owned = True
            # 重复检查需要set，必须在预留之后；域外未来截止也先按完整输入协议核对。
            rule_ids = set()
            for deadline in duration_deadlines:
                if deadline.rule_id in rule_ids:
                    raise ValueError('duration截止快照rule_id重复')
                rule_ids.add(deadline.rule_id)
                if deadline.time_ns <= after:
                    raise ValueError('duration截止必须严格晚于已处理游标')
            # 域末不产生下一个边界；所有输入已验证，本次临时申请由finally释放。
            if after == domain.end_ns:
                return None
            # domain_end恒在当前游标之后，保证无更新、无样本和纯常量查询仍有收尾边界。
            candidates = [(domain.end_ns, BoundaryReason('domain_end', ''))]
            sources = set()
            for name in compiled.dependencies:
                # 每次从当前样本重算TTL，新更新覆盖旧截止；空样本不伪造定时器。
                expiry = holds.next_expiry(name, after)
                if expiry is not None and after < expiry <= domain.end_ns:
                    candidates.append((expiry, BoundaryReason('ttl', name)))
                # 同来源多列只产生一项EOF；未知空来源终点保持None，不能补成域末。
                source = compiled.bindings.resolve(name).source
                if source not in sources:
                    sources.add(source)
                    end = holds._bounds[source][1]
                    if end is not None and after < end <= domain.end_ns:
                        candidates.append((end, BoundaryReason('source_eof', source)))
            # 只加入合法域内的当前duration快照，不保存未选中timer供未来复用。
            for deadline in duration_deadlines:
                if deadline.time_ns <= domain.end_ns:
                    candidates.append((deadline.time_ns, BoundaryReason('duration', deadline.rule_id)))
            # 下一完整组只是一项时刻证据；不消费组、不把timer或EOF标成实际更新。
            if next_group_ns is not None and next_group_ns <= domain.end_ns:
                candidates.append((next_group_ns, BoundaryReason('update', '')))
            # 每次只选择一个最早时刻，保留同刻全部原因；排序只影响可检查展示顺序。
            time_ns = min(time for time, _ in candidates)
            reasons = tuple(sorted((reason for time, reason in candidates if time == time_ns), key=_reason_key))
            result = self._register(cost, time_ns, reasons, compiled)
            # 有局部对象才安装；部分add失败仅撤销当前对象，不扫描旧结果。
            self._results.add(result)
            # 成功以后查询金额移交结果，临时容器消失但保守上界保留到结果关闭。
            owned = False
            return result
        except BaseException:
            if result is not None:
                result._discard()
            raise
        finally:
            # 拒绝、构造/登记故障及取消均只抵销本次金额，caller最新状态保持原样。
            if owned or result is None and self._budget.ram_bytes == before + cost:
                self._budget.release_ram(cost)

    def close(self):
        """关闭全部自有结果与固定申请，保留caller表达式、保持、状态和历史。

        参数:
            无。
        返回:
            None；重复关闭安全，也允许构造中途失败时收尾。
        异常:
            ValueError: 内部账本金额不一致，不能静默绕过。
            KeyboardInterrupt: 子结果/固定申请未释放可重试，已释放不会再次扣账。
        副作用:
            逐项关闭自有结果并丢弃caller引用，不打开或删除文件。
        """
        # 已关闭owner不能再次释放固定申请，部分构造失败时_results可能仍为None。
        if self._closed:
            return
        # 逐项关闭不另复制全部活动结果；每个结果自身解除登记并抵销一次查询金额。
        while self._results:
            result = next(iter(self._results))
            result.close()
            # 释放后脱离取消可能留下已关闭登记，重试只移除该项，不再扣账。
            self._results.discard(result)
        # 固定金额独立于caller元数据申请，释放后只清理本owner字段。
        cost, before, released = self._fixed_cost, self._budget.ram_bytes, False
        try:
            self._budget.release_ram(cost)
            released = True
        finally:
            if released or self._budget.ram_bytes == before - cost:
                self._closed, self._fixed_cost = True, 0
                self._expressions = self._results = self._domain = None
