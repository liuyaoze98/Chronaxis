"""从类型化信号到预设片段，再执行完整分析。参数: --output新目录。返回: 报警时长。"""
from pathlib import Path
import argparse
from chronaxis import (PresetSpec, resolve_preset_roles,
                       build_preset, AnalysisPlan, AnalysisRunner)
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType


def run(output):
    """参数: 新输出目录。返回: 生成的计算行。异常: 角色/计划/执行错误；关闭结果。"""
    # 类型化对象中的有效期使用整数纳秒；它不包含任何输入样本。
    temperature=SignalDefinition(name='temperature',source='table',field='temperature',
        dtype=SignalDType.FLOAT64,unit='degC',valid_for_ns=10_000_000_000)
    signals=(temperature,)
    spec=PresetSpec.from_dict(dict(name='heat',preset_type='threshold_excursion',version='1',
        role_bindings={'signal':'temperature'},parameters={'unit':'degC','enter_threshold':80,'exit_threshold':75}))
    roles=resolve_preset_roles(spec,signals)
    assert roles[0].definition is temperature and roles[0].resolution=='explicit'
    fragment=build_preset(spec,signals)  # 返回PlanFragment；此函数也会自行检查角色。
    nodes=fragment.to_dict()            # 仅节点声明，不包含sources、signals或运行结果。
    raw=dict(config_version=3,dataset=dict(name='preset_api'),
        sources=[dict(name='table',source_type='memory',
            rows=[dict(time=f'{t}s',values={'temperature':v}) for t,v in ((0,85),(3,77),(9,75),(10,75))])],
        signals=[dict(name=s.name,source=s.source,field=s.field,dtype=s.dtype.value,unit=s.unit,valid_for=f'{s.valid_for_ns}ns') for s in signals])
    # 本例基础计划还没有同类节点，故可update。已有节点时须逐列表合并并检查ID冲突。
    # 不再同时把spec加入raw['presets']，否则同一预设会展开两遍。
    raw.update(nodes)
    plan=AnalysisPlan.from_dict(raw)
    with AnalysisRunner().run(plan,work_dir=output/'work') as result:
        rows=list(result.iter_calculations())
        assert len(rows)==1 and rows[0].value==9.0 and rows[0].unit=='s'
        result.write(output/'published')
        return rows


def main():
    """参数: CLI新目录。返回: None。异常: 原校验/执行/I/O错误。"""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output;output.mkdir(parents=True,exist_ok=False)
    for row in run(output):print(row.calculation_id,row.value,row.unit,row.status)


if __name__=='__main__':main()
