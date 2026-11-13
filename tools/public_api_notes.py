"""新增公开子模块的双语用法说明；签名和参数默认值另取自固定产品基线。

说明集中于真实用途、输入、返回和失败政策，不代替接口反射，也不增加根包导出。
"""

COMMON = {
    'name': ('在本次注册中唯一、且不与内置操作重名的表达式标识符。', 'Expression identifier, unique in the registry and distinct from built-in operations.'),
    'version': ('非空的实现版本；实现行为变化时由宿主递增。', 'Nonempty implementation version; the host must change it when implementation behavior changes.'),
    'input': ('一个ValueSpec端口，声明数值dtype与已登记单位；不接受BOOL或ENUM。', 'One ValueSpec numeric port with a registered unit; BOOL and ENUM are not accepted.'),
    'inputs': ('非空ValueSpec元组，按函数的位置参数顺序声明dtype与单位。BOOL端口单位为1，ENUM需先取编码。', 'Nonempty tuple of ValueSpec ports in positional argument order. BOOL uses unit 1; extract enum codes before calling.'),
    'output': ('输出ValueSpec端口；声明回调结果的dtype与单位。', 'Output ValueSpec port declaring the callback result dtype and unit.'),
    'state_bytes': ('状态预留费用，非负整数，单位byte；宿主按实际状态需求声明。', 'Nonnegative integer state reservation in bytes, declared by the host for actual state needs.'),
    'mergeable': ('True要求状态实现merge(other)，False不承诺可合并。', 'True requires state.merge(other); False makes no mergeability promise.'),
    'history_ns': ('必须显式填写正int64回看宽度；单位ns，按所选实际或周期口径计量。默认0不是有效声明。', 'Explicit positive int64 lookback width in ns, measured using the selected actual or periodic interval mode. The default 0 is not a valid declaration.'),
    'interval_modes': ('本实现支持的actual/fixed/dbc非空、无重复元组；不要声明尚未正确实现的权重口径。', 'Nonempty unique tuple drawn from actual/fixed/dbc. Declare only the weighting modes implemented correctly.'),
}

# 未写Python注解的公开参数，依据实际参数检查维护展示类型；签名仍保留源码原貌。
PARAMETER_TYPES = {
    'fast.batch.run_batch': {
        'plan_path': 'str | pathlib.Path', 'output': 'str | pathlib.Path',
        'process_count': 'int | None', 'cancel_event': 'threading.Event | None', 'total': 'bool',
    },
    'ExtensionRegistry': {
        'functions': 'tuple[FunctionSpec, ...]', 'reductions': 'tuple[ReductionSpec, ...]',
        'transforms': 'tuple[TransformSpec, ...]',
    },
}

