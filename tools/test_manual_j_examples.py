"""核对DOC-REVIEW-10的任务路由、默认结果读法及可运行YAML。

使用当前源码和公开CLI；所有新结果写入--output指定的新目录。教学输入只读，
期望值来自示例手算，验证不新增产品输出选项，也不修改示例并行设置。
"""
import argparse
import csv
from datetime import datetime
import importlib.util
import json
from math import ulp
import os
from pathlib import Path
import subprocess
import sys

from ruamel.yaml import YAML

YAML_READER = YAML(typ='safe', pure=True)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'Docs/Current/examples'


def task_cards():
    """核对双语意图路由和验证命令。参数: 无。返回: 查询数。异常: 内容或文件不符。"""
    module = importlib.util.spec_from_file_location('manual_lookup', ROOT/'Docs/AI/lookup.py')
    lookup = importlib.util.module_from_spec(module)
    module.loader.exec_module(lookup)
    queries = 0
    for language in ('zh', 'en'):
        for term in ('积分器', 'integrator', '通用时间积分器', 'general time integrator',
                     'integral', '高性能积分器', 'high-performance integrator'):
            expected = 'FAST_MESSAGE_ENERGY' if '高性能' in term or term.startswith('high-') else 'GENERAL_TIME_INTEGRAL'
            matches = lookup.query('task', term, language=language)
            assert matches and matches[0]['id'] == expected, (language, term, matches)
            queries += 1
        folder = ROOT/'Docs/AI'/('en' if language == 'en' else '')
        cards = json.loads((folder/'tasks.json').read_text(encoding='utf8'))['tasks']
        for card in cards:
            assert (folder/card['example']).is_file(), card['id']
            assert card['example'] in card['verify'], card['id']
            # 纯排错卡可只验证配置；其余卡必须给出能产生所承诺结果的执行入口。
            if card['id'] != 'FIX':
                assert any(token in card['verify'] for token in (' run ', ' batch ', 'run_analysis.py', 'host_extensions.py')), card['id']
    return queries


def command(arguments, folder, name):
    """运行一条公开命令并保留完整日志。参数: 参数/证据目录/名称。返回: None。异常: 子命令失败。"""
    environment = dict(os.environ, PYTHONPATH=str(ROOT/'src'), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    with (folder/(name+'.log')).open('w', encoding='utf8') as log:
        completed = subprocess.run([sys.executable, '-X', 'utf8', '-B', *map(str, arguments)],
            cwd=folder, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    assert completed.returncode == 0, (name, completed.returncode)


def published(folder):
    """按完成清单读取实际CSV。参数: 单次新结果目录。返回: 清单和各表记录。异常: 发布不完整。"""
    path, = folder.glob('*manifest*.json')
    manifest = json.loads(path.read_text(encoding='utf8'))
    assert manifest['status'] == 'completed'
    tables = []
    for item in manifest['outputs']:
        target = folder/item['name']
        if target.suffix == '.csv':
            with target.open(encoding='utf-8-sig', newline='') as stream:
                tables.append(list(csv.DictReader(stream)))
    return manifest, tables


def run_examples(output):
    """使用当前默认发布重算手算例。参数: 新证据目录。返回: 运行个数。异常: 值、表头、清单不符。"""
    cases = (('calculation-minimal.yaml', 30.), ('continuous-parallel.yaml', 38.),
             ('conditional-energy.yaml', 4000.*61/3600000))
    for filename, expected in cases:
        name = Path(filename).stem
        destination = output/name
        command(['-m', 'chronaxis', 'run', EXAMPLES/filename, '--output', destination], output, name)
        _, tables = published(destination)
        row, = tables[0]
        if name == 'conditional-energy':
            # 先乘J到kWh的换算系数与最后做除法，可相差一个binary64末位。
            assert abs(float(row['energy_kwh（kWh）'])-expected) <= ulp(expected)
            assert row['energy_kwh：状态'] == '完整'
            assert row['开始时间（s）'] == '61' and row['结束时间（s）'] == '122'
            assert 'parent_id' not in row and 'event_id' not in row
        else:
            assert float(row['energy（J）']) == expected and row['energy：状态'] == '完整'
    # ASC、BLF、批量子计划与两种连续归并均沿同一条贡献公式。
    fast = (('analysis.yaml', 800.), ('analysis-blf.yaml', 800.), ('batch-analysis.yaml', 800.),
            ('session.yaml', 1200.), ('session-time-order.yaml', 1200.))
    for filename, expected in fast:
        name = 'fast-'+Path(filename).stem
        plan = EXAMPLES/'fast'/filename
        config = YAML_READER.load(plan.read_text(encoding='utf8'))
        assert all('period' not in signal and 'valid_for' not in signal for signal in config['signals'])
        assert config['message_calculations'][0]['expr'] == 'power * frame_duration'
        destination = output/name
        command(['-m', 'chronaxis', 'fast', 'run', plan, '--output', destination], output, name)
        manifest, tables = published(destination)
        row, = tables[0]
        assert set(row) == {'计算项', '结果', '单位', '状态', '说明'}
        assert row['计算项'] == 'energy' and float(row['结果']) == expected
        assert row['单位'] == 'J' and row['状态'] == '完整' and row['说明'] == ''
        counts, = manifest['execution']['calculation_counts']
        assert counts['targets'] == counts['valid'] == counts['selected'] == int(expected/400)
    return len(cases)+len(fast)


def generated_yaml(output):
    """核生成器实际执行的是三份带注释YAML。参数: 证据目录。返回: 格式数。异常: 内容或数值不符。"""
    destination = output/'can-demo'
    command([EXAMPLES/'prepare_can_examples.py', '--output', destination], output, 'prepare-can')
    for name in ('asc', 'blf', 'mixed'):
        text = (destination/(name+'.yaml')).read_text(encoding='utf8')
        raw = json.loads((destination/(name+'.json')).read_text(encoding='utf8'))
        assert YAML_READER.load(text) == raw
        assert len({line.index('#') for line in text.splitlines()}) == 1
        assert raw['execution']['process_count'] == 4
    evidence = json.loads((destination/'verification.json').read_text(encoding='utf8'))
    assert len(evidence['records']) == 3
    for row in evidence['records']:
        assert row['values'] == {'energy': 38., 'sample_average': 6., 'time_average': 38./6.}
    return 3


def main():
    """执行专项并保存摘要。参数: CLI新输出目录。返回: None。异常: 原检查失败；不覆盖旧证据。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'task': 'DOC-REVIEW-10', 'device_label': 'home', 'author': 'liuyaoze',
              'time': datetime.now().astimezone().isoformat()}
    report.update(lookup_queries=task_cards(), published_examples=run_examples(output),
                  generated_formats=generated_yaml(output), status='passed')
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
