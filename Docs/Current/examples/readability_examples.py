"""运行当前文档中的表达式、分批、缺失处理和时间偏移例子。

表达式输入是明示的常数与一条缺值，预期答案直接写在下方表中；两个后端独立
求值。完整Runner部分复用配套5行CSV，比较batch_rows=1/7和report/strict，
再用两份差2秒的内存输入验证offset。在系统临时目录或指定父目录创建独立输出，
不读取RefProjects，不改原配置；最终输出JSON检查摘要。不测试真实日志性能。
"""

import json
import os
from dataclasses import replace
from pathlib import Path
from example_support import new_output

import numpy as np
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core import (MemoryRow, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType, SourceSpec, TimebaseSpec, TimeType,
                            compile_expression, evaluate_memory_reference)
from chronaxis.core.expression_numpy import evaluate_memory_numpy


def expression_bindings():
    """为表达式示例建立一份能手算的固定输入。

    参数: 无。返回: 含浮点/整数/bool/枚举及缺值的SignalBindings。
    异常: 输入模型构造错误原样传播。时间0和1均为纳秒，所有值有效期10纳秒。
    """
    clock = TimebaseSpec('doc_clock', TimeType.RELATIVE, 'doc_expression_examples')
    values = {'x': 6.0, 'y': 2.0, 'current': 10.0, 'voltage': 400.0,
              'period': 0.1, 'power': 4000.0, 'alarm': True, 'mode': 1,
              'i': 6, 'u': 6, 'imin': -(2 ** 63), 'missing': None}
    source = SourceSpec('table', clock, (MemoryRow(0, values, 0), MemoryRow(1, values, 1)),
                        observation_start_ns=0, observation_end_ns=1)
    session = SessionSpec('doc_session', clock, 0, 1, (source,))
    definitions = []
    units = {'current': 'A', 'voltage': 'V', 'period': 's', 'power': 'W'}
    for name in values:
        dtype = {'i': SignalDType.INT64, 'imin': SignalDType.INT64,
                 'u': SignalDType.UINT64, 'alarm': SignalDType.BOOL,
                 'mode': SignalDType.ENUM}.get(name, SignalDType.FLOAT64)
        options = {'choices': ((0, 'idle'), (1, 'charge'))} if name == 'mode' else {}
        definitions.append(SignalDefinition(name, 'table', name, dtype, units.get(name, '1'), 10, **options))
    return SignalBindings(session, tuple(definitions))


def check_expressions():
    """逐项核对文档允许的运算、缺失结果及禁止写法。

    参数: 无。返回: 每个用例的输入式与预期结果记录。
    异常: 与明示答案不符或应拒绝却通过时抛AssertionError；意外运行错误保留。
    """
    bindings = expression_bindings()
    accepted = [
        ('x + y', 8.0), ('x - y', 4.0), ('x * y', 12.0), ('x / y', 3.0),
        ('+x', 6.0), ('-x', -6.0), ('x == y', False), ('x != y', True),
        ('x < y', False), ('x <= 6', True), ('x > y', True), ('x >= 6', True),
        ('0 <= x < 10', True), ('x > 5 and y < 3', True), ('x < 5 or alarm', True),
        ('not alarm', False), ('abs(-x)', 6.0), ('abs(-3)', 3),
        # 当前表达式支持平方和平方根；负数平方根是运行时无效值。
        ('square(x)', 36.0), ('sqrt(square(x))', 6.0), ('sqrt(-x)', None),
        ('isclose(voltage, 400, atol=0.1, rtol=0)', True),
        ('isclose(102, 100, atol=0, rtol=0.02)', True),
        ('x + y * 2', 10.0), ('(x + y) * 2', 16.0), ('1e3', 1000.0),
        ('True', True), ('False', False), ('True == alarm', True),
        ("mode == 'charge'", True), ("mode != 'idle'", True),
        ('voltage * current', 4000.0), ('voltage / current', 40.0), ('power * period', 400.0),
        ('current * period', 1.0), ('voltage + 1', 401.0), ('current / 2', 5.0),
        ('i / 2', 3.0), ('i < 18446744073709551616', True), ('i == u', True),
        ('missing > 0', None), ('False and missing > 0', False),
        ('True or missing > 0', True), ('True and missing > 0', None),
        ('False or missing > 0', None), ('not (missing > 0)', None),
        ('(missing > 0) and (missing < 1)', None),
        ('(missing > 0) or (missing < 1)', None),
        ('x / 0', None), ('abs(imin)', None), ('i + 9223372036854775807', None),
    ]
    rejected = [
        'x ** 2', 'x % 2', 'x // 2', 'x @ y', 'i & 1', 'i | 1', 'i ^ 1', '~i',
        'i << 1', 'i >> 1', 'x in [1, 2]', 'x not in [1, 2]', 'x is None', 'x is not None',
        'battery.current', 'x[0]', 'x[1:3]', 'min(x,y)', 'round(x)',
        'float(i)', "signal('x')", 'x.mean()', 'abs(*[x])', 'abs(x=x)',
        'isclose(x,y)', 'isclose(x,y,atol=0.1)', 'isclose(x,y,atol=1/10,rtol=0)',
        'isclose(x,y,atol=x,rtol=0)', 'isclose(x,y,atol=-1,rtol=0)',
        'isclose(x,y,**{})', '[x,y]', "{'x':x}", '[v for v in x]',
        'x if alarm else y', 'x = 2', '(x := 2)', 'lambda x: x', "__import__('os')",
        'None', '1j', "b'abc'", "'a'+'b'", '1e309', 'true',
        'x and y', 'not x', 'alarm + True', "mode < 'charge'", "mode == 'charging'",
        'x + i', 'x > i', 'voltage + current', 'unknown_signal',
    ]
    records = []
    for expression, expected in accepted:
        compiled = compile_expression(expression, bindings)
        if expression == 'voltage / current':
            # 400V/10A得到40Ohm；当前单位代数允许该物理量。
            assert compiled.root.unit == 'Ohm'
        reference = evaluate_memory_reference(compiled, (0,))[0].value
        array = evaluate_memory_numpy(compiled, np.array([0], dtype=np.int64)).value
        # invalid位置可能有占位值，比较时必须先查看valid。
        values = [reference.value if reference.valid else None,
                  array.values[0].item() if array.valid[0] else None]
        assert values == [expected, expected], (expression, values, expected)
        records.append({'expression': expression, 'expected': expected, 'both_backends': 'passed'})
    for expression in rejected:
        try:
            compile_expression(expression, bindings)
        except ValueError as error:
            records.append({'expression': expression, 'rejected': True, 'reason': str(error)})
        else:
            raise AssertionError(('应在检查表达式时拒绝', expression))
    return records


