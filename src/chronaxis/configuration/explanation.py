"""把已验证的分析声明讲成人可阅读的步骤；不加载来源、不展开运行时数据。

文本与JSON报告使用同一计划和能力报告。这里仅翻译已知术语、格式化精确时间，
并从原始声明区分显式设置与默认设置，不建立另一套配置默认值或执行规则。
"""
from collections.abc import Mapping


OPERATIONS={
    'integral':'积分（按前值保持累计）',
    'sample_mean':'样本均值（每个有效样本权重相同）',
    'time_weighted_mean':'时间加权均值（按有效持续时间加权）',
    'sample_minimum':'有效样本最小值','sample_maximum':'有效样本最大值',
    'min_time':'有效时间区间内最小值','max_time':'有效时间区间内最大值',
    'duration':'条件成立的累计时长','select':'选择符合条件的记录',
}
RULES={'condition_duration':'条件持续成立','rising_edge':'由假变真的上升沿',
       'falling_edge':'由真变假的下降沿','start_only':'触发后保留固定窗口',
       'window_delta':'回看窗口内变化量','debounce':'条件去抖','hysteresis':'进入与退出使用不同条件',
       'start_end':'开始条件启动、结束条件停止'}
SOURCES={'memory':'配置中的内存数据','signal_csv':'已解码信号CSV',
         'can_blf':'CAN二进制BLF','can_asc':'CAN文本ASC','asc_or_blf':'CAN连续ASC/BLF','raw_can_csv':'原始CAN帧CSV'}


