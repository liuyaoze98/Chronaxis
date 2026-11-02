"""提供计划检查、运行发布、独立批量与旧INI导入，复用各自公共接口。

输入为命令行路径、模式及显式mapping；输出为新计划、原INI、迁移报告和简短
JSON摘要。转换失败仍可保存原文与失败报告，绝不返回部分可运行计划。
validate/explain只读取计划，输出共享AnalysisRunner报告，不打开数据/DBC或运行分析。
run才调用同一AnalysisRunner执行、write发布并关闭结果；完整完成后才打印成功摘要。
batch run调用同一批量API，打印状态计数，逐任务错误保存在batch_report.json。
配置和参数错误退出2，文件/平台错误退出1，取消退出130，成功退出0。
--help及参数错误只需标准库；实际命令执行时才加载对应计划或发布模块。
"""

import argparse
import json
import os
from pathlib import Path
import sys


def _parser() -> argparse.ArgumentParser:
    """定义已交付命令，未知命令和缺参数由argparse定位。

    参数: 无。返回: ArgumentParser，不读取任何配置或来源。
    异常: 原参数构造错误传播；解析时的帮助/坏参数分别SystemExit(0/2)。
    """
    parser = argparse.ArgumentParser(prog='chronaxis', description='Chronaxis计划检查、分析与旧INI导入')
    commands = parser.add_subparsers(dest='command', required=True)
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
    convert.add_argument('input', help='当前分析、批量或INI映射配置')
    convert.add_argument('--output', required=True, help='新.json/.yaml/.yml文件；相对路径配置须写同目录')
    resolve = configuration_actions.add_parser('resolve', help='展开有效配置，固定绝对路径；可选显示实际默认')
    resolve.add_argument('input', help='当前分析、批量或INI映射配置')
    resolve.add_argument('--output', help='可选全新JSON/YAML文件；省略时输出到终端')
    resolve.add_argument('--format', choices=('json','yaml'), help='终端默认yaml；文件由扩展名确定')
    resolve.add_argument('--defaults', action='store_true', help='写出适用的执行、输出、信号与规则等默认值')
    # 来源报告只按请求生成，不混入可重新加载的resolve输出。
    origins = configuration_actions.add_parser('origins', help='查看定义来自哪个配置文件，不读取业务输入')
    origins.add_argument('input', help='当前分析、批量或INI映射配置')
    origins.add_argument('--fields', action='store_true', help='列所有显式叶字段；默认列来源、信号和派生定义')
    origins.add_argument('--format', choices=('text','json'), default='text', help='默认中文文本，json用于机器读取')
    # 静态命令只接受配置和明确后端，不提供输出目录等会误导为已运行的选项。
    for name, help_text in (('validate', '检查配置、绑定和当前执行能力'),
                            ('explain', '显示依赖、节点后端与预算声明')):
        check = commands.add_parser(name, help=help_text)
        check.add_argument('plan', help='分析计划YAML或JSON；来源相对路径按配置文件目录解释')
        check.add_argument('--backend', choices=('reference', 'numpy'), default=None,
                           help='显式覆盖本次后端；省略则沿用计划声明')
        check.add_argument('--format', choices=('text','json'), default='text',
                           help='默认显示易读说明；json用于程序读取')
    # run只提供执行选择和新目录，数值、格式和业务声明继续来自同一个计划。
    execute = commands.add_parser('run', help='分析计划并发布到全新输出目录')
    execute.add_argument('plan', help='分析计划YAML或JSON')
    execute.add_argument('--output', required=True, help='全新输出目录，不覆盖已有文件或目录')
    execute.add_argument('--work-dir', default=None, help='可选全新工作目录；省略沿AnalysisRunner唯一专用暂存')
    execute.add_argument('--backend', choices=('reference', 'numpy'), default=None,
                         help='显式覆盖本次后端；省略沿用计划声明')
    batch = commands.add_parser('batch', help='独立分析任务批量运行')
    batch_actions = batch.add_subparsers(dest='batch_command', required=True)
    batch_run = batch_actions.add_parser('run', help='执行批量YAML或JSON并保存逐任务状态')
    batch_run.add_argument('plan', help='批量YAML或JSON，各任务计划路径相对此文件目录')
    batch_run.add_argument('--output', required=True, help='全新批量输出目录')
    batch_run.add_argument('--process-count', type=int, default=None, help='可选覆盖同时运行数，须为正整数')
    legacy = commands.add_parser('legacy', help='旧配置迁移')
    actions = legacy.add_subparsers(dest='legacy_command', required=True)
    migrate = actions.add_parser('import', help='保留原INI，生成可校验计划及迁移报告')
    migrate.add_argument('ini', help='原INI文件')
    migrate.add_argument('--mode', required=True,
        choices=('legacy_sum', 'sclicer_single', 'sclicer_start_only', 'sclicer_slope', 'sclicer_start_end'))
    migrate.add_argument('--mapping', required=True, help='显式映射YAML或JSON，来源路径相对此文件目录')
    migrate.add_argument('--output', required=True, help='新计划.json；原文/报告使用同名前缀，不覆盖已有目标')
    return parser


