"""只计算合成报文的能量总量，演示关闭逐次贡献明细后的公开入口。

复用同目录完整明细示例的四条BLF/DBC与配置：同刻两次各400J，缺值一次
跳过，未知消息不参与，总计800J。输入为显式后端/格式，输出为统一发布目录
及小摘要；仅main调用时在work建立新目录。来源为合成，不代表实际数据验收。
"""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from chronaxis import AnalysisRunner, load_analysis_plan
from message_energy_analysis import create_inputs, configuration, bounded_rows


def run_example(backend='numpy', tables='csv'):
    """用正式AnalysisRunner算总计并发布，不查询未生成的逐条明细。

    参数: backend为numpy/reference，tables为csv/jsonl。返回: 数值及实际输出目录。
    异常: 输入、公开API、手算或清理错误原样传播；所有写入均在唯一work子目录。
    """
    root = Path(__file__).resolve().parents[1]/'work/summary-energy-example'/uuid4().hex
    root.mkdir(parents=True)
    blf, dbc = create_inputs(root)
    config = configuration(blf, dbc, backend, 2, tables)
    config['outputs']['contributions'] = 'none'
    config.pop('diagnostics')
    path = root/'analysis.json'
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    plan = load_analysis_plan(path)
    with AnalysisRunner().run(plan, work_dir=root/'analysis-work') as result:
        summary, = bounded_rows(result.iter_calculations(), 1)
        assert summary.value == 800.0 and summary.unit == 'J'
        assert not result.contributions_available
        assert result.metadata.input_diagnostics == ()
        output = result.write(root/'published')
        budget = result.spool.budget
        report = dict(device_label=result.metadata.device_label, energy_J=summary.value,
            contribution_output=plan.outputs.contributions,
            output_dir=str(output.output_dir))
    assert budget.ram_bytes == 0
    return report


def main():
    """解析后端/格式并运行。参数: 命令行。返回: 无，打印小摘要。异常: 原示例错误。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('numpy', 'reference'), default='numpy')
    parser.add_argument('--tables', choices=('csv', 'jsonl'), default='csv')
    args = parser.parse_args()
    print(json.dumps(run_example(args.backend, args.tables), ensure_ascii=False))


if __name__ == '__main__':
    main()
