"""在有预算的保持快照上调用两个既有独立表达式数值核。

输入为调用方的HoldQueries、实际解码证据绑定和预先编译的固定表达式tuple；
输出须关闭的ExpressionResult，保存同轴结果、实际依赖更新和原样本引用。
owner先申请固定空间，再有预算地遍历元数据及各表达式DAG；查询先按节点、
边、依赖、轴长和ENUM域申请暂存上界，再建立保持/context并求值。
参考逐点调用独立标量核，NumPy调用整列数组核，没有标量回退或重新归一化。
临时HoldResult始终关闭，返回结果独立计持有原样本及输出，不随state更新改变。
本模块不编译任意文本、不读文件、不调度事件/deadline、不关闭调用方资源。
来源关联核对配置及实际描述证据；state样本由调用方从绑定历史推进，本层模型
没有历史SHA字段，不能把这种契约检查声称为逐条样本的防伪认证。
预算是新分析层保守估算，不代表整个进程RSS或恶意修改私有字段的防护。
"""

# 元数据按对象身份去重，避免对共享DAG反复展开或使用32层历史描述限制。
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from sys import getsizeof
from types import MappingProxyType
import numpy as np
from ..core.binding import _identity
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression, ExprNode
from ..core.expression_reference import Evaluation, evaluate_reference
from ..core.expression_numpy import ArrayEvaluation, evaluate_numpy
from ..core.numeric import ScalarValue
from ..core.lookup import pack_requested_lookups
from ..core.types import QualityFlag as Q
from ..core.numeric_numpy import NumericArray
from ..results.errors import ResultClosedError
from ..timebase.conversion import require_int64_ns
from .bindings import _fingerprint
from .history import _metadata_bytes
from .history_records import estimate_record_bytes
from .hold import HoldQueries
from .where_state import before_context, group_updates, group_active
from .calculation_values import scalar_from_column


