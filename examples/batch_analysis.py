"""把三个已有合成分析计划作为独立任务运行，并保存各自结果和批量清单。

输入为同目录batch_plan.json及其指向的开始/结束、窗口变化量、迟滞例子；
它们各自的信号、单位、有效期和手算依据见原示例，不把三者拼成连续试验。
最多两个任务同时运行，失败默认继续；期望三个任务均completed。
运行：python -B examples/batch_analysis.py。输出写新work子目录，结束关闭资源。
"""

import json
import os
from pathlib import Path
from uuid import uuid4
from chronaxis import load_batch_plan, run_batch


def main():
    """运行实际批量API。参数: 无。返回: None并打印摘要。异常: 原运行/断言/关闭错误。"""
    root = Path(__file__).absolute().parents[1]
    plan = load_batch_plan(root / 'examples/batch_plan.json')
    report = run_batch(plan, root/'work/m3-batch-example'/uuid4().hex,
                       device_label=os.environ.get('CHRONAXIS_DEVICE_LABEL', '').strip() or 'pending')
    try:
        assert report.status == 'completed'
        assert report.to_dict()['counts'] == dict(completed=3, failed=0, cancelled=0)
        print(json.dumps(dict(status=report.status, counts=report.to_dict()['counts'],
            output=str(report.output_dir), report=str(report.output_dir/'batch_report.json')),
            ensure_ascii=False, allow_nan=False))
    finally:
        report.close()


if __name__ == '__main__':
    main()
