"""同一ASC输入比较actual、fixed和DBC周期。参数: --output新目录。输出: 三组真实结果。"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import argparse
import json
from chronaxis import AnalysisPlan, AnalysisRunner


def config():
    """参数: 无。返回: 相对本脚本data路径的完整分析字典。异常: 无。"""
    return dict(config_version=3,dataset=dict(name='timing'),
        sources=[dict(paths='data/timing.asc',dbc_by_channel={'1':'data/timing.dbc'})],
        signals=[dict(name=name,field=dict(frame_id='0x100',signal=field),dtype=dtype,unit=unit,valid_for='10s',**({'choices':[[0,False],[1,True]]} if dtype=='bool' else {}))
            for name,field,dtype,unit in [('request','Request','bool','1'),('response','Response','bool','1'),('temperature','Temperature','float64','degC'),('voltage','Voltage','float64','V')]],
        rules=[dict(name='request_edge',rule_type='rising_edge',condition='request'),dict(name='response_edge',rule_type='rising_edge',condition='response'),
            dict(name='hot',rule_type='condition_duration',condition='temperature >= 80',minimum_duration='1.5s'),
            dict(name='change',rule_type='window_delta',signal='voltage',window='4s',direction='rise',threshold=5,emit_initial=True)],
        sequences=[dict(name='pair',start='request_edge',response='response_edge',min_delay='0s',max_delay='3s')],
        calculations=[dict(name='hot_duration',operation='duration',condition='temperature >= 80')])


def verify(output):
    """参数: 新输出目录。返回: 模式对照。异常: 不符合手算预期或运行失败；关闭资源。"""
    output.mkdir(parents=True,exist_ok=False);summary={}
    for mode in ('actual','fixed','dbc'):
        raw=deepcopy(config());choice={'mode':mode}
        if mode=='fixed':choice['value']='1s'
        if mode!='actual':choice['driver']='request'
        raw['intervals']={'default':choice}
        result=AnalysisRunner().run(AnalysisPlan.from_dict(raw,base_dir=Path(__file__).parent),work_dir=output/(mode+'-work'))
        try:
            events=sorted(result.iter_events(),key=lambda r:(r.rule_id,r.start_ns));pairs=list(result.iter_sequences());rows=list(result.iter_calculations())
            summary[mode]={'events':[asdict(e) for e in events],'pairs':[asdict(r) for r in pairs],'calculations':[asdict(r) for r in rows]}
            assert pairs[0].delay_ns== (2_000_000_000 if mode=='actual' else 1_000_000_000)
            assert rows[0].value==(5.0 if mode=='actual' else 2.0)
            result.write(output/mode)
        finally:result.close()
    (output/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    return summary


def main():
    """参数: CLI输出路径。返回: None。异常: 原执行或校验错误。"""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    print(json.dumps(verify(parser.parse_args().output),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
