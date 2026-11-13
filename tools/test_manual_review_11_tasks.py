"""从中英文任务入口运行条件能量、单位换算和ASC导出，并核对实际发布内容。

输入为一个全新证据目录；输出CLI日志和校核摘要。教学配置与输入只读，错误结果
探测只修改新目录内的副本，不改变产品行为或生成完整发行物。
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import cantools

from check_ai_install import verify_review_task

ROOT = Path(__file__).resolve().parents[1]


def run_examples(output):
    """按各语言卡片的真实路径运行。参数: 新证据目录。返回: 六次结果证据。异常: 命令或结果错误。"""
    environment = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    results = []
    for language in ('zh', 'en'):
        base = ROOT / 'Docs/AI' / ('en' if language == 'en' else '')
        tasks = json.loads((base / 'tasks.json').read_bytes())['tasks']
        for name in ('CONDITION_ENERGY', 'UNITS', 'EXPORT'):
            task = next(row for row in tasks if row['id'] == name)
            needed = {'CONDITION_ENERGY': ('energy_kwh：说明',),
                      'UNITS': ('5000', '7000', 'maximum_current：说明'),
                      'EXPORT': ('exports.index_file', 'exports.directory', 'directory', 'manifest.json')}[name]
            assert all(token in task['check'] for token in needed), (language, name, task['check'])
            if name == 'UNITS':
                assert '2000' not in task['check'], task['check']
            destination = output / (language + '-' + name)
            command = [sys.executable, '-X', 'utf8', '-B', '-m', 'chronaxis', 'run', task['example'],
                       '--output', str(destination)]
            completed = subprocess.run(command, cwd=base, env=environment, capture_output=True,
                                       encoding='utf8', timeout=120)
            log = output / (language + '-' + name)
            log.with_suffix('.stdout').write_text(completed.stdout, encoding='utf8')
            log.with_suffix('.stderr').write_text(completed.stderr, encoding='utf8')
            assert completed.returncode == 0, (name, completed.returncode, completed.stderr)
            publication = json.loads(completed.stdout)
            assert publication['status'] == 'completed', publication
            result = verify_review_task(Path(publication['manifest']), name)
            results.append(dict(language=language, configuration=task['example'], **result))
    return results


def verify_conversion_inputs():
    """核实换算卡使用的四个DBC物理值。参数: 无。返回: mA及A读数。异常: 夹具或解码结果变化。"""
    folder = ROOT / 'Docs/Current/examples/data/can'
    database = cantools.database.load_file(folder / 'teaching.dbc')
    values = []
    for line in (folder / 'signal-types.asc').read_text(encoding='utf8').splitlines()[1:]:
        fields = line.split()
        if fields[2] == '101':
            payload = bytes.fromhex(' '.join(fields[6:]))
            values.append(database.decode_message(0x101, payload)['Current_mA'])
    assert values == [5000., 7000., 5000., 5000.], values
    amperes = [value / 1000 for value in values]
    assert amperes == [5., 7., 5., 5.], amperes
    return dict(decoded_ma=values, converted_a=amperes)


def verify_process_boundaries():
    """核对进程上限1与归并方式组合。参数: 无。返回: 三个静态校验结果。异常: 合法范围变化。"""
    from chronaxis.planning.process_execution import process_execution_errors

    def source(name, merge):
        """构造只含本校验所用属性的来源。参数: 名称/归并方式。返回: 声明对象。异常: 无。"""
        return SimpleNamespace(name=name, source_type='can_asc',
                               config=SimpleNamespace(file_merge=merge, decode_scope='requested'))

    cases = [('multi_concatenate', [source('a', 'concatenate'), source('b', 'concatenate')], False),
             ('multi_time_order', [source('a', 'time_order'), source('b', 'concatenate')], True),
             ('single_time_order', [source('a', 'time_order')], False)]
    results = {}
    for name, sources, rejected in cases:
        errors = process_execution_errors(SimpleNamespace(execution=SimpleNamespace(process_count=1), sources=sources))
        assert bool(errors) == rejected, (name, errors)
        results[name] = list(errors)
    for language in ('', 'en/'):
        text = (ROOT / ('Docs/Current/' + language + 'ai-guide.md')).read_text(encoding='utf8')
        assert 'execution.process_count: 1' in text and 'file_merge: concatenate' in text and 'time_order' in text
        assert 'use one worker' not in text
    return results


def verify_rejection(output, results):
    """确认实际结果断言能拒绝错误说明及导出格式。参数: 新目录/正确结果。返回: 拒绝次数。异常: 漏检。"""
    for task in ('CONDITION_ENERGY', 'EXPORT'):
        result = next(row for row in results if row['language'] == 'zh' and row['task'] == task)
        original = Path(result['manifest'])
        destination = output / ('invalid-' + task)
        shutil.copytree(original.parent, destination)
        if task == 'CONDITION_ENERGY':
            import csv
            table = destination / Path(result['table']).name
            with table.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                fields, rows = reader.fieldnames, list(reader)
            rows[0]['energy_kwh：说明'] = '缺失数据'
            with table.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        else:
            detail_path = destination / Path(result['export_manifest']).relative_to(original.parent)
            detail = json.loads(detail_path.read_bytes())
            detail['format'] = 'blf'
            detail_path.write_text(json.dumps(detail, ensure_ascii=False), encoding='utf8')
        try:
            verify_review_task(destination / original.name, task)
        except AssertionError:
            continue
        raise AssertionError('未拒绝错误结果：' + task)
    return 2


def check(output, device):
    """执行本轮专项并保存摘要。参数: 新目录/实际设备标签。返回: 摘要。异常: 任何校核失败。"""
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = run_examples(output)
    report = dict(task='DOC-REVIEW-11/J05/J07/J08', device_label=device, author='liuyaoze',
                  time=datetime.now().astimezone().isoformat(), published=results,
                  conversion=verify_conversion_inputs(), process_boundaries=verify_process_boundaries(),
                  rejected_results=verify_rejection(output, results), status='passed')
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device-label', required=True)
    args = parser.parse_args()
    report = check(args.output, args.device_label)
    print(json.dumps(dict(status=report['status'], published=len(report['published']),
                          rejected_results=report['rejected_results']), ensure_ascii=False))
