"""从源码或解压资料运行用户给定计划并发布到可重复使用的结果目录。

输入：分析YAML/JSON和结果目录路径；输出：计算行与已发布的结果文件。
只使用已安装库的公开接口。夹具及结果留在用户目录；不依赖源码或Git。
"""
import argparse
from contextlib import closing

from chronaxis import AnalysisRunner, load_analysis_plan


def main():
    """运行一个计划。参数: 命令行配置和输出路径。返回: 无。异常: 原加载、运行或发布错误。"""
    # 所有文件均由用户明确选择，避免误写固定路径或覆盖旧结果。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("output")
    args = parser.parse_args()
    plan = load_analysis_plan(args.plan)
    runner = AnalysisRunner()
    # 在启动真实扫描前检查错误，不以声明检查证明业务数据正确。
    report = runner.validate(plan)
    if not report.valid or not report.execution_ready:
        raise ValueError(report.errors)
    # 用上下文管理结果，用 closing 管理游标，即使循环中发生错误也释放资源。
    with runner.run(plan) as result:
        with closing(result.iter_calculations()) as rows:
            for row in rows:
                print(row.calculation_id, row.value, row.unit, row.status, row.reason)
        publication = result.write(args.output)
        print(publication.manifest_path)


if __name__ == "__main__":
    main()
