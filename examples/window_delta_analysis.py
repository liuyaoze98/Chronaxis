"""运行完整窗口电压变化例子，并发布两次事件和窗口均值。

输入为同目录JSON中的合成电压，单位V，时间秒；公共AnalysisRunner在4秒和12秒
检测到最近4秒单调上升5V。各取前后1秒，均值都是2.5V。输出写work独立目录，
不需要CAN/DBC或读取历史项目，finally关闭结果；失败直接传播。
"""

import json
from pathlib import Path
from uuid import uuid4
from chronaxis import AnalysisRunner, load_analysis_plan


def main():
    """通过公开计划和发布接口运行手算样例。

    参数: 无，使用同目录window_delta_plan.json。返回: None，打印摘要及输出路径。
    异常: 配置、计算、断言或发布失败直接传播，结果始终关闭。
    """
    root = Path(__file__).resolve().parents[1]
    plan = load_analysis_plan(Path(__file__).with_name('window_delta_plan.json'))
    work = root / 'work/m3-window-delta-example' / uuid4().hex
    result = AnalysisRunner().run(plan, work_dir=work / 'run')
    try:
        times = [row.confirmed_ns / 1_000_000_000 for row in result.iter_events()]
        means = [row.value for row in result.iter_calculations()]
        assert times == [4.0, 12.0] and means == [2.5, 2.5]
        manifest = result.write(work / 'output')
        print(json.dumps(dict(device_label=result.metadata.device_label, data_kind='synthetic',
                              event_seconds=times, mean_voltage=means, output=str(manifest.output_dir)), ensure_ascii=False))
    finally:
        result.close()


if __name__ == '__main__':
    main()
