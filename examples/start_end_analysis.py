"""从两个开始/结束信号找出三段活动，并发布每段均值。

同目录JSON给出合成秒时间数据，0—2秒正常结束、4—9秒超时、11—14秒正常结束。
三段value时间均值为10、52、110；活动窗口不额外扩展。使用公共API，输出保存在
新项目work唯一目录，finally关闭资源；无需CAN/DBC或历史文件。
"""

import json
from pathlib import Path
from uuid import uuid4
from chronaxis import AnalysisRunner, load_analysis_plan


def main():
    """运行并核对开始/结束与超时样例。

    参数: 无，读取同目录start_end_plan.json。返回: None，打印摘要及结果目录。
    异常: 配置、执行、手算断言或发布错误原样传播，已创建结果总会关闭。
    """
    root=Path(__file__).resolve().parents[1]
    plan=load_analysis_plan(Path(__file__).with_name('start_end_plan.json'))
    work=root/'work/m3-start-end-example'/uuid4().hex
    result=AnalysisRunner().run(plan,work_dir=work/'run')
    try:
        events=[(row.start_ns/10**9,row.end_ns/10**9,row.status) for row in result.iter_events()]
        means=sorted(row.value for row in result.iter_calculations())
        assert events==[(0.,2.,'closed'),(4.,9.,'timeout'),(11.,14.,'closed')]
        assert means==[10,10,52,52,110,110]
        manifest=result.write(work/'output')
        print(json.dumps(dict(device_label=result.metadata.device_label,data_kind='synthetic',
            event_seconds=events,event_and_segment_means=means,output=str(manifest.output_dir)),ensure_ascii=False))
    finally:
        result.close()


if __name__=='__main__':
    main()
