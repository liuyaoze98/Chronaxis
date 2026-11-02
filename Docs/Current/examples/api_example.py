"""从YAML配置执行分析并逐行读取结果；输入为配置路径，可选输出新目录。"""
import argparse
from pathlib import Path

from chronaxis import AnalysisRunner, load_analysis_plan, validate_analysis_plan


def main():
    """检查配置后执行，显式关闭游标和结果。返回None；配置/执行错误保留异常链。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', nargs='?', type=Path, default=Path(__file__).parent / 'analysis.yaml')
    parser.add_argument('--output', type=Path, help='尚不存在的正式输出目录；省略则只打印结果')
    args = parser.parse_args()
    plan = load_analysis_plan(args.plan)
    report = validate_analysis_plan(plan)
    if not report.valid or not report.execution_ready:
        raise RuntimeError(report)
    with AnalysisRunner().run(plan) as result:
        rows = result.iter_calculations()
        try:
            for row in rows:
                print(row.calculation_id, row.value, row.unit, row.status, row.reason)
        finally:
            rows.close()
        if args.output is not None:
            manifest = result.write(args.output)
            print(manifest)


if __name__ == '__main__':
    main()