def time_text(nanoseconds):
    """无损显示纳秒时长。参数: 整数或None。返回: 带单位文本。异常: 无。"""
    if nanoseconds is None:
        return '未设置'
    for divisor,unit in ((10**9,'s'),(10**6,'ms'),(1000,'us')):
        if nanoseconds and nanoseconds%divisor==0:
            return str(nanoseconds//divisor)+unit
    return str(nanoseconds)+'ns'


def _declared(plan,*parts):
    """检查原声明是否包含字段。参数: 计划/路径。返回: bool。异常: 无；不取文件默认值。"""
    current=plan.raw_config
    for part in parts:
        if isinstance(current,Mapping) and part in current:
            current=current[part]
        elif type(current) is tuple and type(part) is int and 0<=part<len(current):
            current=current[part]
        else:
            return False
    return True


def _setting(plan,label,value,*parts):
    """显示实际生效值及其来源。参数: 计划/标签/值/路径。返回: 文本。异常: 无。"""
    if type(value) is bool:
        value='开启' if value else '关闭'
    source='配置指定' if _declared(plan,*parts) else '默认'
    return f'{label}={value}（{source}）'


def _scope(value):
    """解释计算/输出范围。参数: 已校验范围文本。返回: 中文及具体ID。异常: 无。"""
    if value=='session':
        return '整个会话'
    prefix,_,identifier=value.partition(':')
    return ('每个事件 ' if prefix=='event' else '每个窗口片段 ')+identifier


def _validation_lines(validation):
    """保留报告中全部错误与限制。参数: ValidationReport。返回: 文本行。异常: 无。"""
    lines=['静态检查通过：当前声明有可用执行路径。' if validation.valid and validation.execution_ready
           else '静态检查未通过：请修正以下问题。']
    lines.extend('错误：'+message for message in validation.errors)
    lines.append('此检查尚未读取日志、信号表或DBC；未验证实际字段、数据覆盖和内存峰值。')
    lines.extend('提示：'+message for message in validation.warnings)
    return lines


def validation_text(plan,validation):
    """生成简短校验说明。参数: 已加载计划/同次报告。返回: 多行文本。异常: 无。"""
    return '\n'.join([f'分析 {plan.dataset.dataset_id}：{len(plan.sources)}个来源，'
        f'{len(plan.signals)}个信号，{len(plan.rules)}个事件规则，'
        f'{len(plan.calculations)+len(plan.message_calculations)}个计算项。',
        *_validation_lines(validation)])


def _rule_lines(plan):
    """说明事件、窗口和请求响应的有效声明。参数: 计划。返回: 文本行。异常: 内部模型不符。"""
    lines=[]
    rule_indices={item['name']:index for index,item in enumerate(plan.raw_config.get('rules',()))}
    for rule in plan.rules:
        index=rule_indices.get(rule.rule_id)
        line=f'  {rule.rule_id}：{RULES[rule.rule_type]}；条件 {rule.condition.text}'
        if rule.minimum_duration_ns is not None:
            line+=('；持续严格超过 ' if rule.duration_comparison == '>' else '；至少持续 ')+time_text(rule.minimum_duration_ns)
            line+='；统计从'+('首次成立' if rule.selection_origin=='onset' else '持续确认')+'时刻开始'
        if rule.window_duration_ns is not None:
            line+='；固定窗口 '+time_text(rule.window_duration_ns)
        if rule.exit_condition is not None:
            line+='；退出条件 '+rule.exit_condition.text
        if rule.stability is not None:
            line+='；进入稳定 '+time_text(rule.stability.enter_ns)+'，退出稳定 '+time_text(rule.stability.exit_ns)
        if rule.window_delta is not None:
            spec=rule.window_delta
            line+=f'；回看 {time_text(spec.window_ns)}，门槛 {spec.threshold}，方向 {spec.direction}，单调约束 {spec.monotonic}'
        if rule.start_end is not None:
            line+='；等待上限 '+('不限制' if rule.start_end.timeout_ns is None else time_text(rule.start_end.timeout_ns))
        # 开始/结束规则的首次策略存于专用规格；活动和稳定性规则没有该配置项。
        if rule.rule_type not in ('condition_duration','debounce','hysteresis'):
            emit=rule.start_end.emit_initial if rule.start_end is not None else rule.emit_initial
            setting=_setting(plan,'首次已知条件触发',emit,'rules',index,'emit_initial')
            line+='；'+(setting if index is not None else setting.replace('（默认）','（由预设展开）'))
        lines.append(line)
    for window in plan.windows:
        merge={'none':'分别保留','overlap':'合并重叠片段','overlap_and_adjacent':'合并重叠或相邻片段',
               'exit_delay':'按退出延迟合并'}[window.merge]
        lines.append(f'  窗口 {window.window_id}：来自事件 {window.event}，向前 {time_text(window.pre_ns)}，'
            f'向后 {time_text(window.post_ns)}，{merge}，退出延迟 {time_text(window.exit_delay_ns)}')
    for sequence in plan.sequences:
        lines.append(f'  序列 {sequence.sequence_id}：请求 {sequence.start_rule} → 响应 {sequence.response_rule}；'
            f'允许延迟 [{time_text(sequence.min_delay_ns)}, {time_text(sequence.max_delay_ns)}]（包含两端）；'
            f'最多等待 {sequence.max_pending} 个请求')
    return lines or ['  未声明事件、窗口或请求响应序列。']


def explanation_text(plan,report,*,backend_override=None):
    """按输入→信号→事件→计算→输出说明同一有效计划。参数: 计划/报告/CLI后端。返回: 多行文本。

    异常: 内部接口不符传播，不用默认文案掩盖未实现类型；无输入I/O。
    """
    dataset=plan.dataset
    domain=dataset.domain
    declared_domain=plan.raw_config['dataset'].get('domain',{})
    start=declared_domain.get('start',time_text(domain.start_ns) if domain is not None else '')
    end=declared_domain.get('end',time_text(domain.end_ns) if domain is not None else '')
    lines=[f'分析 {dataset.dataset_id}：对象 {dataset.entity}，会话 {dataset.session_id}',
        '请求范围：'+('整文件（没有时间筛选）' if domain is None else
        f'[{start}, {end})，包含起点，不包含终点'),
        '输入来源：']
    for source in plan.sources:
        config=source.config
        if source.source_type=='memory':
            paths='数据已在配置内声明'
        elif source.source_type=='signal_csv':
            paths='，'.join(map(str,config.paths))
        elif source.source_type=='can_blf':
            paths='，'.join(map(str,config.paths or (config.path,)))
        else:
            paths='，'.join(str(item.path) for item in config.inputs)
        lines.append(f'  {source.name}：{SOURCES[source.source_type]}；{paths}；时间单位 {source.time_unit}，偏移 {time_text(config.offset_ns)}')
        if source.source_type in ('can_blf','can_asc','asc_or_blf','raw_can_csv'):
            lines.append(f'    通道 {config.channel + 1}，DBC {config.dbc_path}（缺省信号声明按需读取元数据，未读取报文）')
        execution=next((item for item in report.source_execution if item['source']==source.name),None)
        if execution is not None:
            merge='按文件顺序接续' if execution['file_merge']=='concatenate' else '按记录时间归并，需要磁盘暂存'
            lines.append(f"    {execution['file_count']}个文件；{merge}；读取子进程上限{execution['read_process_limit']}；保持一个连续会话（未实测输入时间）")
    lines.append('输入信号：')
    signal_paths={}
    for index,raw in enumerate(plan.raw_config.get('signals',())):
        if 'signals' in raw:
            for child_index,child in enumerate(raw['signals']):
                signal_paths[child['name']]=('signals',index,'signals',child_index)
        else:
            signal_paths[raw['name']]=('signals',index)
    source_types={source.name:source.source_type for source in plan.sources}
    for index,item in enumerate(plan.signals):
        signal=item.definition
        # 未读DBC时直说等待周期，不把None展示为没有有效期或假定无限保持。
        validity = ('DBC周期的3倍（运行时确定）' if signal.valid_for_ns is None
                    else time_text(signal.valid_for_ns))
        location=f'{signal.source}.{signal.field}'
        if source_types[signal.source] in ('can_blf','can_asc','asc_or_blf','raw_can_csv'):
            # 人读说明沿用配置通道；内部规范键和机器报告仍保持0基模型合同。
            from ..sources.can_spec import can_field_from_key
            field=can_field_from_key(signal.field)
            location=(f'{signal.source} 通道 {field.channel+1}，报文0x{field.frame_id:X}'
                      f'（{field.frame_id}），信号 {field.signal}')
        lines.append(f'  {signal.name} ← {location}；单位 {signal.unit}；'
            f'有效期 valid_for={validity}；'
            +_setting(plan,'样本策略','在有效期内沿用最近有效值（backward_hold）',
                      *signal_paths.get(signal.name,('signals',index)),'sample_policy'))
    lines.append('  有效期表示一个有效样本最多沿用多久；到期即未知，无效更新覆盖前值，缺口不补零。')
    if plan.derived:
        lines.append('派生信号：')
        lines.extend(f'  {item.definition.name} = {item.definition.expr}；单位 {expression.root.unit}'
                     for item,expression in zip(plan.derived,plan.derived_expressions))
    lines.append('事件与时间窗口：')
    lines.extend(_rule_lines(plan))
    lines.append('计算项：')
    for index,calculation in enumerate(plan.calculations):
        signal='无单独信号' if calculation.signal is None else calculation.signal.text
        condition='' if calculation.condition is None else '；筛选 '+calculation.condition.text
        lines.append(f'  {calculation.calculation_id}：{OPERATIONS[calculation.operation]}；'
            f'{_scope(calculation.scope)}；信号 {signal}；结果单位 {calculation.unit}{condition}；'
            +_setting(plan,'有效覆盖门槛',calculation.minimum_coverage,'calculations',index,'minimum_coverage')
            +f'，部分结果策略 {calculation.partial_policy}')
    for calculation in plan.message_calculations:
        lines.append(f'  {calculation.calculation_id}：逐消息累计；来源 {calculation.source}；'
            f'表达式 {calculation.expr.text}；单位 {calculation.unit}；按原消息参数求值，不额外乘时间间隔')
    if not plan.calculations and not plan.message_calculations:
        lines.append('  未声明计算项。')
    lines.append('计算间隔：')
    choices=report.intervals.resolved if report.intervals is not None else ()
    for name,choice in choices:
        description={'actual':'采用实际记录时间差','fixed':'采用指定间隔 '+time_text(choice.step_ns),
                     'dbc':'运行时从DBC读取周期'}[choice.mode]
        lines.append(f'  {name}：{description}'+('；驱动信号 '+choice.driver if choice.driver else ''))
    if not choices:
        lines.append('  没有使用普通计算间隔的消费者。')
    lines.append('  固定间隔或DBC周期不延长信号有效期；导出网格独立于计算间隔。')
    lines.append('输出与默认设置：')
    lines.append('  '+_setting(plan,'结果表格式',plan.outputs.tables,'outputs','tables')+'；清单格式 JSON')
    contributions={'none':'关闭','full':'逐条保存'}[plan.outputs.contributions]
    lines.append('  '+_setting(plan,'逐消息贡献明细',contributions,'outputs','contributions'))
    for name,label,output in (('signal_csv','信号CSV导出',plan.outputs.signal_csv),
                              ('can_frames','CAN帧导出',plan.outputs.can_frames)):
        if output is None:
            lines.append('  '+label+'：关闭（默认）')
            continue
        description='开启，范围 '+output.scope+('，窗口 '+output.window if output.window else '')
        grid=output.spec.resampling if name=='signal_csv' else output.resampling
        if name=='signal_csv':
            description+='；信号 '+', '.join(output.spec.signals)
        else:
            description+='；来源 '+output.source+'，格式 '+output.spec.format
        if grid is None:
            description+='；保留原始采样，不重采样'
        else:
            description+='；独立导出网格 '+('运行时读取DBC周期' if grid.period_ns is None else time_text(grid.period_ns))
        lines.append('  '+label+'：'+description)
    backend=plan.execution.backend if backend_override is None else backend_override
    lines.append('  执行后端='+backend+('（命令行覆盖）' if backend_override is not None else
        '（配置指定）' if _declared(plan,'execution','backend') else '（默认）'))
    for field,label in (('process_count','读取解码工作进程上限'),('batch_rows','每批记录上限'),('memory_budget_bytes','分析层内存预算/字节'),
                        ('result_buffer_rows','结果缓冲行数'),('spool_quota_bytes','暂存磁盘预算/字节')):
        value=report.budget[field] if field=='process_count' else getattr(plan.execution,field)
        if field=='process_count' and value!=plan.execution.process_count:
            lines.append('  '+label+'='+str(value)+'（本次调用覆盖）')
            continue
        lines.append('  '+_setting(plan,label,'未设置' if value is None else value,'execution',field))
    for field,label in (('trace','详细追溯'),('integrity','完整性诊断'),('retain_work','保留现场')):
        lines.append('  '+_setting(plan,label,getattr(plan.diagnostics,field),'diagnostics',field))
    lines.append('检查结论：')
    lines.extend(_validation_lines(report.validation))
    return '\n'.join(lines)
