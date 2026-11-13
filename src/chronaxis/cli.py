"""提供当前配置检查、分析发布、独立批量和高性能积分器入口。

参数为命令行选项；按命令延迟导入实现，帮助只依赖标准库。
检查按需读取配置和DBC元数据，运行命令才扫描业务输入并发布结果。
结果目录可复用；完成清单最后写入，失败不报告正常完成。
"""

import argparse
import json
from pathlib import Path
import sys


def _parser() -> argparse.ArgumentParser:
    """定义已交付命令，未知命令和缺参数由argparse定位。

    参数: 无。返回: ArgumentParser，不读取任何配置或来源。
    异常: 原参数构造错误传播；解析时的帮助/坏参数分别SystemExit(0/2)。
    """
    parser = argparse.ArgumentParser(prog='chronaxis', description='Chronaxis当前配置检查与分析')
    commands = parser.add_subparsers(dest='command', required=True)
    fast = commands.add_parser('fast', help='校验、解释或执行单会话同帧累计')
    actions = fast.add_subparsers(dest='fast_command',required=True)
    for action in ('validate','explain','run'):
        sub = actions.add_parser(action)
        sub.add_argument('config')
        sub.add_argument('--process-count', type=int, default=None, help='覆盖本次读取、解码和单帧求值工作进程上限')
        if action == 'run':
            sub.add_argument('--output',required=True)
    fast_batch = actions.add_parser('batch',help='并行运行独立文件并发布批量报告')
    fast_batch.add_argument('config')
    fast_batch.add_argument('--output',required=True)
    fast_batch.add_argument('--process-count', type=int, default=None, help='覆盖独立任务工作进程数；不建立嵌套池')
    fast_batch.add_argument('--total',action='store_true',help='对同一模板内可比指标求总量')
    guide = commands.add_parser('guide', help='显示可直接阅读的AI指南路径')
    guide.add_argument('--language', choices=('zh', 'en'), default='zh', help='阅读入口语言，默认zh；不写文件')
    guide.add_argument('--output', help='可选：另存完整双语ZIP；父目录须存在，目标不能已存在')
    configuration = commands.add_parser('config', help='初始化及检查配置文件')
    configuration_actions = configuration.add_subparsers(dest='config_command', required=True)
    initialize = configuration_actions.add_parser('init', help='从合成场景生成完整新目录')
    initialize.add_argument('scene', nargs='?', help='场景名；用--list查看可选场景')
    initialize.add_argument('--list', action='store_true', help='列出全部场景，不写文件')
    initialize.add_argument('--output', help='全新目录；父目录须已存在')
    initialize.add_argument('--style', choices=('minimal','annotated'), default='annotated', help='默认完整注释版')
    convert = configuration_actions.add_parser('convert', help='当前JSON/YAML互转，保持类型和值；不保留注释')
    convert.add_argument('input', help='当前分析或批量配置')
    convert.add_argument('--output', required=True, help='新.json/.yaml/.yml文件；相对路径配置须写同目录')
    resolve = configuration_actions.add_parser('resolve', help='展开有效配置，固定绝对路径；可选显示实际默认')
    resolve.add_argument('input', help='当前分析或批量配置')
    resolve.add_argument('--output', help='可选全新JSON/YAML文件；省略时输出到终端')
    resolve.add_argument('--format', choices=('json','yaml'), help='终端默认yaml；文件由扩展名确定')
    resolve.add_argument('--defaults', action='store_true', help='写出适用的执行、输出、信号与规则等默认值')
    # 来源报告只按请求生成，不混入可重新加载的resolve输出。
    origins = configuration_actions.add_parser('origins', help='查看定义来自哪个配置文件，不读取业务输入')
    origins.add_argument('input', help='当前分析或批量配置')
    origins.add_argument('--fields', action='store_true', help='列所有显式叶字段；默认列来源、信号和派生定义')
    origins.add_argument('--format', choices=('text','json'), default='text', help='默认中文文本，json用于机器读取')
    # 静态命令只接受配置和明确后端，不提供输出目录等会误导为已运行的选项。
    for name, help_text in (('validate', '检查配置、绑定和当前执行能力'),
                            ('explain', '显示依赖、节点后端与预算声明')):
        check = commands.add_parser(name, help=help_text)
        check.add_argument('plan', help='分析计划YAML或JSON；来源相对路径按配置文件目录解释')
        check.add_argument('--backend', choices=('reference', 'numpy', 'auto'), default=None,
                           help='显式覆盖本次后端；省略则沿用计划声明')
        check.add_argument('--process-count', type=int, default=None, help='覆盖本次读取解码进程上限；正整数，省略沿用配置')
        check.add_argument('--format', choices=('text','json'), default='text',
                           help='默认显示易读说明；json用于程序读取')
    # 结果目录可复用；文件由本次时间区分，数值与格式仍来自同一个计划。
    execute = commands.add_parser('run', help='分析计划并发布带时间文件名的结果')
    execute.add_argument('plan', help='分析计划YAML或JSON')
    execute.add_argument('--output', required=True, help='结果目录，可重复使用；不覆盖已有文件')
    execute.add_argument('--work-dir', default=None, help='可选全新工作目录；省略沿AnalysisRunner唯一专用暂存')
    execute.add_argument('--backend', choices=('reference', 'numpy', 'auto'), default=None,
                         help='显式覆盖本次后端；省略沿用计划声明')
    execute.add_argument('--process-count', type=int, default=None, help='覆盖本次读取解码进程上限；正整数，省略沿用配置')
    batch = commands.add_parser('batch', help='独立分析任务批量运行')
    batch_actions = batch.add_subparsers(dest='batch_command', required=True)
    batch_run = batch_actions.add_parser('run', help='执行批量YAML或JSON并保存逐任务状态')
    batch_run.add_argument('plan', help='批量YAML或JSON，各任务计划路径相对此文件目录')
    batch_run.add_argument('--output', required=True, help='批量结果目录，可重复使用；每批使用独立时间标识')
    batch_run.add_argument('--process-count', type=int, default=None, help='可选覆盖同时运行数，须为正整数')
    return parser


