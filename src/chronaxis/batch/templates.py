"""把一个分析模板应用于明确输入集合，每个文件形成独立任务，不读取日志。

路径按模板目录解释；输入目录按批量配置目录解释。复用已有自然序和4096文件限制，
来源有多个候选时要求source，绝不把连续会话自动拆开。本入口由用户显式选择。
"""
from copy import deepcopy
from pathlib import Path

from ..configuration import load_configuration
from ..configuration.imports import expand_document_imports
from ..planning.checks import PlanValidationError, text_at
from ..planning.input_paths import expand_source_files


def template_jobs(raw, base):
    """参数为批量对象和路径基准；返回独立BatchJob列表。配置错误抛PlanValidationError，不写文件。"""
    from .models import BatchJob
    from ..planning.plan import AnalysisPlan
    path=base/Path(text_at(raw['template'],'$.template'))
    path=path.absolute()
    template=expand_document_imports(load_configuration(path)).data
    sources=template.get('sources',[]) if type(template) is dict else []
    if type(sources) is not list or any(type(source) is not dict for source in sources):
        raise PlanValidationError('$.template','模板sources必须为来源对象数组')
    selector=raw.get('source')
    if selector is not None:selector=text_at(selector,'$.source',identifier=True)
    candidates=[i for i,s in enumerate(sources) if selector is None or s.get('name',f'source_{i+1}')==selector]
    if len(candidates)!=1:
        raise PlanValidationError('$.source','模板必须能唯一确定要替换文件的来源；多来源时填写source')
    index=candidates[0]
    selected=sources[index]
    if selected.get('source_type')=='memory':
        raise PlanValidationError('$.source','目录批量模板不能替换内存来源')
    files,shifts=expand_source_files(dict(paths=raw['inputs'],source_type=selected.get('source_type')),base,'$.inputs')
    jobs=[]
    for number,file in enumerate(files,1):
        config=deepcopy(template);source=config['sources'][index]
        for key in ('path','paths','offsets'):source.pop(key,None)
        source['path']=str(file)
        if shifts is not None:source['paths']=[dict(path=source.pop('path'),offset=shifts[number-1])]
        jobs.append(BatchJob(f'job_{number}',AnalysisPlan.from_dict(config,base_dir=path.parent)))
    return jobs
