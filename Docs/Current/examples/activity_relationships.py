"""按同一次运行的实例ID关联事件、片段与计算。参数: --output新目录。输出: 关联JSON。"""
from pathlib import Path
from dataclasses import asdict
import argparse
import json
from chronaxis import AnalysisRunner, load_analysis_plan


def verify(output):
    """参数: 新目录。返回: 三表关联内容。异常: 缺失父对象或运行失败；关闭结果。"""
    result=AnalysisRunner().run(load_analysis_plan(Path(__file__).parent/'activity.yaml'),work_dir=output/'work')
    try:
        events={r.event_id:r for r in result.iter_events()}
        segments={r.segment_id:r for r in result.iter_segments()}
        rows=list(result.iter_calculations())
        # 先判断scope，再选择对应ID空间；calculation_id和rule_id是定义名称，不能用于跨表实例关联。
        for row in rows:
            if row.scope=='event':assert row.parent_id in events
            elif row.scope=='segment':assert row.parent_id in segments
            else:assert row.parent_id is None
        for segment in segments.values():assert all(i in events for i in segment.parent_event_ids)
        assert {r.calculation_id:r.value for r in rows}=={'event_energy':50.0,'context_energy':70.0}
        result.write(output/'published')
        data={'events':[asdict(r) for r in events.values()],'segments':[asdict(r) for r in segments.values()],'calculations':[asdict(r) for r in rows]}
        (output/'relationships.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
        return data
    finally:result.close()


def main():
    """参数: CLI新输出目录。返回: None。异常: 参数或原运行错误。"""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output;output.mkdir(parents=True,exist_ok=False)
    print(json.dumps(verify(output),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
