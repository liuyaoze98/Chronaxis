"""把公共AnalysisRunner的检查、解释和实际分析接到CLI，提供文本和JSON报告。

输入为解析后的命令参数，load_analysis_plan只读取指定JSON/YAML并按配置目录解释来源路径。
validate和explain直接调用同一AnalysisRunner接口，不读取CSV、DBC或旧日志，不建立
运行目录。序列化逐项选择公开报告字段，不遍历任意对象或另做一套配置校验。
报告中的预算和有效期是声明，execution_ready不证明实际输入已核实。
run先检查输出根与独占工作路径，再交给AnalysisRunner运行，在同一结果上write并关闭。
只有真实关闭成功才打印成功摘要；失败保留原原因链和现存产物，不假报回滚。

本模块仅在实际计划命令时加载；CLI帮助与参数错误仍只需要标准库。
"""

import json
from pathlib import Path
import sys

# 这些接口只有计划命令实际执行时才加载；取得AnalysisRunner类不会创建运行会话。
from . import AnalysisRunner, load_analysis_plan
from .planning.checks import PlanValidationError
from .results.errors import AnalysisError


def validation_json(report) -> dict:
    """保留公共校验报告的全部固定字段和未验证警告。

    参数: report为AnalysisRunner.validate返回的ValidationReport。
    返回: 原生JSON字典；元组和只读映射转换为列表和dict，不改变字段含义。
    异常: 接口不符的编程错误原样传播，不靠反射补缺失属性。
    """
    # 显式白名单避免漏掉能力限制，也避免把内部状态或任意元数据输出到控制台。
    return dict(valid=report.valid, errors=list(report.errors), warnings=list(report.warnings),
                capability_status=dict(report.capability_status), execution_ready=report.execution_ready)


def explanation_json(report) -> dict:
    """将依赖、节点后端、历史需求和预算声明完整交给CLI使用者。

    参数: report为AnalysisRunner.explain返回的ExplainReport。
    返回: 固定JSON字典，节点保持原顺序，plan_identity保持原配置身份。
    异常: 接口不符的编程错误原样传播；不推算实测峰值或来源观测范围。
    """
    # 各节点只含原公开报告字段；state_driver与数值后端沿原报告区别显示。
    nodes = [dict(node_id=node.node_id, node_type=node.node_type, dependencies=list(node.dependencies),
                  unit=node.unit, backend=node.backend) for node in report.nodes]
    requirements = report.input_requirements
    scopes = ([] if requirements is None else [dict(source=item.source, input_check=item.input_check,
        time_scope=item.time_scope, required_aliases=list(item.required_aliases),
        decode_frame_ids=list(item.decode_frame_ids), reasons=list(item.reasons)) for item in requirements.sources])
    if report.intervals is not None and requirements is not None:
        for item,scope in zip(requirements.sources,scopes):
            scope['active']=item.active
    output = dict(source_execution=[dict(item) for item in report.source_execution],
                input_requirements=scopes, validation=validation_json(report.validation), plan_identity=report.plan_identity,
                source_names=list(report.source_names), nodes=nodes,
                history_ns=dict(report.history_ns), budget=dict(report.budget))
    # 解释已解析的间隔声明，不推测DBC周期或输出第二时间轴。
    if report.intervals is not None:
        choices = {}
        for name, choice in report.intervals.resolved:
            choices[name] = dict(mode=choice.mode, step_ns=choice.step_ns, driver=choice.driver)
        output['intervals'] = choices
    if report.diagnostics is not None:
        output['diagnostics'] = dict(trace=report.diagnostics.trace,
            integrity=report.diagnostics.integrity, retain_work=report.diagnostics.retain_work)
    return output


