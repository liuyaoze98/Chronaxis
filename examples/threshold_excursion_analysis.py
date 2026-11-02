"""运行显式温度阈值预设，打印报警区间、逐段时长和同次累计。

同目录JSON为合成85→77→75℃样例，实际报警[0,9)，累计9秒。
通过正式API运行和发布；产物只写work，finally关闭结果并验证RAM账本归零。
示例温度、门槛和有效期用于解释配置，不代表真实设备标定。
"""

import json
from pathlib import Path
from uuid import uuid4
from chronaxis import AnalysisRunner, load_analysis_plan


def main():
    """运行完整阈值计划并用手算核对结果。

    参数: 无，读取同目录threshold_excursion_plan.json。
    返回: None，打印结果路径与累计字段。异常: 读写/分析错误或手算断言失败。
    """
    root=Path(__file__).resolve().parents[1]
    work=root/'work/m3-accept-home-20261023/threshold-example'/uuid4().hex
    plan=load_analysis_plan(Path(__file__).with_name('threshold_excursion_plan.json'))
    result=AnalysisRunner().run(plan,work_dir=work/'run')
    budget=result.spool.budget
    try:
        # 真值直接来自0秒85℃、9秒75℃；中间77℃保持报警，不因文件/批变化结束。
        intervals=[(row.start_ns/10**9,row.end_ns/10**9) for row in result.iter_events()]
        durations=[row.value for row in result.iter_calculations()]
        summary=result.metadata.threshold_durations[0]
        assert intervals==[(0.0,9.0)] and durations==[9.0]
        assert summary.value==9 and summary.status=='complete'
        published=result.write(work/'output')
        report=dict(device_label='home',data_kind='synthetic',intervals_seconds=intervals,
            duration_seconds=durations,summary=summary.to_dict(),output=str(published.output_dir),
            manifest=str(published.manifest_path))
    finally:
        result.close()
    assert budget.ram_bytes==0
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
