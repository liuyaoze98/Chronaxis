"""加载合成公共配置，展示经过检查的依赖、历史范围和能力状态。

输入默认为本目录analysis_plan.json，可用命令行显式指定其他JSON；
输出为JSON静态报告，时间均为整数纳秒。流程是load_analysis_plan读取配置、
validate_analysis_plan报告声明和能力、explain_analysis_plan展示依赖及资源限额。
不读待分析CSV/DBC，不启动AnalysisRunner，不计算事件/积分或写结果文件。
需将src加入PYTHONPATH；本示例不依赖开发用jsonschema包。
"""

# 公共入口示例只负责参数和输出，不复制来源或数值逻辑。
import argparse
import json
from pathlib import Path
from chronaxis import explain_analysis_plan, load_analysis_plan, validate_analysis_plan


def main() -> None:
    """读取一个JSON配置并打印公共静态报告。

    参数: 无，命令行位置参数config默认指向本目录合成样例。
    返回: None，标准输出为一份JSON报告；history_ns单位纳秒。
    异常: PlanValidationError为配置/文件错误，保留位置且退出非零。
    副作用: 只读指定JSON并打印，不创建输入数据或分析结果。
    """
    # 默认合成例没有车型或真实业务阈值，明确配置路径可替换。
    parser = argparse.ArgumentParser(description='检查公共计划并展示依赖，不执行分析')
    parser.add_argument('config', nargs='?', type=Path, default=Path(__file__).with_name('analysis_plan.json'))
    args = parser.parse_args()
    # 三个公开接口共用同一个不可变计划，不再加载原始日志或DBC。
    plan = load_analysis_plan(args.config)
    validation = validate_analysis_plan(plan)
    explanation = explain_analysis_plan(plan)
    # 逐项选择公开字段，避免对只读MappingProxy进行可变深拷贝。
    output = {
        'static_valid': validation.valid,
        'execution_ready': validation.execution_ready,
        'plan_identity': explanation.plan_identity,
        'source_names': list(explanation.source_names),
        'nodes': [{'name': node.node_id, 'node_type': node.node_type, 'dependencies': list(node.dependencies),
                   'unit': node.unit, 'backend': node.backend} for node in explanation.nodes],
        'history_ns': dict(explanation.history_ns),
        'budget': dict(explanation.budget),
        'capability_status': dict(validation.capability_status),
        'warnings': list(validation.warnings),
    }
    # 静态通过与可执行状态分别输出，不伪造积分或完成标记。
    print(json.dumps(output, ensure_ascii=False, indent=2))


# 导入示例模块不打开配置，只有直接运行时执行命令行入口。
if __name__ == '__main__':
    main()