def main(argv=None) -> int:
    """执行共享CLI并给出固定退出码，完整事实保在报告和原异常中。

    参数: argv为参数字符串序列或None（使用进程参数）。
    返回: 0成功、130取消；失败按入口/阶段返回1或2。普通文件失败为1，
        fast单会话准备失败（含文件错误）为2、运行失败为1；批量规则见手册CLI。
    异常: argparse帮助/参数错误按标准抛SystemExit；MemoryError及内部编程错误不伪装配置错误。
    副作用: 静态命令只读计划；run分析后发布本次时间文件到可复用目录。
    """
    arguments = _parser().parse_args(argv)
    operation = {'guide': '资料读取'}.get(arguments.command, '计划')
    try:
        if arguments.command == 'guide':
            # 默认只定位已经存在的README；显式output才生成独立副本。
            from .user_guide import export_guide, guide_path
            print(export_guide(arguments.output) if arguments.output else guide_path(arguments.language))
            return 0
        if arguments.command == 'fast':
            from .fast.cli import execute
            return execute(arguments)
        if arguments.command == 'config':
            from .configuration.cli import run_configuration_cli
            return run_configuration_cli(arguments)
        if arguments.command == 'batch':
            from .batch.cli import run_batch_cli
            return run_batch_cli(arguments)
        # 帮助和参数错误先由argparse结束；只有实际计划命令才加载计划依赖。
        from .analysis_cli import run_static, run_analysis
        return run_analysis(arguments) if arguments.command == 'run' else run_static(arguments)
    except KeyboardInterrupt:
        # 发布器已尝试最小收尾并保恢复owner；CLI退出后系统还会关闭进程持有的FD。
        if arguments.command == 'run':
            message = '分析已取消；输出可能已发布，请核对目标目录 ' + str(Path(arguments.output).absolute())
        elif arguments.command == 'batch':
            message = '批量操作已取消；请核对各任务结果和批量报告目录 ' + str(Path(arguments.output).absolute())
        else:
            message = '计划操作已取消。'
        print(message, file=sys.stderr)
        return 130
    except NotImplementedError as error:
        print(operation + '功能不可用：' + str(error), file=sys.stderr)
        return 1
    except OSError as error:
        print(operation + '文件操作失败：' + str(error), file=sys.stderr)
        return 1
    except ValueError as error:
        if arguments.command in ('run', 'batch'):
            # run只把明确的配置异常归为2；未包装的内部ValueError仍保原异常传播。
            from .planning.checks import PlanValidationError
            if not isinstance(error, PlanValidationError):
                raise
        # 共享语法加载增加一层配置错误，仍沿有限原异常链区分真实文件失败。
        from .analysis_cli import _cause_chain
        file_error = any(isinstance(cause,OSError) for issue in getattr(error, 'diagnostics', (error,))
                         for cause in _cause_chain(issue))
        if arguments.command in ('validate','explain') and arguments.format=='json':
            from .planning.checks import PlanValidationError
            if isinstance(error,PlanValidationError):
                payload = dict(valid=False, errors=[item.to_dict() for item in error.diagnostics])
                if error.blocked_checks:
                    payload['blocked_checks'] = error.blocked_checks
                print(json.dumps(payload,ensure_ascii=False,allow_nan=False))
                return 1 if file_error else 2
        print(operation + ('文件操作失败：' if file_error else '配置错误：') + str(error), file=sys.stderr)
        return 1 if file_error else 2