NOTES = {
 'fast.run': {
  'summary': ('高性能积分器：一个会话管理一个或多个ASC/BLF分卷，按确定顺序累计同帧贡献并发布一次汇总。', 'High-performance integrator: one session accumulates same-frame contributions from one or more ASC/BLF volumes in a deterministic order and publishes one summary.'),
  'parameters': {
   'config': ('YAML/JSON分析配置路径；一个来源的paths列出同一会话分卷，内部路径相对配置文件。仅支持fast当前帧数值子集。', 'YAML/JSON analysis path. One source lists all session volumes in paths; relative input/DBC paths resolve against the configuration. Only the fast current-message numeric subset is supported.'),
   'output': ('结果目录，可已存在；使用本次时间标记文件，不覆盖既有结果。', 'Result directory, which may exist. Timestamped output files preserve earlier results.'),
   'process_count': ('可选正整数工作进程上限，不含主进程；None沿用execution.process_count，默认1内联。超过文件数时按文件数限制，拒绝bool，不修改原配置。', 'Optional positive integer worker limit, excluding the main process. None uses execution.process_count, default 1 inline. Capped at file count; booleans are rejected and configuration is unchanged.'),
   'work_dir': ('可选暂存父目录，None使用系统临时目录；本次创建的私有暂存完成或失败后清理。', 'Optional parent directory for temporary contributions. None uses system temporary storage. This invocation removes its private temporary files after completion or failure.'),
   'cancel_event': ('可选带is_set()的取消事件，例如threading.Event；set()请求停止调度并清理，run抛InterruptedError，不发布成功汇总。', 'Optional cancellation event with is_set(), such as threading.Event. set() requests cancellation and cleanup; run raises InterruptedError without publishing a successful summary.')},
  'returns': ('pathlib.Path：本次完成清单。inputs列出全部文件，outputs列出结果表；每项独立判断空值/有效零，某分卷无目标不使其他有效贡献失效。', 'pathlib.Path to the completion manifest. inputs lists every file and outputs names the result table. Missing values and valid zeros are determined per calculation across the session.'),
  'raises': ('PlanValidationError为配置不合法；ValueError为非法覆盖或数值/协议问题；资源超额、worker故障可抛RuntimeError；取消抛InterruptedError；文件和发布错误可抛OSError。任一必需文件失败均不发布正常会话结果。会话异常保留原类型；清理未完成时，原异常可能带fast_session_cleanup_owner，排除资源故障后调用该对象close，不必分别关闭子对象。该属性不保证存在，也可能在后续重试后指向已关闭对象。', 'PlanValidationError for configuration errors; ValueError for invalid overrides or numeric/protocol errors; RuntimeError for resource or worker failures; InterruptedError for cancellation; OSError for file/publication failures. Any required-file failure prevents a successful session result. Session errors keep their original type. If cleanup remains incomplete, the original exception may expose fast_session_cleanup_owner; resolve the resource fault and call that object\'s close(), without separately closing its children. The attribute is optional and may refer to an object closed by a later retry.'),
  'behavior': ('读取配置/DBC及分卷；工作进程求单帧贡献，主进程逐条累计。单进程内联；time_order多文件需暂存。Windows多进程调用须置于`if __name__ == "__main__":`保护中，清单最后发布。', 'Read configuration, DBC and volumes. Workers evaluate individual contributions; the main process accumulates them in order. One worker runs inline; multi-file time_order requires staging. Protect multiprocessing calls with `if __name__ == "__main__":` on Windows. Publish the manifest last.')},
 'fast.batch.run_batch': {
  'summary': ('并行执行相互独立的高性能积分任务；连续来源paths不能借此拆成独立文件。', 'Run independent high-performance integration jobs in parallel. Do not use this to split paths that belong to one continuous source.'),
  'parameters': {
   'plan_path': ('str或Path：batch_version为1的jobs或template批量配置路径。每个任务都需满足fast能力范围。', 'str or Path to a batch_version 1 jobs or template plan. Every job must satisfy the fast capability subset.'),
   'output': ('str或Path：批量输出目录，可以复用；任务输出与批量报告使用本次独占名称。', 'str or Path to a reusable batch output directory. Job outputs and batch reports use names allocated exclusively for this run.'),
   'process_count': ('正整数或None。None沿用批量配置；显式正整数覆盖进程上限。布尔值不是合法计数。', 'Positive integer or None. None uses the batch plan setting; an integer overrides its process limit. Boolean values are not valid counts.'),
   'cancel_event': ('`threading.Event`或`None`。调用`set()`请求取消：停止派发尚未启动的任务，并通知在途fast任务停止；协作退出超过5秒时启动进程回收。已完成任务可保留completed状态，其他任务以报告中的status、error_type和error_message为准。只有is_set()方法的其他对象不被接受。', '`threading.Event` or `None`. Call `set()` to stop pending dispatch and request running fast jobs to stop. After a five-second cooperative grace period, process cleanup begins. Already finished jobs may remain completed; inspect each job\'s status, error_type and error_message. Other objects merely providing is_set() are not accepted.'),
   'total': ('布尔值，True请求同模板且定义一致的全批总量；按计算项完整性判定，不把缺失值当0。默认不额外汇总。', 'Boolean. True requests totals for a same-template batch with matching definitions. Completeness is checked per calculation; missing values are not zero. No extra total is computed by default.')},
  'returns': ('pathlib.Path：本次批量报告路径。报告可包含失败或未启动任务；返回路径不代表每个任务成功，须检查报告。', 'pathlib.Path to the batch report. It can contain failed or unstarted jobs; returning a path does not mean every job succeeded. Inspect the report.'),
  'raises': ('参数或组合错误直接抛出，不返回正常批量报告：total不是bool时抛TypeError；process_count不是正原生int（包括bool）时抛ValueError；cancel_event不是threading.Event或None时抛TypeError；jobs配置请求total=True时抛ValueError，只有同一template展开且计算定义一致的独立文件支持总计。total类型在加载配置前检查，其余覆盖值和组合在配置准备后、任务派发前检查。\n\n配置解析或fast能力检查失败抛PlanValidationError。已派发任务的普通失败记录在报告jobs的status、error_type和error_message中，按fail_fast决定是否继续派发；返回报告路径不代表全部成功。\n\n通信、调度、清理及报告发布等基础设施异常继续传播，可能通过异常的batch_report附带已保存报告，但启动前或报告发布错误不保证有该属性。worker构造期间中断且清理未完成时，原异常还可带batch_worker_cleanup_owner；该worker可能不在报告任务中，需要对实际存在的恢复对象单独close。', 'Parameter and combination errors raise directly instead of returning a normal batch report: TypeError for a non-bool total; ValueError for process_count that is not a positive native int, including bool; TypeError for cancel_event other than threading.Event or None; ValueError for total=True with jobs. Totals require independent files expanded from one template with matching calculation definitions. The total type is checked before loading configuration; the other overrides and combinations are checked after configuration preparation and before dispatch.\n\nConfiguration parsing or fast-capability failures raise PlanValidationError. Ordinary failures in dispatched jobs appear in report.jobs with status, error_type, and error_message; fail_fast controls further dispatch. Returning a report path does not mean every job succeeded.\n\nCommunication, scheduling, cleanup, and report-publication errors propagate. An exception may carry a saved batch_report, but pre-dispatch and publication failures do not guarantee that attribute. If worker construction is interrupted and cleanup remains incomplete, the original exception may also expose batch_worker_cleanup_owner. That unfinished worker may not belong to a report job; close an available recovery object separately.'),
  'behavior': ('创建工作进程、读取每个任务输入并写报告；内部关闭批量资源。Windows脚本必须在`if __name__ == "__main__":`保护内调用。', 'Starts worker processes, reads job inputs, writes reports, and closes batch resources internally. On Windows, call inside an `if __name__ == "__main__":` guard.')},
 'ExtensionRegistry': {
  'summary': ('构造不可变宿主扩展注册表；创建计划与执行计划须传同一个注册实例。配置只引用已注册名称，不自动导入Python模块。', 'Construct an immutable host-extension registry. Pass the same instance when building and running the plan. Configuration references registered names; it does not import Python modules.'),
  'parameters': {
   'functions': ('FunctionSpec元组；省略为空，表示没有自定义逐点函数。', 'Tuple of FunctionSpec declarations; empty means no custom pointwise functions.'),
   'reductions': ('ReductionSpec元组；省略为空，表示没有自定义样本归约。', 'Tuple of ReductionSpec declarations; empty means no custom sample reductions.'),
   'transforms': ('TransformSpec元组；省略为空，表示没有自定义时序变换。', 'Tuple of TransformSpec declarations; empty means no custom temporal transforms.')},
  'returns': ('新ExtensionRegistry。functions/reductions/transforms为只读名称映射；identity是声明及实现版本的摘要。', 'New ExtensionRegistry. Its functions/reductions/transforms are read-only name mappings; identity is a digest of declarations and implementation versions.'),
  'raises': ('容器不是tuple或条目类型错误时抛TypeError；三类之间名称重复时抛ValueError。', 'TypeError for non-tuple containers or incorrectly typed entries; ValueError for duplicate names across categories.'),
  'behavior': ('只登记声明，不执行回调或创建运行状态；同次运行不能替换注册表。', 'Registers declarations without executing callbacks or creating runtime state. Do not replace the registry within a run.')},
 'FunctionSpec': {
  'summary': ('声明无历史的逐点函数，回调impl(args, resources)返回同形状ScalarValue或NumericArray。', 'Declare a stateless pointwise function. impl(args, resources) returns ScalarValue or NumericArray with the matching shape.'),
  'parameters': {**{key: COMMON[key] for key in ('name','version','inputs','output')},
   'reference': ('逐点实现`impl(args, resources)`。args按inputs声明顺序提供ScalarValue元组，返回一个符合output的ScalarValue；resources用于申请/释放临时内存。None表示不支持此后端；两个后端至少提供一个，不自动回退。', 'Point implementation `impl(args, resources)`. args is a tuple of ScalarValue objects in inputs order; return one ScalarValue matching output. resources reserves/releases temporary memory. None disables this backend; provide at least one backend, with no automatic fallback.'),
   'numpy': ('数组逐点实现`impl(args, resources)`。args是按inputs排列的NumericArray元组，返回同长度、符合output的NumericArray；只接收到全部必要输入有效的行。None表示不支持numpy，不以reference替代。', 'Array point implementation `impl(args, resources)`. args is a tuple of NumericArray objects in inputs order; return a NumericArray of matching length and output type. Only rows with all required inputs valid are passed. None disables numpy; reference is not substituted.')},
  'returns': ('不可变FunctionSpec声明。', 'Immutable FunctionSpec declaration.'),
  'raises': ('名称、端口、版本或回调声明不合法时拒绝构造；ValueError或TypeError保留具体原因。', 'Invalid names, ports, versions, or implementations reject construction with ValueError or TypeError and a specific reason.'),
  'behavior': ('必要输入无效时传播无效；未选where分支不执行。注册只检查声明，不调用计算实现。', 'Invalid required inputs propagate invalidity; an unselected where branch is not executed. Registration checks declarations without calling the implementation.')},
 'ReductionSpec': {
  'summary': ('声明对真实样本归约的工厂factory(resources)。每个统计范围独立创建状态。', 'Declare a sample-reduction factory, factory(resources). Each statistical scope gets its own state.'),
  'parameters': {**{key: COMMON[key] for key in ('name','version','input','output','state_bytes','mergeable')},
   'reference': ('状态工厂`factory(resources)`，每个统计范围创建一个对象。对象必须提供consume(values)、finalize()、cancel()和close()；values是有效ScalarValue元组，finalize返回符合output的ScalarValue。mergeable=True还须merge(other)。None表示不支持reference，两个后端至少提供一个。', 'State factory `factory(resources)`, creating one object per reduction scope. It must provide consume(values), finalize(), cancel() and close(); values is a tuple of valid ScalarValue objects and finalize returns a ScalarValue matching output. mergeable=True also requires merge(other). None disables reference; provide at least one backend.'),
   'numpy': ('状态工厂`factory(resources)`，必需方法与reference相同；consume(values)接收有效NumericArray，finalize()仍返回ScalarValue。None表示不支持numpy，不自动使用reference工厂。', 'State factory `factory(resources)`, with the same required methods as reference. consume(values) receives a valid NumericArray; finalize() still returns ScalarValue. None disables numpy; no reference factory fallback is used.')},
  'returns': ('不可变ReductionSpec声明。', 'Immutable ReductionSpec declaration.'),
  'raises': ('非法端口、后端、state_bytes或mergeable抛ValueError/TypeError；输入与输出均须为数值。', 'ValueError/TypeError for invalid ports, backends, state_bytes, or mergeable. Both input and output must be numeric.'),
  'behavior': ('状态consume接收选定真实样本，finalize返回ScalarValue；cancel和close均为必需方法，分别处理取消与资源释放。mergeable=True须实现merge(other)。', 'State.consume receives selected real samples and finalize returns ScalarValue. Both cancel and close are required, for cancellation and resource release respectively. mergeable=True requires merge(other).')},
 'TransformSpec': {
  'summary': ('声明有状态网格变换工厂factory(resources)，advance(time_ns, window_ns, values, weights_ns)计算窗口值。', 'Declare a stateful grid-transform factory, factory(resources). advance(time_ns, window_ns, values, weights_ns) calculates each window value.'),
  'parameters': {**{key: COMMON[key] for key in ('name','version','input','output','state_bytes','history_ns','interval_modes')},
   'reference': ('状态工厂`factory(resources)`，每会话创建对象，必须提供advance(time_ns, window_ns, values, weights_ns)、cancel()、close()。advance接收实际输出时刻、窗口计量宽度、有效ScalarValue元组及对应时长权重，返回符合output的ScalarValue；时间数值单位ns。None表示不支持reference，两个后端至少提供一个。', 'State factory `factory(resources)`, creating one object per session with required advance(time_ns, window_ns, values, weights_ns), cancel() and close(). advance receives the actual output time, measured window width, valid ScalarValue tuple and corresponding duration weights, returning a ScalarValue matching output. Time values use ns. None disables reference; provide at least one backend.'),
   'numpy': ('状态工厂`factory(resources)`，必需方法与reference相同；advance中的values为有效NumericArray，weights_ns为对应时长数组，返回ScalarValue。None表示不支持numpy，不自动使用reference工厂。', 'State factory `factory(resources)`, with the same required methods as reference. advance receives a valid NumericArray as values and a matching duration array as weights_ns, and returns ScalarValue. None disables numpy; no reference factory fallback is used.')},
  'returns': ('不可变TransformSpec声明。', 'Immutable TransformSpec declaration.'),
  'raises': ('非法端口、资源、历史宽度、重复或未知interval_modes抛ValueError/TypeError。输入与输出均须为数值。', 'ValueError/TypeError for invalid ports, resources, history width, or duplicate/unknown interval_modes. Both ports must be numeric.'),
  'behavior': ('每会话创建状态，advance仅接收有效ZOH区间及权重，返回网格时刻ScalarValue；按所声明历史及状态费用使用共享预算，关闭时释放资源。', 'Creates state per session. advance receives valid zero-order-hold spans and weights and returns a ScalarValue at the grid time. History and state use the shared budget; close releases resources.')},
}


