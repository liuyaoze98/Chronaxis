"""执行当前分析计划并管理一次运行的资源。

公开AnalysisRunner选择实际计算后端后交给本会话。构造只检查声明、申请有限预算
并创建独占工作目录；execute调用记录流执行树，关闭输入，再把结果及导出文件
移交给AnalysisResult。默认依据真实相邻记录的时间间隔计算，逐消息累计由同一
执行树按原消息语义处理；不根据旧配置版本选择另一套流程。

错误保留原异常和明确的清理所有者。只有各层实际关闭后才退还对应费用；成功移交
后的结果由调用方关闭，本会话不重复关闭它。现场留存仅由diagnostics.retain_work
决定；目录删除始终核对本次创建身份，不触碰已有目录或RefProjects。
"""

# 协调层只调用已有生产协议；UUID/时区时间是运行身份，不参与稳定输入摘要。
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from uuid import uuid4
from ..planning.plan import AnalysisPlan
from ..planning.legacy_execution import require_can_decode_scope
from ..planning.input_requirements import collect_input_requirements
from ..results.budget import ResourceBudget
from ..results.errors import AnalysisError, ResultClosedError
from ..results.manifest import RunMetadata
from ..results.result import AnalysisResult
from ..results.spool import ResultSpool, _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .history import _metadata_bytes