class ExpressionResult:
    """持有独立输出和样本预算；关闭后拒绝读取，owner关闭全部自有结果。

    数组按普通只读约定提供；外部另存已取得的rows/arrays/samples超过关闭时刻，
    须自行负责这些引用的内存，不把释放申请解释为强制销毁外部对象。
    """

    def __init__(self, owner, cost, times, payload, actual, samples, compiled):
        """保存一次表达式查询的完整输出及其内存申请。

        参数:
            owner: 创建本结果的ExpressionQueries，负责登记和统一关闭。
            cost: 本结果持有的预算字节数，由查询入口提前申请。
            times: 整数纳秒轴，为tuple或只读一维INT64数组。
            payload: 参考Evaluation元组或NumPy ArrayEvaluation，与时间轴等长。
            actual: 各查询点是否存在真实依赖更新，与时间轴等长。
            samples: 保持查询使用的非空原样本元组，保留来源定位。
            compiled: 本次使用的已登记编译对象，提供表达式及绑定身份。
        返回:
            新结果；不复制样本，不重新计算表达式。
        异常:
            构造失败由调用方释放本次预算，不向owner安装半成品。
        """
        # 结果取得自己的申请；关闭前不依赖state仍保留同一旧样本。
        self._owner, self._cost, self._closed = owner, cost, False
        self._times, self._payload, self._actual, self._samples = times, payload, actual, samples
        self._where_invalid = None  # where 对当前真实组的活动无效更新；其他表达式沿用原证据。
        self._where_ends = None  # where 仅保留活动输入的来源末端；数量受来源数限制。
        self._binding_identity, self._compiled_identity = compiled.bindings.identity, compiled.identity

    def _ensure_open(self):
        """拒绝关闭后读取。参数: 无。返回: None。异常: ResultClosedError。"""
        # 关闭已释放本对象预算，不能继续从它读取输出。
        if self._closed:
            raise ResultClosedError('表达式查询结果已关闭')

    @property
    def closed(self):
        """读取关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def times_ns(self):
        """读取自有整数ns轴。参数: 无。返回: tuple或只读int64列。异常: ResultClosedError。"""
        self._ensure_open()
        return self._times

    @property
    def rows(self) -> tuple[Evaluation, ...]:
        """读取参考输出。参数: 无。返回: Evaluation tuple。异常: 关闭或后端类型错误。"""
        self._ensure_open()
        # 参考输出与数组输出有不同结构，禁止取错接口后误解字段。
        if type(self._payload) is not tuple:
            raise TypeError('NumPy表达式查询请读取arrays')
        return self._payload

    @property
    def arrays(self) -> ArrayEvaluation:
        """读取NumPy输出。参数: 无。返回: ArrayEvaluation。异常: 关闭或后端类型错误。"""
        self._ensure_open()
        # 数组接口只返回真实数组计算结果，不把参考元组包装成数组。
        if not isinstance(self._payload, ArrayEvaluation):
            raise TypeError('参考表达式查询请读取rows')
        return self._payload

    @property
    def actual_update(self):
        """读取真实输出更新，where 按活动分支。参数: 无。返回: 同轴bool tuple或只读列。异常: 关闭。"""
        self._ensure_open()
        return self._actual

    @property
    def samples(self):
        """读取非None原样本，保留dependencies顺序。参数: 无。返回: tuple。异常: 关闭。"""
        self._ensure_open()
        return self._samples

    @property
    def binding_identity(self):
        """读取实际绑定身份。参数: 无。返回: SHA文本。异常: ResultClosedError。"""
        self._ensure_open()
        return self._binding_identity

    @property
    def compiled_identity(self):
        """读取登记表达式身份。参数: 无。返回: SHA文本。异常: ResultClosedError。"""
        self._ensure_open()
        return self._compiled_identity

    def close(self):
        """释放本结果的申请及引用，保留调用方的保持查询对象。

        参数:
            无。
        返回:
            None；重复关闭不会重复抵销申请。
        异常:
            预算账本不一致时传播内部错误。
        副作用:
            从owner登记表移除自身，丢弃时间轴、输出和原样本引用。
            外部提前取得的数组或行对象仍由外部调用方负责其生命周期。
        """
        if self._closed:
            return
        # 单线程快照只辨认本结果release是否实际完成，不改变其他owner的账目。
        budget, cost = self._owner._budget, self._cost
        before = budget.ram_bytes
        released = False
        try:
            budget.release_ram(cost)
            released = True
        finally:
            # 已扣账后的返回取消必须关闭，未扣账的取消保留原结果可重试。
            if released or budget.ram_bytes == before - cost:
                self._discard()

    def _discard(self):
        """移除当前结果并丢引用，预算抵销责任留给调用者。

        参数: 无；仅用于已释放结果或尚由查询持有申请的失败结果。
        返回: None，标记关闭。
        异常: 登记移除错误传播，finally仍关闭避免重复扣账。
        """
        # 不调用close抵销第二次金额，保留外层对本次唯一申请的清理责任。
        try:
            self._owner._results.discard(self)
        finally:
            self._closed, self._cost = True, 0
            self._times = self._payload = self._actual = self._samples = self._owner = self._where_ends = None


class ExpressionQueries:
    """登记固定可执行表达式，按当前保持状态产生独立预算快照。

    不持有全量样本；绑定、声明、文本、DAG和ENUM域在固定申请中独立计账。
    查询仅接受登记的对象本身，不根据同名或同SHA接收另一个编译对象。
    调用方关闭holds/state后拒绝新查询，已返回结果仍可读至自身/本owner关闭。
    """

    def __init__(self, holds: HoldQueries, bindings: DecodedBindings, expressions: tuple[CompiledExpression, ...]):
        """登记一组已编译表达式，并为固定元数据先申请空间。

        参数:
            holds: 调用方的HoldQueries，包含当前状态及已核对的来源范围。
            bindings: DecodedBindings，来自实际历史校核，静态声明不能代替。
            expressions: CompiledExpression元组；只接受这些对象本身的后续查询。
        返回:
            新ExpressionQueries；不持有全部历史样本，也不关闭调用方资源。
        异常:
            TypeError: 输入类型或元数据类型不符合已定义协议。
            ValueError: 来源、转换、范围或表达式绑定不匹配。
            BudgetExceededError: 固定元数据超预算；关闭本次部分构造并抵销申请。
            原构造异常不被清理失败替换；持续失败时从expression_queries_cleanup_owner恢复close。
        处理流程:
            先预留容器，再按对象身份遍历绑定、表达式及标签域，逐步增加申请。
            核对来源证据和同步条件，最后记录每个表达式的节点、边及枚举域成本。
        """
        if (not isinstance(holds, HoldQueries) or not isinstance(bindings, DecodedBindings)
                or type(expressions) is not tuple or any(not isinstance(item, CompiledExpression) for item in expressions)):
            raise TypeError('表达式查询需要HoldQueries/DecodedBindings及CompiledExpression tuple')
        # 构造前确认调用方保持对象仍可用，此时尚未创建任何自有申请。
        holds._ensure_open()
        # 引用和遍历容器先有固定预留；后续每一对象/节点增长另申请后再加入容器。
        self._budget, self._fixed_cost, self._closed = holds._budget, 0, False
        self._holds = self._bindings = self._expressions = self._stats = self._labels = self._results = None
        self._lookup_plans = None
        try:
            self._charge(32768 + len(expressions) * 2048)
            self._holds, self._bindings, self._expressions = holds, bindings, expressions
            self._results, self._stats = set(), {}
            self._lookup_plans = {}
            # 标签映射可很宽；复制容器之前先计槽位，深域随后逐对象申请。
            self._charge(8192 + len(holds._labels) * 1024)
            self._labels = MappingProxyType(dict(holds._labels))
            # 包括原描述/EOF和借用标签，owner在调用方lease关闭后仍计自身元数据引用。
            self._walk_metadata((bindings, expressions, holds._context, self._labels))
            # 原历史描述已按JSON深度协议验证；指纹临时树会重复编码共享来源定位。
            # 此额外申请仅计实际描述，不把32层JSON限制施加给表达式DAG。
            self._charge(16 * _metadata_bytes(holds._context.descriptions))
            # 同名字段不能证明转换、来源及时间范围一致，必须逐项核对。
            self._check_contract()
            # 每棵树属于当前实际绑定，联合依赖仍要通过同步约束。
            for compiled in expressions:
                if not isinstance(compiled.bindings, DecodedBindings) or compiled.bindings.identity != bindings.identity:
                    raise ValueError('登记表达式与当前解码运行绑定不同')
                bindings.require_synchronized(compiled.dependencies)
                # 同一登记对象重复出现不增加查询选择语义；元数据早已按id去重。
                if id(compiled) not in self._stats:
                    self._stats[id(compiled)] = self._node_counts(compiled)
        except BaseException as exc:
            # 部分构造也可能已持有固定申请；取消和分配失败均仅清理本owner。
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'表达式查询初始化清理附加失败: {type(cleanup).__name__}')
                # 固定申请分次产生，恢复owner保留完整自有金额，不动借用holds/state。
                if not self._closed:
                    try:
                        self.close()
                    except BaseException as retry:
                        exc.add_note(f'表达式查询初始化清理重试失败: {type(retry).__name__}')
                        if not self._closed:
                            exc.expression_queries_cleanup_owner = self
                            exc.add_note('释放恢复后调用expression_queries_cleanup_owner.close()')
            raise

    def _charge(self, amount):
        """逐步申请固定空间。参数: amount非负bytes。返回: None。异常: 预算超限。

        先申请再增加本owner计数，失败不改原申请，不启动后续容器增长。
        """
        before = self._budget.ram_bytes
        try:
            self._budget.reserve_ram(amount)
        finally:
            # reserve正常完成或已记账后取消，都先纳入构造owner再由其关闭收尾。
            if self._budget.ram_bytes == before + amount:
                self._fixed_cost += amount

    def _walk_metadata(self, value):
        """按对象身份遍历固定元数据，先计账再扩展遍历容器。

        参数:
            value: 已冻结的绑定、表达式、来源描述及标签树。
        返回:
            None；每个不同对象只计一次，DAG共享节点不反复展开。
        异常:
            TypeError: 遇到协议之外的类型。
            BudgetExceededError: 本次对象或容器的预留不足。
        边界:
            表达式树不套用历史JSON的32层限制；不扩大表达式允许的语法。
            预算包含对象浅大小、遍历集合、栈以及后续指纹计算的保守暂存。
        """
        stack, seen = [value], set()
        while stack:
            item = stack.pop()
            # 共享节点按对象身份只展开一次，避免DAG重复持有量无限增长。
            if id(item) in seen:
                continue
            # 16倍对象浅大小和固定槽位覆盖持有、visited、栈与稍后指纹临时树。
            self._charge(1024 + getsizeof(item) * 16)
            seen.add(id(item))
            if is_dataclass(item) and not isinstance(item, type):
                # 所有模型字段进入成本；字段信息只在已预留的局部容器中使用。
                for entry in fields(item):
                    self._charge(512)
                    stack.append(getattr(item, entry.name))
            elif isinstance(item, Mapping):
                # 键和值均进入树；先预留全部槽位，再增长遍历栈。
                self._charge(len(item) * 1024)
                for key, child in item.items():
                    stack.append(key)
                    stack.append(child)
            elif type(item) is tuple:
                # 冻结序列仍需要遍历暂存，空tuple不会虚构子项。
                self._charge(len(item) * 512)
                stack.extend(item)
            elif isinstance(item, Enum) or item is None or type(item) in (str, int, float, bool, bytes):
                # 原生叶值已计入getsizeof；枚举是typed声明而非任意对象协议。
                continue
            else:
                raise TypeError('表达式查询元数据含未支持类型')

    def _check_contract(self):
        """核对保持上下文与实际证据、投影内完整定义及会话domain，禁止同名借用。

        参数: 无。返回: None。异常: ValueError为来源/指纹/端点/定义不符。
        不重读历史；调用方仍负责从绑定历史推进当前state。
        """
        # 校验上下文契约，不重读历史；样本仍由调用方按同一绑定历史推进。
        context, declarations = self._holds._context, self._bindings.declarations
        if context.session_id != declarations.session_id or context.domain != declarations.domain:
            raise ValueError('保持会话/domain与解码运行绑定不同')
        evidence = {item.source: item for item in self._bindings.sources}
        descriptions = {item.name: item for item in context.descriptions}
        completions = {item.source: item for item in context.completions}
        # 元数据遍历已经预付绑定及描述；保持状态必须恰好覆盖真实历史投影。
        # 未使用声明仍在bindings.signals中供静态检查，不把它们当作实际读取事实。
        definitions = {item.name: item for item in self._bindings.projected_signals}
        if (evidence.keys() != descriptions.keys() or evidence.keys() != completions.keys()
                or definitions.keys() != self._holds._definitions.keys()):
            raise ValueError('保持来源/信号集合与解码运行绑定不同')
        # 完整转换定义参与比对，不能只根据别名或目标类型借用旧状态。
        for name, definition in definitions.items():
            if _identity(definition.identity()) != _identity(self._holds._definitions[name].identity()):
                raise ValueError('保持完整信号转换与解码运行绑定不同')
        # 来源描述、观测范围和完整EOF记录共同匹配实际运行证据。
        for name, proof in evidence.items():
            description, completion = descriptions[name], completions[name]
            if (_fingerprint(description) != proof.description_sha256
                    or description.observation_start_ns != proof.observation_start_ns
                    or completion.session_id != proof.session_id or not completion.source_eof
                    or completion.observed_end_ns != proof.observation_end_ns
                    or completion.batch_index + 1 != proof.progress_count):
                raise ValueError('保持实际描述/范围/EOF与运行证据不同')

    def _node_counts(self, compiled):
        """记录表达式的唯一节点、全部参数边及枚举域暂存成本。

        参数:
            compiled: 当前登记的CompiledExpression对象。
        返回:
            四项元组：唯一节点数、参数边数、枚举暂存字节估算、是否有 where。
        异常:
            TypeError: 节点不是ExprNode。
            BudgetExceededError: 遍历节点及容器增长的固定申请不足。
        边界:
            用对象身份去重，不对递归节点作结构哈希；不同对象保守分别计账。
            即使查询轴为空，枚举标签构造和验证仍可能需要空间。
        """
        # 只遍历ExprNode；共享对象只展开一次，节点及全部参数边先计账再扩栈。
        stack, seen, edges, enum_cost = [compiled.root], set(), 0, 0
        has_where = False
        while stack:
            node = stack.pop()
            if not isinstance(node, ExprNode):
                raise TypeError('登记表达式需要typed ExprNode树')
            if id(node) in seen:
                continue
            self._charge(4096 + len(node.args) * 512)
            if node.operator == 'lookup':
                # 预付执行副本中两列及构造暂存。只在首次实际 NumPy 查询时打包。
                self._charge(32 * len(node.value.points))
            seen.add(id(node))
            edges += len(node.args)
            has_where |= node.operator == 'where'
            stack.extend(node.args)
            # 核心模型/求值器会set/tuple固定域，N=0时这些临时量仍存在。
            enum_cost += 16 * (getsizeof(node.labels) + sum(getsizeof(label) + 128 for label in node.labels))
        for name in compiled.dependencies:
            labels = self._labels[name]
            enum_cost += 16 * (getsizeof(labels) + sum(getsizeof(label) + 128 for label in labels))
        from ..core.enum_codes import code_dependencies
        return len(seen), edges, enum_cost, has_where, code_dependencies(compiled.root)

    @property
    def closed(self):
        """读取owner关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def _ensure_open(self):
        """拒绝owner/调用方保持/state关闭后新查询。参数: 无。返回: None。异常: 关闭。"""
        if self._closed:
            raise ResultClosedError('表达式查询owner已关闭')
        # 上游保持对象继续检查state；已有结果不借此限制读取自身快照。
        self._holds._ensure_open()

    def _prepare(self, compiled, count, point):
        """检查表达式登记关系，并预留本次输出、缓存及原样本的空间。

        参数:
            compiled: 必须是本owner登记的对象本身。
            count: 查询轴长度，空轴为0。
            point: 原生bool，是否按点视图解释真实末端。
        返回:
            本次成功申请的字节数；调用方负责将其交给结果或在失败时释放。
        异常:
            ResultClosedError: owner、保持对象或状态已关闭。
            TypeError: point不是bool。
            ValueError: 编译对象未登记。
            BudgetExceededError: 无法预留本次查询空间。
        边界:
            成本随节点、边、依赖和轴长增长，也覆盖空轴对象头及固定枚举临时量。
            原样本引用单独计账；这里不创建保持列，也不执行数值运算。
        """
        self._ensure_open()
        # 不接受整数或NumPy bool隐式充当点查询开关。
        if type(point) is not bool:
            raise TypeError('point需要bool')
        # 身份摘要相同也不能绕过登记，只接受已保留成本的原对象。
        if id(compiled) not in self._stats or not any(item is compiled for item in self._expressions):
            raise ValueError('只能查询当前owner登记的CompiledExpression对象')
        nodes, edges, enum_cost, _, _ = self._stats[id(compiled)]
        # 所有局部cache节点同时存活；4096/节点边依赖/点覆盖复制、整数掩码和isclose多核。
        # (N+1)包括N=0的对象/列头/缓存容器，ENUM域另计而不是按轴长隐藏。
        sample_cost = sum(estimate_record_bytes(sample) for name in compiled.dependencies
                          if (sample := self._holds._state.get(name)) is not None)
        cost = 32768 + 4096 * (nodes + edges + len(compiled.dependencies) + 1) * (count + 1) + enum_cost * 4 + sample_cost
        self._budget.reserve_ram(cost)
        return cost

    def _where_evidence(self, compiled, time, context, backend):
        """同一状态快照只有最近组可能更新。参数: 树、纳秒、当前标量和后端。
        返回: 真实输出更新及活动无效输入标志。异常: 状态/后端求值错误。
        """
        state = self._holds._state
        previous = before_context(state, compiled.dependencies, time, bounds=self._holds._bounds, left_limit=True)
        if time == self._holds._context.domain.start_ns:
            previous = {name: ScalarValue(None, val.dtype, False, Q.MISSING, val.labels) for name,val in previous.items()}
        updated, invalid = {}, {}
        for name in compiled.dependencies:
            sample = state.get(name)
            updated[name] = sample is not None and sample.time_ns == time
            invalid[name] = updated[name] and not sample.value.valid
        return (group_updates(compiled.root, context, previous, updated, backend),
                group_active(compiled.root, context, invalid, backend))

    def _source_cutoffs(self, compiled):
        """取静态候选末端供活动判断。参数: 登记表达式。返回: 别名到纳秒。异常: 绑定错误。"""
        return {name: self._holds._bounds[self._holds._definitions[name].source][1] for name in compiled.dependencies}

    def _check_axis(self, times):
        """检查规范整数轴非回退及最新状态限制，纯常量同样执行。

        参数: times已规范tuple或精确int64列。返回: None。异常: ValueError为回退。
        此处共享时间协议，不共享两个保持/表达式数值核。
        """
        # 数组轴用整列比较，参考tuple用独立整数协议；临时mask已在查询上界内。
        backward = np.any(times[1:] < times[:-1]) if type(times) is np.ndarray else any(
            right < left for left, right in zip(times, times[1:]))
        if backward:
            raise ValueError('表达式查询轴回退')
        # 当前状态只能向后查询；等于最后更新时间合法，重复轴也合法。
        last = self._holds._state.last_time_ns
        if len(times) and last is not None and int(times[0]) < last:
            raise ValueError('最新状态不能回溯已经提交的过去')

    def _register(self, cost, times, payload, actual, samples, compiled):
        """在完整申请中只构造结果，外层取得对象后负责登记。

        参数: cost/times/payload/actual/samples已完成输出、compiled登记对象。
        返回: ExpressionResult。异常: 构造错误由查询抵销，返回取消不遗留登记。
        """
        # 局部对象和集合安装分开，使半安装取消能准确撤销本批对象。
        return ExpressionResult(self, cost, times, payload, actual, samples, compiled)

    def _keep_hold(self, held, result):
        """登记临时保持结果，列表增长失败也关闭刚取得的申请。

        参数: held本次临时列表、result新HoldResult。返回: None。
        异常: 列表分配错误传播；新结果关闭，之前结果仍由查询finally处理。
        """
        try:
            held.append(result)
        except BaseException:
            # 新保持句柄尚未登记，必须就地关闭；此前句柄由查询finally关闭。
            result.close()
            raise

    def query_reference(self, compiled, times_ns: tuple[int, ...], *, point=False) -> ExpressionResult:
        """在当前状态上逐点执行独立参考保持和标量表达式计算。

        参数:
            compiled: 当前owner登记的编译对象。
            times_ns: 非递减整数纳秒tuple；不能回溯到已提交状态之前。
            point: 默认False；True按点视图检查真实末端，仍排除有效期右端。
        返回:
            须关闭的ExpressionResult；rows为Evaluation元组，空轴得到空元组。
            actual_update记录真实依赖更新，samples保留原样本及其定位。
        异常:
            类型、登记、时间轴、预算或数值错误原样传播；取消也释放本次申请。
        处理流程:
            先预留并检查轴，建立各依赖的独立保持结果，再逐点准备输入并求值。
            输出独立持有原样本预算；所有临时保持结果在finally关闭。
        """
        # 参考轴需要明确元组，避免消费任意迭代器后才发现预算不足。
        if type(times_ns) is not tuple:
            raise TypeError('参考表达式轴需要tuple')
        held, output, cost = None, None, 0
        before = self._budget.ram_bytes
        try:
            # _prepare的申请返回也在保护内，未开始数值核时可安全抵销后重试。
            cost = self._prepare(compiled, len(times_ns), point)
            held = []
            # 先有查询预算，再逐值检查时间，不允许有损转换或回退。
            times = tuple(require_int64_ns(time, 'expression.time_ns') for time in times_ns)
            self._check_axis(times)
            # 各依赖使用同一精确轴；逐项登记临时句柄，所有出口统一关闭。
            for name in compiled.dependencies:
                self._keep_hold(held, self._holds.query_reference(name, times, point=point))
            # 结果与更新诊断分别累积，已知逻辑结果也要保留依赖质量。
            rows, actual = [], []
            evidence = None
            cutoffs = self._source_cutoffs(compiled) if self._stats[id(compiled)][3] else {}
            candidates, active_ends = set(cutoffs.values()), set()
            # 参考实现逐点独立计算；每点只使用同轴保持输入。
            for index, _ in enumerate(times):
                context = {}
                updated = False
                for name, result in zip(compiled.dependencies, held):
                    row = result.rows[index]
                    code = None
                    if name in self._stats[id(compiled)][4]:
                        from ..core.enum_codes import history_code
                        code = history_code(result.definition, row.sample)
                        boundary = row.quality & (Q.MISSING | Q.STALE)
                        if boundary:
                            code = ScalarValue(None, code.dtype, False, code.quality | boundary)
                    context[name] = ScalarValue(row.value, result.definition.dtype, row.valid, row.quality, self._labels[name], code)
                    updated |= row.actual_update
                rows.append(evaluate_reference(compiled, context, self._bindings))
                if times[index] in candidates and group_active(compiled.root, context,
                        {name: end == times[index] for name, end in cutoffs.items()}, 'reference'):
                    active_ends.add(times[index])
                if updated and self._stats[id(compiled)][3]:
                    if evidence is None:
                        evidence = self._where_evidence(compiled, times[index], context, 'reference')
                    updated = evidence[0]
                actual.append(updated)
            # 输出保留原记录定位，关闭临时保持后仍独立计持有量。
            samples = tuple(result.sample for result in held if result.sample is not None)
            # 先取得完整输出但暂不登记；临时保持全部关闭后才允许对外交付。
            output = self._register(cost, times, tuple(rows), tuple(actual), samples, compiled)
            if self._stats[id(compiled)][3]:
                output._where_invalid = evidence is not None and evidence[1]
                output._where_ends = active_ends
            for result in held:
                result.close()
            held = None
            self._results.add(output)
            return output
        except BaseException:
            # 失败输出不会再次close扣账；_prepare返回取消时只能新增其一次申请。
            try:
                if output is not None:
                    output._discard()
            finally:
                amount = cost if cost else max(0, self._budget.ram_bytes - before)
                if amount:
                    self._budget.release_ram(amount)
            raise
        finally:
            # 成功结果已保存独立样本及计账；临时保持句柄在所有出口关闭。
            for result in held or ():
                result.close()

    def query_numpy(self, compiled, times_ns: np.ndarray, *, point=False) -> ExpressionResult:
        """在当前状态上执行独立数组保持与整轴表达式计算。

        参数:
            compiled: 当前owner登记的编译对象。
            times_ns: 一维形状(N,)的INT64 ndarray，时间为整数纳秒且非递减。
            point: 默认False；必须为原生bool，True检查真实末端点视图。
        返回:
            须关闭的ExpressionResult；arrays为ArrayEvaluation，轴及更新掩码只读。
            N=0合法；常量表达式仍显式使用N作为结果长度。
        异常:
            数组布局、登记、时间轴、预算、数值或取消错误原样传播。
        处理流程:
            先申请空间，再复制轴、取得各依赖保持列并调用现有独立数组求值核。
            不逐点调用标量数值核；临时保持始终关闭，失败抵销本次申请。
        """
        # 禁止广播和浮点时间，轴必须使用精确一维INT64布局。
        if type(times_ns) is not np.ndarray or times_ns.ndim != 1 or times_ns.dtype != np.dtype('int64'):
            raise TypeError('NumPy表达式轴需要一维完整int64 ndarray')
        held, output, cost = None, None, 0
        before = self._budget.ram_bytes
        try:
            # 数组预算在任何轴/列复制之前申请，并覆盖申请返回取消的清理窗口。
            cost = self._prepare(compiled, len(times_ns), point)
            held = []
            # 已取得预算才复制轴，查询结果不借用调用方可修改的存储。
            times = times_ns.copy()
            self._check_axis(times)
            context = {}
            actual = np.zeros(len(times), dtype='bool')
            # 各依赖整轴独立保持；取得句柄后立即登记，部分失败也能清理。
            for name in compiled.dependencies:
                result = self._holds.query_numpy(name, times, point=point)
                self._keep_hold(held, result)
                arrays = result.arrays
                # NumericArray复制三个列，已包含在树/依赖×N暂存上界，不借用可变输入。
                from ..core.enum_codes import historical_column
                code = historical_column(result.definition, arrays) if name in self._stats[id(compiled)][4] else None
                context[name] = NumericArray(arrays.dtype, arrays.values, arrays.valid, arrays.quality, arrays.labels, code)
                actual |= arrays.actual_update
            # 整轴调用真实数组求值核；size让无依赖常量和空轴保持长度。
            executable = compiled
            if compiled.bindings.lookups:
                if id(compiled) not in self._lookup_plans:
                    self._lookup_plans[id(compiled)] = pack_requested_lookups(compiled)
                executable = self._lookup_plans[id(compiled)]
            payload = evaluate_numpy(executable, context, self._bindings, size=len(times))
            evidence = None
            active_ends = set()
            if self._stats[id(compiled)][3]:
                cutoffs = self._source_cutoffs(compiled)
                for end in set(cutoffs.values()) - {None}:
                    index = int(times.searchsorted(end))
                    if index < len(times) and times[index] == end:
                        values = {name: scalar_from_column(column, index) for name, column in context.items()}
                        if group_active(compiled.root, values, {n: t == end for n, t in cutoffs.items()}, 'numpy'):
                            active_ends.add(end)
            if self._stats[id(compiled)][3] and np.any(actual):
                # 最新状态的所有真实更新只可能在同一 t。一次求证后应用到重复坐标，
                # 不把未来 TTL 或窗口边界解释成更新，不逐行调用标量数值核。
                index = int(np.argmax(actual))
                values = {name: scalar_from_column(column, index) for name, column in context.items()}
                evidence = self._where_evidence(compiled, int(times[index]), values, 'numpy')
                actual &= evidence[0]
            # 输出保留原记录定位，关闭临时保持后仍独立计持有量。
            samples = tuple(result.sample for result in held if result.sample is not None)
            # 输出轴及真实更新掩码采用普通只读约定，避免外部原地改变诊断。
            times.flags.writeable = actual.flags.writeable = False
            # 临时保持先关闭，尚未登记的完整输出仍由本查询唯一持有。
            output = self._register(cost, times, payload, actual, samples, compiled)
            if self._stats[id(compiled)][3]:
                output._where_invalid = evidence is not None and evidence[1]
                output._where_ends = active_ends
            for result in held:
                result.close()
            held = None
            self._results.add(output)
            return output
        except BaseException:
            # 半安装取消只脱离自己的输出，不能扫描或关闭之前已交付结果。
            try:
                if output is not None:
                    output._discard()
            finally:
                amount = cost if cost else max(0, self._budget.ram_bytes - before)
                if amount:
                    self._budget.release_ram(amount)
            raise
        finally:
            # 成功结果已保存独立样本及计账；临时保持句柄在所有出口关闭。
            for result in held or ():
                result.close()

    def close(self):
        """关闭全部自有查询结果，再释放固定元数据申请。

        参数:
            无。
        返回:
            None；重复关闭幂等，部分初始化失败也可调用。
        异常:
            预算账本不一致时传播内部错误。
        副作用:
            丢弃本owner持有的绑定、表达式、标签及登记引用。
            调用方的holds、state、history和运行绑定lease不由这里关闭。
        """
        if self._closed:
            return
        # 先逐项关闭结果的动态申请，再释放owner固定申请。
        while self._results:
            result = next(iter(self._results))
            result.close()
            # 已关闭对象的脱离曾被取消时，可在owner重试中移除而不再抵销成本。
            self._results.discard(result)
        cost, before = self._fixed_cost, self._budget.ram_bytes
        released = False
        try:
            self._budget.release_ram(cost)
            released = True
        finally:
            # 只有固定申请实际抵销后才关闭owner，返回取消也完成最小引用收尾。
            if released or self._budget.ram_bytes == before - cost:
                self._finish_close()

    def _finish_close(self):
        """丢弃已释放固定申请的owner引用，不再关闭上游或操作账本。

        参数: 无。返回: None，owner关闭。
        异常: 无主动异常；只在已释放固定空间的收尾调用。
        """
        # 与保持/state/运行绑定lease的所有权分离，借用引用在此释放。
        self._closed, self._fixed_cost = True, 0
        self._lookup_plans = None
        self._holds = self._bindings = self._expressions = self._stats = self._labels = self._results = None
