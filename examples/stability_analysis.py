"""运行温度报警例子：85降到77保持报警，直到75解除。

输入为同目录JSON中的合成温度，时间单位秒；温度已是摄氏值，degC作为
明确单位标签，不执行温度换算。公共AnalysisRunner输出0—9秒活动、对应片段及
手算平均温度239/3。结果发布到work新目录，finally关闭，不读取历史项目。
"""

import json
from pathlib import Path
from uuid import uuid4
from chronaxis import AnalysisRunner, load_analysis_plan


def main():
    """执行迟滞配置并检查实际活动和统计结果。

    参数: 无，读取stability_plan.json。返回: None，打印活动/均温/输出目录。
    异常: 配置、分析、断言、发布或关闭错误原样传播。
    """
    root = Path(__file__).resolve().parents[1]
    plan = load_analysis_plan(Path(__file__).with_name('stability_plan.json'))
    work = root / 'work/m3-stability-example' / uuid4().hex
    result = AnalysisRunner().run(plan, work_dir=work / 'run')
    try:
        intervals = [(row.start_ns / 10**9, row.end_ns / 10**9, row.status)
                     for row in result.iter_events()]
        means = [row.value for row in result.iter_calculations()]
        assert intervals == [(0.0, 9.0, 'closed')]
        assert len(means) == 2 and all(abs(value - 239/3) < 1e-12 for value in means)
        manifest = result.write(work / 'output')
        print(json.dumps(dict(device_label=result.metadata.device_label, data_kind='synthetic',
                              alarm_seconds=intervals, mean_temperature=means,
                              output=str(manifest.output_dir)), ensure_ascii=False))
    finally:
        # 已发布文件保留；清理当前运行的句柄和有预算状态。
        result.close()


if __name__ == '__main__':
    main()
