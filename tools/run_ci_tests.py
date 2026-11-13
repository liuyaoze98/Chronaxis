"""按公开源码清单运行CI分组，并记录全部测试模块的唯一归属。

输入是当前源码树及core/input/docs/install分组；所有公开unit测试均进入一个组，
没有专门分类的新测试默认进入core。仅沿用公开导出已有的内部测试排除清单，
不会因导入失败、缺少Node或资料锁漂移而跳过。报告写到显式路径；运行状态原样返回。
"""

import argparse
import json
import os
from pathlib import Path
import sys
import unittest

from export_public_source import EXCLUDED_TESTS, PUBLIC_TOOLS, included


ROOT = Path(__file__).resolve().parents[1]
GROUPS = ('core', 'input', 'docs', 'install')
INSTALL_MODULES = {'test_software_version', 'test_user_flow_dependencies'}
DOC_PREFIXES = ('test_ai_', 'test_english_', 'test_manual_', 'test_guide_')
INPUT_TOKENS = ('asc', 'blf', 'can', 'csv', 'dbc', 'input', 'export')


def group_for(module):
    """确定unit模块的唯一执行组，没有专门分类的新模块默认进入core。

    参数: module为相对于tests/unit的点分模块名称。返回: 四种分组名之一。
    异常: 无；不导入或执行测试，分组不决定是否纳入测试总集。
    """
    name = module.rsplit('.', 1)[-1]
    if name in INSTALL_MODULES:
        return 'install'
    if name.startswith(DOC_PREFIXES):
        return 'docs'
    if any(token in name.removeprefix('test_').split('_') for token in INPUT_TOKENS):
        return 'input'
    return 'core'


def inventory(root=ROOT):
    """枚举全部公开unit及已发布的文档工具测试，并验证无遗漏或重复。

    参数: root为当前仓库或独立公开树根目录。返回: 各组模块列表及实际排除文件列表。
    异常: ValueError为不存在的测试目录、模块重名、缺项或重复；不运行测试。
    """
    root = Path(root)
    unit = root / 'tests/unit'
    if not unit.is_dir():
        raise ValueError('缺少公开unit测试目录：' + str(unit))
    groups = {name: [] for name in GROUPS}
    excluded, expected = [], []
    # 递归发现新增测试，不能因未更新一份手工文件名列表而静默漏跑。
    for path in sorted(unit.rglob('test_*.py')):
        relative = path.relative_to(root).as_posix()
        if not included(relative):
            if path.name not in EXCLUDED_TESTS:
                raise ValueError('公开测试出现未说明的排除项：' + relative)
            excluded.append(relative)
            continue
        module = '.'.join(path.relative_to(unit).with_suffix('').parts)
        expected.append(module)
        groups[group_for(module)].append(module)
    # 工具测试也以发布白名单为准；与unit同名会造成import命中错误，因此直接报错。
    for path in sorted((root / 'tools').glob('test_*.py')):
        if path.name in PUBLIC_TOOLS:
            expected.append(path.stem)
            groups['docs'].append(path.stem)
    actual = [module for group in groups.values() for module in group]
    if not expected or len(actual) != len(set(actual)) or sorted(actual) != sorted(expected):
        raise ValueError('公开测试分组存在遗漏、重复或空测试总集')
    return groups, excluded


def main(argv=None):
    """运行所选组，保存模块清单和实际测试结果，失败返回非零退出码。

    参数: argv为可选命令行参数；--list-only只检查分组；--report为可选JSON报告。
    返回: int，全部通过或仅清单检查为0，任何测试错误/失败为1。
    异常: 文件系统和分组错误直接传播；不吞掉测试导入失败或变相跳过缺失工具。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=(*GROUPS, 'all'), default='all')
    parser.add_argument('--list-only', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    groups, excluded = inventory()
    summary = {'device_label': os.environ.get('CHRONAXIS_DEVICE_LABEL', 'pending'),
               'groups': groups, 'excluded_internal_tests': excluded,
               'group': args.group, 'executed': False}
    code = 0
    if not args.list_only:
        # 产品通过前置pip install -e .[test]导入；这里只加入测试及文档工具模块路径。
        for directory in (ROOT, ROOT / 'tools', ROOT / 'tests/unit'):
            sys.path.insert(0, str(directory))
        os.chdir(ROOT)
        modules = [module for group, items in groups.items()
                   if args.group in ('all', group) for module in items]
        if not modules:
            raise ValueError('所选CI组没有测试：' + args.group)
        loader = unittest.TestLoader()
        suite = unittest.TestSuite(loader.loadTestsFromName(module) for module in modules)
        result = unittest.TextTestRunner(verbosity=1, buffer=True).run(suite)
        summary.update(executed=True, tests_run=result.testsRun,
                       failures=[test.id() for test, _ in result.failures],
                       errors=[test.id() for test, _ in result.errors],
                       skipped=[{'test': test.id(), 'reason': reason} for test, reason in result.skipped],
                       passed=result.wasSuccessful())
        code = 0 if result.wasSuccessful() else 1
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # 控制台仅给数目和结果；完整模块清单及跳过原因由报告明确保存。
    print(json.dumps({'groups': {name: len(items) for name, items in groups.items()},
                      'excluded': len(excluded), 'tests_run': summary.get('tests_run'),
                      'passed': summary.get('passed'), 'report': str(args.report) if args.report else None},
                     ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
