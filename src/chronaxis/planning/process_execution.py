"""静态检查单会话文件读取并行的支持范围，不打开日志或DBC。

进程数与文件归并分别检查，明确拒绝未接入的来源及嵌套并行。
只声明执行上限，不能凭校验成功证明文件内部有序或实际使用了多个进程。
"""

# 只由独立批量工作进程设置，不读取环境变量或根据CPU数量隐式改变用户配置。
IN_BATCH_WORKER = False


def process_execution_errors(plan):
    """核有效计划的进程与归并声明。参数: plan。返回: 错误tuple。异常: 无输入IO。
    """
    count = plan.execution.process_count
    if type(count) is not int or count < 1:
        return ('execution.process_count需要大于等于1的整数，不接受bool',)
    errors = []
    merged = False
    for source in plan.sources:
        merge = getattr(source.config, 'file_merge', 'concatenate')
        if merge not in ('concatenate', 'time_order'):
            errors.append(source.name + '的file_merge需要concatenate或time_order')
        merged |= merge == 'time_order'
    if (count > 1 or merged) and (len(plan.sources) != 1 or plan.sources[0].source_type not in ('can_blf', 'can_asc', 'asc_or_blf')):
        errors.append('文件并行读取或时间归并当前需要一个ASC/BLF来源；其他来源或多个来源请使用process_count: 1及默认文件接续')
    if count > 1 or merged:
        if IN_BATCH_WORKER:
            errors.append('独立批量工作进程内不再建立文件读取进程池；请直接运行此连续分析计划')
        if any(getattr(source.config,'decode_scope','requested')=='all' for source in plan.sources):
            errors.append('并行读取及时间归并当前需要reader.decode_scope: requested')
    return tuple(errors)


def source_execution_facts(plan):
    """解释文件组织与读取进程上限。参数: 有效计划。返回: 有限dict元组。异常: 无；不读输入。
    """
    from ..sources.can_spec import LegacyCANSpec
    from ..sources.text_can_spec import CANTextSpec
    result=[]
    if type(plan.execution.process_count) is not int or plan.execution.process_count<1:
        return ()
    for source in plan.sources:
        config=source.config
        if source.source_type not in ('can_blf','can_asc','asc_or_blf'):
            continue
        if not isinstance(config,(LegacyCANSpec,CANTextSpec)):
            continue
        if source.source_type=='can_blf' and type(config) is not LegacyCANSpec:
            continue
        if source.source_type!='can_blf' and type(config) is not CANTextSpec:
            continue
        files=config.input_paths if source.source_type=='can_blf' else config.inputs
        requested=plan.execution.process_count
        merge=config.file_merge
        # 接续只有多文件且有效上限大于1才建读取进程；时间归并沿独立工作槽。
        effective=min(requested,len(files))
        limit=effective if effective>1 or merge=='time_order' else 0
        result.append(dict(source=source.name,file_count=len(files),file_merge=merge,
            read_process_limit=limit,continuous_session=True,
            temporary_merge_files=merge=='time_order'))
    return tuple(result)