class RunSession:
    """拥有一次执行的资源树和协调费用，原计划仅借用且不重新解析。

    _constructing标识当前未返回工厂的最高槽。记录执行树负责其输入与计算子资源，
    本会话负责执行树、最终暂存及结果的唯一移交。
    _result在最后费用释放成功前仍自有；_completed后移交且_closed为True。
    """

    def __init__(self, plan, work_dir=None):
        """申请有限固定状态，拒绝已有或受保护目录，不读取来源。

        参数: plan为已选实际backend的AnalysisPlan；work_dir为全新路径，None创建
            唯一临时根。返回: 单次执行owner。异常: 类型、路径、预算或取消原错；
            持续构造清理失败附runner_cleanup_owner，已有目录不会被写入诊断。
        """
        # 类型拒绝不接管调用方计划；其来源与raw_config从未复制或修改。
        if not isinstance(plan, AnalysisPlan) or work_dir is not None and not isinstance(work_dir, (str, Path)):
            raise TypeError('RunSession需AnalysisPlan及可选新工作路径')
        # typed计划也可直接构造；先检查有限策略值，实际需求在支付协调费用后统一计算。
        require_can_decode_scope(plan)
        from ..planning.export_options import require_export_options
        require_export_options(plan)
        self._plan = plan
        self._budget = ResourceBudget(plan.execution.memory_budget_bytes, plan.execution.spool_quota_bytes)
        self._requirements = None
        self._fixed_cost = self._metadata_cost = self._held_cost = 0
        self._record_calculations = None
        self._spool = self._result = self._metadata = None
        self._constructing = None
        self._artifact_exports = None
        self._path = self._run_id = self._started_at = None
        self._path_identity = None
        self._owns_path = False
        self._retain_work = plan.diagnostics.retain_work
        self._started = self._completed = self._closed = self._closing = self._failed = False
        try:
            # 先付协调数组、路径和运行标识的有限槽，再构造这些容器。
            cost = (65536 + 8192 * len(plan.sources) + 4096 * len(plan.signals)
                + 16 * _metadata_bytes((plan.identity, plan.dataset.dataset_id,
                    plan.dataset.entity, plan.dataset.session_id, plan.dataset.domain, plan.dataset.timebase))
                + (0 if work_dir is None else 32 * _metadata_bytes(str(work_dir))))
            _reserve_owned_ram(self, cost, '_fixed_cost')
            # 需求索引只含有限声明字段；先覆盖集合、定位解析及冻结tuple，再创建实际需求。
            _reserve_owned_ram(self, 65536 + 64 * _metadata_bytes(plan.bindings)
                + 32 * _metadata_bytes((plan.rules, plan.windows, plan.calculations, plan.message_calculations)), '_fixed_cost')
            self._require_static_derived()
            self._requirements = collect_input_requirements(plan)
            # resolve同时防止符号链接把看似新目录导入历史快照；保护检查在mkdir前。
            candidate = Path(tempfile.gettempdir()) if work_dir is None else Path(work_dir)
            candidate = candidate.resolve()
            if any(part.casefold() == 'refprojects' for part in candidate.parts):
                raise ValueError('运行工作目录不能位于RefProjects')
            if work_dir is None:
                self._path = Path(tempfile.mkdtemp(prefix='chronaxis-run-', dir=candidate))
            else:
                candidate.mkdir(parents=True, exist_ok=False)
                self._path = candidate
            from ..results.owned_directory import directory_identity
            self._path_identity = directory_identity(self._path)
            self._owns_path = True
            self._run_id = uuid4().hex
            self._started_at = datetime.now(timezone.utc).isoformat()
        except BaseException as exc:
            # 本构造只有自有有限费用与新根；关闭不删除文件，也不向未取得的目录写诊断。
            self._failed = True
            exc.runner_cleanup_owner = self
            _cleanup_owner(self, exc, 'runner_cleanup_owner', '运行会话构造')
            raise

    def _require_static_derived(self):
        """在需求收集和输入动作前复核全部派生声明，不把派生项变成运行根。

        参数: 无，借用本会话原计划及声明绑定。
        返回: None；原静态对象、声明顺序和完整身份均须一致，空任务也不省略校验。
        异常: TypeError/ValueError为typed声明或静态对象被替换；预算和取消错误原样传播。
        所有解析表、遍历容器和展开树先付到本owner的_fixed_cost槽，构造失败由
        原RunSession清理链回收；本方法不创建目录、不打开来源、不生成普通样本。
        """
        from ..core.expression import ExprNode, StaticExpression, validate_expression
        plan = self._plan
        definitions = definition = static = checked = stack = sizes = node = None
        try:
            if (type(plan.derived) is not tuple or type(plan.derived_expressions) is not tuple
                    or len(plan.derived) != len(plan.derived_expressions)
                    or any(type(item) is not StaticExpression for item in plan.derived_expressions)):
                raise ValueError('计划派生与静态表达式数量或类型不一致')
            if not plan.derived and not plan.bindings.derived_names:
                return
            # 使用协调owner既有费用槽；解析表、遍历栈和展开树都在创建前付款。
            _reserve_owned_ram(self, 65536 + 32 * _metadata_bytes(plan.derived), '_fixed_cost')
            definitions = tuple(item.definition for item in plan.derived)
            if tuple(item.name for item in definitions) != plan.bindings.derived_names:
                raise ValueError('计划派生与原绑定名称空间不一致')
            total = 0
            for static in plan.derived_expressions:
                # 与历史阶段同样计共享DAG的展开边，不能按唯一节点低估repr空间。
                _reserve_owned_ram(self, 4096, '_fixed_cost')
                stack, sizes = [(static.root, False)], {}
                while stack:
                    node, expanded = stack.pop()
                    if not isinstance(node, ExprNode):
                        raise TypeError('计划静态表达式需ExprNode树')
                    if id(node) in sizes:
                        continue
                    if not expanded:
                        _reserve_owned_ram(self, 4096 + 512 * len(node.args), '_fixed_cost')
                        stack.append((node, True))
                        stack.extend((child, False) for child in node.args)
                        continue
                    own = _metadata_bytes((node.operator, node.dtype, node.unit, node.unit_status,
                        node.value, node.name, node.labels, node.aliases, node.constant,
                        node.allow_float_literal))
                    sizes[id(node)] = 4096 + 16 * own + sum(sizes[id(child)] for child in node.args)
                total += sizes[id(static.root)] + 16 * _metadata_bytes((
                    static.text, static.normalized_ast, static.dependencies))
                stack = sizes = node = None
            _reserve_owned_ram(self, (1 + len(definitions)) * total, '_fixed_cost')
            for definition, static in zip(definitions, plan.derived_expressions):
                if static.text != definition.name:
                    raise ValueError('计划派生静态表达式需对应原名称')
                checked = validate_expression(definition.name, plan.bindings,
                    derived=definitions, unit=definition.unit)
                if checked != static:
                    raise ValueError('计划派生与原完整静态表达式不一致')
                checked = None
        finally:
            # 构造失败后最高owner会退款，异常栈先撤掉新树和遍历容器的引用。
            plan = definitions = definition = static = checked = stack = sizes = node = None

    @property
    def closed(self):
        """读取协调owner关闭状态。参数: 无。返回: bool。异常: 无。
        """
        return self._closed

    @property
    def failed(self):
        """读取执行或本owner清理失败事实。参数: 无。返回: bool。异常: 无。
        """
        return self._failed

    @property
    def work_dir(self):
        """读取本次已取得的新根。参数: 无。返回: Path或构造未取得时None。异常: 无。
        """
        return self._path

    def _construct(self, slot, factory, *args, **kwargs):
        """调用真实工厂并立即登记返回owner，失败只接其明确恢复属性。

        参数: slot是本会话有限责任槽；factory/args/kwargs为既有生产入口。
        返回: 实际owner。异常: 原工厂错误传播，不对旧半初始化对象调用close。
        """
        self._constructing = slot
        try:
            owner = factory(*args, **kwargs)
            setattr(self, slot, owner)
            return owner
        except BaseException as exc:
            # 在标识仍为当前工厂时接管；其他阶段内部spool不能误当最终spool。
            self._adopt_cleanup(exc)
            raise
        finally:
            self._constructing = None


    def execute(self):
        """读取一次并返回独立AnalysisResult，重复调用或失败后禁止重新扫描。

        参数: 无。返回: 完成且尚未关闭的AnalysisResult。异常: 原执行/预算/取消
            错误保留，普通非AnalysisError由公开AnalysisRunner包装；本方法不反复清理，原错
            附runner_cleanup_owner供公开层统一清理或恢复后close。
        """
        if self._started or self._closed or self._closing or self._failed:
            raise ResultClosedError('RunSession只能执行一次，且不能在关闭或失败后推进')
        self._started = True
        try:
            self._run_record_calculations()
            self._close_inputs()
            # 这里只核一致性，不用差额替旧工厂抵账；残留费用不能被成功结果掩盖。
            self._assert_owned_balance()
            self._spool.seal()
            result_options = ({'owned_work': (self._path, self._path_identity)})
            self._construct('_result', AnalysisResult, self._spool, self._metadata,
                table_format=self._plan.outputs.tables, artifact_exports=self._artifact_exports,
                **result_options)
            self._owns_path = False
            # 构造成功时实际result已拥有同一导出仓；在父槽可达后才撤会话责任。
            self._artifact_exports = None
            self._spool = None
            # 结果暂留最高槽直到本owner全部费用成功释放；最后取消仍能从会话关真实结果。
            self._clear_contracts()
            self._release_costs()
            self._assert_owned_balance()
            result, self._result = self._result, None
            self._completed = self._closed = True
            return result
        except BaseException as exc:
            self._failed = True
            self._adopt_cleanup(exc)
            self._diagnose(exc)
            exc.runner_cleanup_owner = self
            raise

    def _run_record_calculations(self):
        """在原会话资源树内执行按需周期统计，保持一个公开AnalysisRunner。

        参数: 无。返回: None，完成结果仍由execute统一封存和移交。
        异常: 静态未支持组合在I/O前拒绝，实际子owner统一登记及清理。
        """
        from ..planning.record_execution import record_execution_errors
        from .record_session_calculations import RecordSessionCalculations
        plan = self._plan
        errors = record_execution_errors(plan)
        if errors:
            raise AnalysisError('; '.join(errors))
        self._construct('_spool', ResultSpool, self._budget, self._path / 'result',
            result_buffer_rows=plan.execution.result_buffer_rows,
            requested_tables=(('events',) if plan.rules else ())+(('calculations',) if any(m.operation!='select' for m in plan.calculations) or plan.message_calculations else ())
                +(('sequences',) if plan.sequences else ())+ (('segments',) if plan.windows else ())
                +(('contributions',) if plan.outputs.contributions=='full' and plan.message_calculations else ())
                +(('input_trace',) if plan.diagnostics.trace else ())
                +(('selections',) if any(m.operation=='select' for m in plan.calculations) else ())
                +(('aggregations',) if plan.aggregations else ()),
            enable_sequences=bool(plan.sequences),
            enable_contributions=plan.outputs.contributions=='full' and bool(plan.message_calculations),
            enable_trace=plan.diagnostics.trace,
            enable_selections=any(m.operation=='select' for m in plan.calculations),
            enable_aggregations=bool(plan.aggregations),
            failure_diagnostics=plan.diagnostics.retain_work)
        self._construct('_record_calculations', RecordSessionCalculations, plan, self._budget, self._path, requirements=self._requirements)
        self._record_calculations.execute_into(self._spool)
        if self._record_calculations._exports is not None:
            self._record_calculations._exports.take_exports(self)
        diagnostic_inputs=(() if self._record_calculations._diagnostics is None else
            self._record_calculations._diagnostics.summaries(self._record_calculations._cursors))
        frame_notices = tuple((cursor.source_name, notice) for cursor in self._record_calculations._cursors
                              for notice in cursor.frame_format_notices)
        analysis_outcome=self._record_calculations.analysis_outcome()
        _reserve_owned_ram(self, 65536 + 32 * _metadata_bytes((plan.metadata,plan.presets,diagnostic_inputs,frame_notices,analysis_outcome,plan.aggregations)), '_metadata_cost')
        self._metadata = RunMetadata(run_id=self._run_id, input_identity=None,
            plan_hash=plan.identity, backend=plan.execution.backend, config_version=plan.config_version,
            source_time_interpretation='original-record-times',
            session_boundaries=(), session_ids=(plan.dataset.session_id,),
            started_at=self._started_at, parsing_policy='requested-fields-and-driver-times',
            device_label=plan.metadata.get('device_label', 'pending'), retain_work=plan.diagnostics.retain_work,
            threshold_durations=self._record_calculations.threshold_summaries(),input_diagnostics=diagnostic_inputs,
            frame_format_notices=frame_notices,analysis_outcome=analysis_outcome,aggregation_definitions=plan.aggregations,
            limitations=tuple(f'{source}.{notice.alias}: DBC声明CAN FD，按显式经典CAN定位读取；原帧未转换'
                              for source, notice in frame_notices),
            trace_requested=plan.diagnostics.trace,integrity_diagnostics=plan.diagnostics.integrity)

    def _adopt_cleanup(self, exc):
        """接管当前工厂明确移交的最高资源所有者，保留失败后可重试关闭的责任。

        参数: exc为原构造错误。返回: None。异常: 原属性访问错误；不凭字段猜测内层资源。
        """
        if self._constructing == '_record_calculations':
            owner = getattr(exc, 'record_session_cleanup_owner', None)
            if owner is not None and self._record_calculations is None:
                self._record_calculations = owner
        elif self._constructing in ('_result', '_spool'):
            result = getattr(exc, 'analysis_result_cleanup_owner', None)
            if result is not None:
                self._result, self._spool = result, None
            else:
                spool = getattr(exc, 'result_spool_cleanup_owner', None)
                if spool is not None:
                    self._spool = spool

    def _diagnose(self, exc):
        """在本次已取得的最终暂存标失败，诊断清理副错只附note。

        参数: exc为实际原错误。返回: None。异常: 不替换主异常，不接触未取得或已有根。
        """
        spool = self._spool if self._result is None else self._result.spool
        if spool is not None and spool.path is not None:
            try:
                if self._result is not None:
                    self._result.status = 'cancelled' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failed'
                spool._fail(exc)
            except BaseException as diagnostic:
                exc.add_note(f'运行会话失败诊断附加失败: {type(diagnostic).__name__}')

    @staticmethod
    def _require_closed(owner):
        """检查真实close完成及已知费用槽，不让旧提前closed掩盖尚持有资源。

        参数: owner为刚关闭的实际对象。返回: None。异常: AnalysisError为未完成关闭；
            旧深层缺口只据真实槽拒绝，不推测、转移或自行释放未知余额。
        """
        if not (getattr(owner, 'closed', False) or getattr(owner, '_closed', False)):
            raise AnalysisError('内部资源close返回但没有完成关闭')
        for slot in ('_held_cost', '_input_cost', '_state_cost', '_pending_cost', '_cost'):
            if getattr(owner, slot, 0):
                raise AnalysisError(f'内部资源关闭仍持有{slot}，需恢复后由实际owner处理')

    def _close_slot(self, slot):
        """关闭一个最高owner并在成功后才清槽。参数: slot责任名。返回: None。异常: 原关闭错误。
        """
        owner = getattr(self, slot)
        if owner is not None:
            owner.close()
            self._require_closed(owner)
            setattr(self, slot, None)


    def _close_inputs(self):
        """关闭记录执行树，失败时保留其最高所有者供调用方重试。

        参数: 无。返回: None。异常: 原关闭错误；不越过尚未关闭的依赖资源。
        """
        self._close_slot('_record_calculations')

    def _clear_contracts(self):
        """释放本会话借用的有限声明，随后才退还覆盖它们的预算。

        参数: 无。返回: None。异常: 无；不修改调用方计划或已经移交的结果。
        """
        self._requirements = None
        self._plan = self._metadata = self._run_id = self._started_at = None

    def _release_costs(self):
        """逐笔释放本owner真实槽，覆盖释放前后取消。参数: 无。返回: None。异常: 原预算错误。
        """
        for slot in ('_metadata_cost', '_fixed_cost'):
            _release_owned_ram(self, getattr(self, slot), slot)

    def _assert_owned_balance(self):
        """检查执行树已关闭且账本只含本会话及待移交结果费用。

        参数: 无。返回: None。异常: AnalysisError表示真实资源或费用残留，不靠差额退费。
        """
        if self._record_calculations is not None:
            raise AnalysisError('成功前仍有未关闭内部资源')
        expected = self._held_cost
        if self._artifact_exports is not None:
            expected += self._artifact_exports.owned_ram
        if self._result is not None:
            expected += self._result._held_cost + self._result.spool._held_cost
            if self._result._artifact_exports is not None and self._result._artifact_exports is not self._artifact_exports:
                expected += self._result._artifact_exports.owned_ram
        elif self._spool is not None:
            expected += self._spool._held_cost
        if self._budget.ram_bytes != expected:
            raise AnalysisError('会话实际账本与已登记所有者费用不一致')

    def close(self):
        """可重试关闭本次最高资源和协调费用，保留文件及已移交结果。

        参数: 无。返回: None，成功后幂等。异常: 原句柄、预算或取消错误附
            runner_cleanup_owner；不会用共享余额抵销旧工厂遗失的费用。
        """
        if self._closed:
            return
        self._closing = True
        try:
            # 可选固定编码借用生产者和spool，先解除其引用和真实费用；若失败，
            # 下层保持可达，恢复后从同一sink槽继续关闭，不越级退费。
            # 未移交result拥有最终spool，始终从最高父关闭；失败时不重复关闭内层。
            self._close_slot('_result')
            self._close_slot('_spool')
            self._close_inputs()
            self._close_slot('_artifact_exports')
            self._clear_contracts()
            self._release_costs()
            if self._owns_path and not self._retain_work:
                from ..results.owned_directory import remove_owned_directory
                remove_owned_directory(self._path, self._path_identity)
                self._owns_path = False
            if self._held_cost == 0:
                self._closed = True
        except BaseException as exc:
            self._failed = True
            exc.runner_cleanup_owner = self
            raise