def _brief(result, files) -> dict:
    """生成固定摘要，不将全部原字段或warnings输出到控制台。

    参数: result为完整导入结果；files为已实际发布的固定路径模型。
    返回: 原生JSON对象，三路径为绝对str，转换失败plan为None。
    异常: 内部typed接口不符直接传播，不以自由反射吞掉错误。
    """
    issues = result.report.issues
    return dict(status=result.report.status, plan=None if files.plan is None else str(files.plan),
        original=str(files.original), report=str(files.report), device_label=result.report.device_label,
        issue_count=len(issues), error_count=sum(item.level == 'error' for item in issues),
        warning_count=sum(item.level == 'warning' for item in issues))


def _issue_text(issue) -> str:
    """将首个错误压缩为可跳转位置，完整事实留在迁移报告。

    参数: issue为固定导入问题。返回: 一行文本，含来源/路径及存在的行列。
    异常: 内部字段类型错误传播，不截掉报告中的原始消息。
    """
    location = issue.origin + ':' + issue.path
    if issue.line is not None:
        location += ':' + str(issue.line)
        if issue.column is not None:
            location += ':' + str(issue.column)
    return location + ' [' + issue.code + '] ' + issue.message.replace('\n', ' ')


def _run_import(arguments) -> int:
    """调用真实两配置加载与计划最后发布，静态成功不代表数据运行通过。

    参数: arguments为argparse已经校验的legacy import参数。
    返回: 0为完整转换/发布成功，2为原配置整体拒绝且原文/报告已保存。
    异常: 文件/平台/取消/资源错误原样向main传播，保发布器恢复owner。
    """
    from .migration import load_legacy_ini
    from .migration.publication import write_legacy_import
    # 环境未声明时只标pending；CLI不把当前文件位置猜成home或work。
    label = os.environ.get('CHRONAXIS_DEVICE_LABEL', '').strip() or 'pending'
    ini, mapping = Path(arguments.ini).absolute(), Path(arguments.mapping).absolute()
    result = load_legacy_ini(ini, mapping, mode=arguments.mode, device_label=label)
    files = write_legacy_import(result, arguments.output, source_paths=(ini, mapping))
    print(json.dumps(_brief(result, files), ensure_ascii=False, allow_nan=False))
    if result.plan is None:
        issue = next((item for item in result.report.issues if item.level == 'error'), None)
        print('导入失败：' + (_issue_text(issue) if issue is not None else '配置不能整体转换'), file=sys.stderr)
        return 2
    return 0


def main(argv=None) -> int:
    """执行共享CLI并给出固定退出码，完整事实保在报告和原异常中。

    参数: argv为参数字符串序列或None（使用进程参数）。
    返回: 0成功、2配置错误、1文件/平台错误、130取消。
    异常: argparse帮助/参数错误按标准抛SystemExit；MemoryError及内部编程错误不伪装配置错误。
    副作用: 导入读取两配置并发布；静态命令只读计划；run分析后发布到新目录。
    """
    arguments = _parser().parse_args(argv)
    operation = {'legacy': '导入', 'guide': '资料读取'}.get(arguments.command, '计划')
    try:
        if arguments.command == 'guide':
            # 默认只定位已经存在的README；显式output才生成独立副本。
            from .user_guide import export_guide, guide_path
            print(export_guide(arguments.output) if arguments.output else guide_path(arguments.language))
            return 0
        if arguments.command == 'config':
            from .configuration.cli import run_configuration_cli
            return run_configuration_cli(arguments)
        if arguments.command == 'legacy':
            return _run_import(arguments)
        if arguments.command == 'batch':
            from .batch.cli import run_batch_cli
            return run_batch_cli(arguments)
        # 帮助和参数错误先由argparse结束；只有实际计划命令才加载计划依赖。
        from .analysis_cli import run_static, run_analysis
        return run_analysis(arguments) if arguments.command == 'run' else run_static(arguments)
    except KeyboardInterrupt:
        # 发布器已尝试最小收尾并保恢复owner；CLI退出后系统还会关闭进程持有的FD。
        if arguments.command == 'legacy':
            message = '导入已取消；目标目录中的原文和迁移报告可用于核对已保存内容。'
        elif arguments.command == 'run':
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
        file_error = any(isinstance(cause,OSError) for cause in _cause_chain(error))
        if arguments.command in ('validate','explain') and arguments.format=='json':
            from .planning.checks import PlanValidationError
            if isinstance(error,PlanValidationError):
                print(json.dumps(dict(valid=False,error=error.to_dict()),ensure_ascii=False,allow_nan=False))
                return 1 if file_error else 2
        print(operation + ('文件操作失败：' if file_error else '配置错误：') + str(error), file=sys.stderr)
        return 1 if file_error else 2