def collect_calculations(plan, backend, directory):
    """运行一个计划并读取本例有限数量的指标。

    参数: plan为AnalysisPlan；backend为计算实现名；directory为全新工作目录。
    返回: 指标行列表，仅供本例少量合成输出比较。异常: 分析/关闭错误保留。
    """
    with AnalysisRunner(backend=backend).run(plan, work_dir=directory) as result:
        rows = result.iter_calculations()
        try:
            return list(rows)
        finally:
            rows.close()


def check_runtime(destination):
    """验证分批不切断事件、report/strict输出、覆盖门槛与平坦结果字段。

    参数: destination为本次新目录。返回: 8组运行摘要。
    异常: 任何预期数值/状态不符抛AssertionError；产品错误不吞掉。
    """
    here = Path(__file__).resolve().parent
    config = json.loads((here / 'execution-comparison.json').read_text(encoding='utf-8'))
    records = []
    for backend in ('reference', 'numpy'):
        for batch_rows in (1, 7):
            for policy in ('report', 'strict'):
                config['execution'].update(backend=backend, batch_rows=batch_rows, partial_policy=policy)
                # 设置90%门槛，证明report仍保留已知部分，并标明覆盖不足。
                for metric in config['calculations']:
                    metric['minimum_coverage'] = 0.9
                plan = AnalysisPlan.from_dict(config, base_dir=here)
                rows = collect_calculations(plan, backend, destination / f'{backend}-{batch_rows}-{policy}')
                session = next(row for row in rows if row.calculation_id == 'session_energy')
                assert session.value == (32000.0 if policy == 'report' else None)
                assert session.status == ('partial' if policy == 'report' else 'indeterminate')
                assert session.coverage_status == 'indeterminate'
                assert [row.value for row in rows if row.calculation_id == 'event_energy'] == [4000.0, 4000.0]
                assert [row.value for row in rows if row.calculation_id == 'segment_energy'] == [24000.0]
                records.append({'backend': backend, 'batch_rows': batch_rows, 'policy': policy,
                                'session_energy': session.value, 'status': session.status})
    return records


def check_clock_offset(destination):
    """验证同一时刻在两份输入中相差2秒时如何填写offset。

    参数: destination为本次输出目录。返回: 两后端的均值结果。
    异常: 时间转换或数值与预期8不符时抛错；不推断真实设备同步关系。
    """
    config = {
        'config_version': 4,
        'execution': {'process_count': 1},  # 内存和多来源会话使用单进程。
        'dataset': {'name': 'clock_demo', 'domain': {'start': '0s', 'end': '1s'}},
        'sources': [
            {'name': 'a', 'source_type': 'memory', 'time': {'clock': 'test_button'},
             'rows': [{'time': '0s', 'values': {'x': 6.0}}, {'time': '1s', 'values': {'x': 6.0}}]},
            {'name': 'b', 'source_type': 'memory', 'time': {'clock': 'test_button', 'offset': '-2s'},
             'rows': [{'time': '2s', 'values': {'y': 2.0}}, {'time': '3s', 'values': {'y': 2.0}}]},
        ],
        'signals': [{'name': name, 'source': source, 'field': name, 'dtype': 'float64', 'unit': '1', 'valid_for': '2s'}
                    for name, source in (('x', 'a'), ('y', 'b'))],
        'derived': {'total': {'expr': 'x + y', 'unit': '1'}},
        'calculations': [{'name': 'mean', 'operation': 'time_weighted_mean', 'expr': 'total', 'unit': '1'}],
    }
    plan = AnalysisPlan.from_dict(config)
    values = []
    for backend in ('reference', 'numpy'):
        rows = collect_calculations(plan, backend, destination / f'clock-{backend}')
        assert len(rows) == 1 and rows[0].value == 8.0 and rows[0].status == 'complete'
        values.append({'backend': backend, 'mean_after_offset': rows[0].value})
    return values


def main():
    """执行所有文档例子并保存本次结果。

    参数: 无。返回: None；打印检查数和摘要路径。异常: 任一验证失败即停止并保留已写内容。
    """
    destination, label = new_output('readability-manual-')
    expressions = check_expressions()
    runtime = check_runtime(destination)
    clocks = check_clock_offset(destination)
    summary = {'device_label': label,
               'expressions': expressions, 'runtime': runtime, 'clocks': clocks}
    output = destination / 'checks.json'
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'expression_cases': len(expressions), 'runtime_cases': len(runtime),
                      'clock_cases': len(clocks), 'status': 'passed', 'evidence': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
