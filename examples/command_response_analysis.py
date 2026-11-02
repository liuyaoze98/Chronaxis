"""从公开JSON预设运行请求/响应分析，并发布可直接查看的结果。

输入examples/command_response_plan.json内的合成布尔信号，时间单位为秒；
输出写work下新目录（home映射到E盘），控制台只显示请求、结论及延迟。
本例不需要CAN/DBC，不读取RefProjects；既有目录不覆盖，结果在finally关闭。
"""

import json
from pathlib import Path
from uuid import uuid4
from chronaxis import AnalysisRunner, load_analysis_plan


def main():
    """通过公共计划、AnalysisRunner、迭代器及原子发布演示四次请求。

    参数: 无，配置为同目录command_response_plan.json。
    返回: None，打印JSON摘要；完整结果和清单写新工作目录。
    异常: 输入、计算、断言、发布或清理错误直接传播，不打印伪成功。
    """
    root = Path(__file__).resolve().parents[1]
    plan = load_analysis_plan(Path(__file__).with_name('command_response_plan.json'))
    work = root / 'work/m3-command-response-example' / uuid4().hex
    result = AnalysisRunner().run(plan, work_dir=work / 'run')
    try:
        events = {row.event_id: row for row in result.iter_events()}
        summaries = [dict(request_s=events[row.request_id].confirmed_ns / 1_000_000_000,
            status=row.status, decided_s=row.decided_ns / 1_000_000_000,
            delay_s=None if row.delay_ns is None else row.delay_ns / 1_000_000_000,
            quality=int(row.quality)) for row in result.iter_sequences()]
        assert [row['status'] for row in summaries] == ['matched', 'indeterminate', 'matched', 'no_response']
        manifest = result.write(work / 'output')
        print(json.dumps(dict(device_label=result.metadata.device_label, data_kind='synthetic', rows=summaries,
            output=str(manifest.output_dir)), ensure_ascii=False))
    finally:
        result.close()


if __name__ == '__main__':
    main()
