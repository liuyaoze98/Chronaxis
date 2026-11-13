"""核对教学结果的业务值、单位和发布结构，不把旧文件摘要当作数值真值。

输入为功率统计示例的CSV或本次运行清单；输出独立手算值或校核摘要。
只用标准库读取指定结果，不运行分析、不改文件。固定字段精确比较，浮点数按
既有1e-12容差比较；运行编号、时间和文件名检查有效性，不要求跨次相同。
"""

import csv
from datetime import datetime
import hashlib
import json
from math import isclose, sqrt
from pathlib import Path


def runtime_fingerprint(root=None) -> str:
    """标识实际导入产品的源码，使产品变化后旧结果快照明确失效。

    参数: root为测试可指定的包目录，省略时使用已导入chronaxis的真实目录。
    返回: 源码路径与内容的合成SHA256。异常: 缺少合法模块或文件读取错误。
    只纳入合法模块路径，排除缓存和同步冲突副本；统一文本换行避免跨平台误报。
    """
    import chronaxis
    folder = Path(root) if root is not None else Path(chronaxis.__file__).resolve().parent
    entries = {}
    for path in sorted(folder.rglob('*.py')):
        relative = path.relative_to(folder)
        if all(part.isidentifier() for part in (*relative.parts[:-1], relative.stem)):
            entries[relative.as_posix()] = hashlib.sha256(path.read_text(encoding='utf-8-sig').encode('utf-8')).hexdigest()
    assert entries, '未找到实际运行产品源码，不能确认示例生成基线'
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def power_statistics_expected():
    """给出合成台架的独立真值，避免从当前程序输出反推期望。

    参数: 无。返回: 计算名称到(数值,单位)的字典。异常: 无主动异常。
    五条读数0/10/0/20/0W分别产生样本统计；时间权重为4/3/2秒。
    """
    return {
        'cycles': (1, '1'), 'loads': (2, '1'), 'readings': (5, '1'), 'starts': (2, '1'),
        'held_variance': (5000 / 81, 'W^2'), 'held_spread': (sqrt(5000 / 81), 'W'),
        'held_rms': (sqrt(1100 / 9), 'W'), 'reading_variance': (80, 'W^2'),
        'reading_spread': (8, 'W'), 'reading_rms': (10, 'W'),
        'reading_median': (0, 'W'), 'reading_p95': (18, 'W'),
    }


def verify_power_statistics_csv(path):
    """按独立合同检查功率统计的中文会话表。

    参数: path为实际CSV路径。返回: 名称到实际数值的字典。
    异常: AssertionError表示表头、行数、状态或数值不符；I/O与数值解析错误传播。
    不使用另一后端或教学快照作为真值，参考和NumPy各自对照同一手算结果。
    """
    expected = power_statistics_expected()
    # 表头的顺序、名称、单位和固定状态文本都属于确定输出，必须精确一致。
    headers = [field for name in sorted(expected)
               for field in (f'{name}（{expected[name][1]}）', name + '：状态', name + '：说明')]
    # CSV允许UTF-8 BOM；扣除编码标记和行终止符后，确定性表头按UTF-8字节核对。
    first_line = Path(path).read_bytes().removeprefix(b'\xef\xbb\xbf').splitlines()[0]
    assert first_line == ','.join(headers).encode('utf-8'), '功率统计表头字节或单位不符'
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == headers, ('功率统计表头或单位不符', reader.fieldnames, headers)
        rows = list(reader)
    assert len(rows) == 1, ('功率统计会话表应为一行', len(rows))
    row = rows[0]
    actual = {}
    for name, (value, unit) in expected.items():
        assert row[name + '：状态'] == '完整' and row[name + '：说明'] == '', (name, row)
        actual[name] = float(row[f'{name}（{unit}）'])
        assert isclose(actual[name], value, rel_tol=1e-12, abs_tol=1e-12), (name, actual[name], value)
    return actual


def verify_power_statistics_publication(manifest_path):
    """检查一次实际发布，再按稳定业务合同校核会话表。

    参数: manifest_path为本次write或CLI返回的完成清单。返回: 手算核对后的数值字典。
    异常: AssertionError表示发布结构或业务结果不符；JSON、日期和I/O错误传播。
    运行身份和绝对时间属于动态字段，只核合同；所有输出必须在本次清单目录内。
    """
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_bytes())
    assert manifest['status'] == 'completed', manifest['status']
    run = manifest['run']
    assert isinstance(run['run_id'], str) and run['run_id'], '运行标识缺失'
    started = datetime.fromisoformat(run['started_at'])
    ended = datetime.fromisoformat(manifest['ended_at'])
    assert started.utcoffset() is not None and ended.utcoffset() is not None and ended >= started
    tables = []
    for item in manifest['outputs']:
        target = (path.parent / item['name']).resolve()
        assert target.is_relative_to(path.parent) and target.is_file(), item['name']
        assert target.stat().st_size == item['bytes'], item['name']
        if target.name.startswith('会话结果_') and target.suffix == '.csv':
            tables.append(target)
    assert len(tables) == 1, ('缺少唯一的会话结果表', tables)
    return verify_power_statistics_csv(tables[0])