def run_static(arguments) -> int:
    """只加载配置并输出共享AnalysisRunner报告，不触碰来源或创建分析产物。

    参数: arguments含command=validate或explain、plan路径和可选backend覆盖。
    返回: 0表示静态有效且当前有执行路径，2表示报告中存在能力错误。
    异常: 配置加载、依赖、JSON输出或取消错误向主CLI传播，由统一边界处理。
    副作用: 只读取计划JSON、写stdout；来源路径按load_analysis_plan解释，不按CLI另猜。
    """
    # 只构建静态计划和无状态AnalysisRunner；这些步骤不验证来源文件是否存在或可读。
    plan = load_analysis_plan(arguments.plan)
    runner = AnalysisRunner(backend=arguments.backend)
    # 两种命令使用相同有效计划，覆盖后端不会伪造新的配置或输入身份。
    if arguments.command == 'validate':
        validation = runner.validate(plan, process_count=arguments.process_count)
        payload = validation_json(validation)
    else:
        report = runner.explain(plan, process_count=arguments.process_count)
        validation = report.validation
        payload = explanation_json(report)
    # 人读输出复用同一计划及报告；机器格式保持明确字段，不重新解析输入。
    if arguments.format=='json':
        print(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    else:
        from .configuration.explanation import validation_text, explanation_text
        text=(validation_text(plan,validation) if arguments.command=='validate'
              else explanation_text(plan,report,backend_override=arguments.backend))
        print(text)
    return 0 if validation.valid and validation.execution_ready and not validation.errors else 2


def _new_output(arguments) -> Path:
    """在扫描来源前检查可复用输出根、历史目录和冲突工作路径。

    参数: arguments包含output和可选work_dir，由argparse限定为路径文本。
    返回: 绝对输出Path；不创建目录，工作目录实际分配仍归AnalysisRunner。
    异常: FileExistsError或原lstat错误为文件失败；PlanValidationError为Ref或路径冲突。
    """
    output = Path(arguments.output).absolute()
    # 同时检查词法与物理路径，不能借符号链接把新产物写进历史快照。
    candidates = (output,) if arguments.work_dir is None else (output, Path(arguments.work_dir).absolute())
    for path in candidates:
        if any(part.casefold() == 'refprojects' for part in (*path.parts, *path.resolve().parts)):
            raise PlanValidationError('$.cli.output', '运行输出和工作目录不能位于RefProjects')
    if arguments.work_dir is not None:
        work = Path(arguments.work_dir).absolute().resolve()
        destination = output.resolve()
        # AnalysisRunner会先建立work；若它位于output内部，随后发布必因output已存在而失败。
        if work == destination or destination in work.parents:
            raise PlanValidationError('$.cli.work_dir', '工作目录不能等于输出目录或位于输出目录内部')
    for path in candidates:
        try:
            # 工作路径必须新建；输出允许已有目录，悬空链接不允许。
            # 最终输出安装的竞态仍由原write检查，运行会话也保留原工作目录检查。
            path.lstat()
        except FileNotFoundError:
            continue
        if path == output and path.is_dir() and not path.is_symlink():
            continue
        raise FileExistsError('工作目录须新建，输出目标须为目录：' + str(path))
    return output


def _cause_chain(error) -> tuple:
    """取得有限且不重复的真实cause链，供诊断和致命异常判断共用。

    参数: error为实际异常。返回: 最多16个原异常对象，保持外层到根因顺序。
    异常: 无主动异常；不访问任意业务对象，不解析日志或重建错误。
    """
    chain, seen = [], set()
    current = error
    # 防御外部异常的cause循环；不因诊断无限遍历而阻塞清理或退出。
    while current is not None and id(current) not in seen and len(chain) < 16:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__
    return tuple(chain)


def run_analysis(arguments) -> int:
    """复用真实分析和发布，成功关闭所有结果资源后才报告completed。

    参数: arguments含plan、output、可选backend及work_dir；输出目录可复用。
    返回: 成功0；已知分析/发布/关闭失败1，并说明输出可能已经发布。
    异常: 配置/路径错误交主CLI分类；取消原样传播；MemoryError及已知编程错误
        的直接或AnalysisError原因链继续抛出，不伪装成普通业务错误。
    副作用: AnalysisRunner建立专用暂存并读来源，write在输出根新增本次文件；不删除已有产物。
    """
    plan = load_analysis_plan(arguments.plan)
    output = _new_output(arguments)
    runner = AnalysisRunner(backend=arguments.backend)
    manifest = None
    try:
        # 结果拥有其真实仓和资源；write不重新运行来源，退出上下文完成实际close。
        with runner.run(plan, work_dir=arguments.work_dir, process_count=arguments.process_count) as result:
            manifest = result.write(output)
            summary = dict(status=manifest.status, run_id=manifest.run_id,
                plan_identity=result.metadata.plan_hash, backend=result.metadata.backend,
                output=str(manifest.output_dir), manifest=str(manifest.manifest_path),
                row_counts=dict(manifest.row_counts), device_label=result.metadata.device_label)
            if result.metadata.analysis_outcome is not None:
                summary['analysis_outcome']=result.metadata.analysis_outcome.to_dict()
            if result.table_format == 'readable_csv':
                from .results.readable_format import outcome_messages
                summary['result_files'] = [path.name for path in manifest.output_files]
                summary['result_messages'] = outcome_messages(result.metadata.analysis_outcome)
    except (AnalysisError, OSError) as error:
        chain = _cause_chain(error)
        # AnalysisRunner可能包装构造内存/编程错误；保留该公开异常及原cause，不归类普通失败。
        if any(isinstance(item, (MemoryError, TypeError, AttributeError, AssertionError, NameError)) for item in chain):
            raise
        causes = ' <- '.join(type(item).__name__ + ': ' + str(item).replace('\n', ' ') for item in chain)
        completed = manifest or next((getattr(item, 'completed_manifest') for item in chain
                                      if getattr(item, 'completed_manifest', None) is not None), None)
        if completed is not None:
            print('结果已发布，清单：' + str(completed.manifest_path) + '；收尾失败：' + causes, file=sys.stderr)
            return 1
        # 目录可能已安装后才发生close错误，非零退出不证明输出被撤销。
        print('分析或发布失败（输出可能已发布，请核对目标目录 ' + str(output) + '）：' + causes,
              file=sys.stderr)
        return 1
    # 本行在with真实退出之后，不能提前把analysis_complete当成发布和关闭成功。
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    return 0
