"""复核四个完整教学案例；仅把新运行输出写入调用者指定的新目录。

参数为--output；运行须安装CAN依赖。返回JSON核对记录，断言失败或读取错误传播。
"""
from pathlib import Path
import argparse
import csv
import json
from chronaxis import AnalysisRunner, load_analysis_plan


def verify(output):
    """参数: 尚不存在的输出目录。返回: 核对摘要。异常: 执行/断言/I/O错误；关闭结果。"""
    output.mkdir(parents=True,exist_ok=False);summary={}
    for name in ('can-joint-analysis','start-end','message-energy','dual-grid'):
        result=AnalysisRunner().run(load_analysis_plan(Path(__file__).parent/(name+'.yaml')),work_dir=output/(name+'-work'))
        try:
            rows=list(result.iter_calculations())
            if name=='start-end':
                events=sorted(result.iter_events(),key=lambda r:r.start_ns)
                starts={r.event_id:r.start_ns for r in events}
                rows.sort(key=lambda r:starts[r.parent_id])
            entry={'values':[r.value for r in rows],'status':[r.status for r in rows]}
            expected={'can-joint-analysis':[26.0],'start-end':[10.0,52.0,110.0],'message-energy':[800.0],'dual-grid':[13.0]}[name]
            assert entry['values']==expected,(name,entry)
            if name=='start-end':
                assert [(r.start_ns,r.end_ns) for r in events]==[(0,2_000_000_000),(4_000_000_000,9_000_000_000),(11_000_000_000,14_000_000_000)]
                entry['events']=[{'start_ns':r.start_ns,'end_ns':r.end_ns,'status':r.status,'trigger':r.trigger} for r in events]
            target=output/name;result.write(target)
            if name=='message-energy':
                with (target/'贡献明细.csv').open(encoding='utf-8-sig',newline='') as stream:contributions=list(csv.DictReader(stream))
                assert len(contributions)==3,contributions
                assert any('缺少计算输入' in r['说明'] for r in contributions),contributions
                entry['contributions']=contributions
            if name=='dual-grid':
                resampled=next(target.rglob('resampled.csv'))
                with resampled.open(encoding='utf8',newline='') as stream:grid=list(csv.DictReader(stream))
                assert len(grid)==12,grid
                assert [float(r['value']) for r in grid[:5]]==[3,4,5,6,7]
                frames=next(target.rglob('frames.asc')).read_text(encoding='utf8').splitlines()
                # 排除ASC头部，逐条核对实际生成帧数。
                frames=[line for line in frames if ' Rx ' in line or ' Tx ' in line]
                assert len(frames)==5,frames
                assert [r['reason'] for r in grid[-3:]]==['missing_right']*3
                entry.update(signal_points=len(grid),can_frames=len(frames))
            summary[name]=entry
        finally:result.close()
    (output/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    return summary


def main():
    """参数: CLI输出目录。返回: None。异常: 原校验/执行错误；不覆盖目录。"""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(verify(parser.parse_args().output),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