def render_note(item, source_page, language):
    """渲染双语说明和共享参数事实。源码定位由调用方从基线页保留。"""
    import re
    index = 1 if language == 'en' else 0
    notes = NOTES[item['name']]
    module, symbol = item['import_module'], item['import_name']
    out = [f'# {module}.{symbol}\n\n`from {module} import {symbol}`\n\n',
           f'<a id="api-{item["qualified"].replace(".", "-")}"></a>\n## `{symbol}`\n\n',
           notes['summary'][index]+'\n\n', f'```python\n{symbol}{item["signature"]}\n```\n\n',
           '| Name | Type | Required | Default | Purpose |\n|---|---|---|---|---|\n' if index else '|名称|类型|必填|默认值|用途|\n|---|---|---|---|---|\n']
    if set(notes['parameters']) != {p['name'] for p in item['parameters']}:
        raise ValueError('公开API参数说明与当前签名不一致：'+item['name'])
    for parameter in item['parameters']:
        name = parameter['name']
        required = ('Yes' if parameter['required'] else 'No') if index else ('是' if parameter['required'] else '否')
        default = parameter['default'] if parameter['default'] is not None else ('No default' if index else '无默认值')
        typename = parameter['type'] or PARAMETER_TYPES.get(item['name'], {}).get(name)
        if not typename:
            # 仅检查由NOTES维护的公开页；不要求内部或自动生成方法补造类型。
            raise ValueError('公开API参数缺少已核对类型：'+item['name']+'.'+name)
        values = (f'`{name}`', typename, required, default, notes['parameters'][name][index])
        out.append('|'+ '|'.join(v.replace('|', '&#124;') for v in values)+'|\n')
    for key, labels in (('returns',('返回','Returns')),('raises',('异常','Raises')),('behavior',('执行与资源','Execution and resources'))):
        out.append(f'\n### {labels[index]}\n\n{notes[key][index]}\n')
    if item['name'] in ('FunctionSpec','ReductionSpec','TransformSpec'):
        out.append('\n'+('Declare ports with `from chronaxis.extensions import ValueSpec` and `from chronaxis.core.types import SignalDType`. For example, `ValueSpec(SignalDType.FLOAT64, "A")` declares a numeric current port.\n' if index else '端口通过`from chronaxis.extensions import ValueSpec`与`from chronaxis.core.types import SignalDType`声明。例如`ValueSpec(SignalDType.FLOAT64, "A")`表示浮点电流端口。\n'))
        out.append(f'\n### `require_backend`\n\n```python\n{symbol}.require_backend(backend)\n```\n\n')
        out.append(('Inherited method: backend is required and must be reference or numpy. Returns that registered callback/factory; raises ValueError for an unknown or unsupported backend.\n' if index else '继承的公开方法：必填backend只能为reference或numpy。返回对应已登记回调或工厂；未知后端或缺少该后端实现抛ValueError。\n'))
    out.append('\n'+('[Worked host example](../host-extensions.md)' if index else '[完整宿主示例](../host-extensions.md)')+'\n' if item['name'] not in ('fast.run','fast.batch.run_batch') else '\n'+('[High-performance integrator tutorial](../fast-energy.md)' if index else '[高性能积分器教程](../fast-energy.md)')+'\n')
    out.extend('\n'+m.group(0)+'\n' for m in re.finditer(r'(?m)^源码：.*$',source_page))
    return ''.join(out)
