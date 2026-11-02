"""在同一计划中运行请求响应、迟滞、窗口变化和开始/结束规则。

输入是明确构造的16秒合成试验，不是车辆标定。四类规则共享一次来源读取；
窗口和均值仍按原信号计算。手算结果由常量给出，不能由被测引擎反推期望。
产物保存在work下的唯一目录，关闭后检查新分析层内存账本归零。
"""

import json
from math import isclose
from pathlib import Path
from uuid import uuid4

from chronaxis import AnalysisPlan, AnalysisRunner


def combined_config():
    """构造一个含四类规则的公开计划字典。

    参数: 无。返回: 独立JSON兼容dict。异常: 原示例文件读取或解析错误。
    """
    root = Path(__file__).resolve().parent
    names = ('command_response', 'stability', 'window_delta', 'start_end')
    plans = [json.loads((root / f'{name}_plan.json').read_text(encoding='utf-8')) for name in names]
    raw = plans[0]
    raw['dataset']['domain']['end'] = '16s'
    raw['dataset']['name'] = 'combined_demo'
    raw['windows'], raw['calculations'] = [], []

    # 同刻输入合并；其余时刻明确给出最近值，使CSV与内存输入具有相同样本。
    updates = {}
    for index, plan in enumerate(plans):
        for row in plan['sources'][0]['rows']:
            updates.setdefault(int(row['time'][:-1]), {}).update(row['values'])
        if index:
            raw['signals'].extend(plan['signals'])
            raw['rules'].extend(plan['rules'])
            for window in plan.get('windows', []):
                window['name'] = f'{names[index]}_{window['name']}'
                raw['windows'].append(window)
            for calculation in plan.get('calculations', []):
                calculation['name'] = f'{names[index]}_{calculation['name']}'
                if isinstance(calculation.get('scope'), dict) and 'window' in calculation['scope']:
                    calculation['scope']['window'] = f'{names[index]}_{calculation["scope"]["window"]}'
                raw['calculations'].append(calculation)
    values, rows = {}, []
    for second in range(17):
        values.update(updates.get(second, {}))
        rows.append(dict(time=f'{second}s', values=dict(values)))
    raw['sources'][0]['rows'] = rows
    raw['outputs'] = dict(tables='csv')
    return raw


def check_result(result, *, alarm=True):
    """与独立手算的活动、配对及时间均值核对，返回便于阅读的摘要。

    参数: result为未关闭结果；alarm表示本例温度是否高于阈值。
    返回: JSON兼容摘要。异常: AssertionError表示与已声明手算值不符。
    """
    event_rows = {row.event_id: row for row in result.iter_events()}
    segment_rows = {row.segment_id: row for row in result.iter_segments()}
    events = {}
    for row in result.iter_events():
        event = row
        events.setdefault(event.rule_id, []).append(
            (event.start_ns / 10**9, None if event.end_ns is None else event.end_ns / 10**9, event.status))
    # 85℃维持3秒，77℃维持6秒，9秒降到75℃；中间区间不能提前解除报警。
    assert events.get('alarm', []) == ([(0, 9, 'closed')] if alarm else [])
    assert [row.confirmed_ns / 10**9 for row in result.iter_events()
            if row.rule_id == 'change'] == [4, 12]
    assert events['cycle'] == [(0, 2, 'closed'), (4, 9, 'timeout'), (11, 14, 'closed')]
    pairs = [(event_rows[row.request_id].confirmed_ns / 10**9, row.status,
              row.decided_ns / 10**9,
              None if row.delay_ns is None else row.delay_ns / 10**9)
             for row in result.iter_sequences()]
    assert pairs == [(1, 'matched', 3, 2), (4, 'indeterminate', 6, None),
                     (7, 'matched', 9, 2), (10, 'no_response', 12, None)]
    calculations = {}
    # 公共表按父ID排序；按实际窗口核对，不能假设迭代顺序就是时间顺序。
    def window_for(row):
        """按父对象取得窗口。参数: 计算行。返回: 事件或片段。异常: 父ID缺失。"""
        return event_rows[row.parent_id] if row.scope == 'event' else segment_rows[row.parent_id]
    calculation_rows = sorted(result.iter_calculations(), key=lambda row: (row.calculation_id, window_for(row).start_ns))
    for row in calculation_rows:
        calculations.setdefault(row.calculation_id, []).append(row.value)
    for name in ('start_end_event_average', 'start_end_segment_average'):
        assert [(window_for(row).start_ns / 10**9, window_for(row).end_ns / 10**9)
                for row in calculation_rows if row.calculation_id == name] == [(0, 2), (4, 9), (11, 14)]
    expected = dict(window_delta_average=[2.5, 2.5],
                    start_end_event_average=[10, 52, 110],
                    start_end_segment_average=[10, 52, 110])
    if alarm:
        expected.update(stability_event_mean=[239 / 3], stability_segment_mean=[239 / 3])
    assert set(calculations) == set(expected), calculations
    for name, values in expected.items():
        actual = calculations[name]
        assert len(actual) == len(values) and all(isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
                                                  for a, b in zip(actual, values)), (name, actual, values)
    assert len(list(result.iter_segments())) == (6 if alarm else 5)
    return dict(device_label='home', data_kind='synthetic', activities=events, pairs=pairs, calculations=calculations)


def main():
    """通过正式API运行、核对并发布组合例子。

    参数: 无。返回: None，打印摘要和输出路径。异常: 原I/O/分析错误或手算断言。
    """
    work = Path(__file__).resolve().parents[1] / 'work/m3-accept-home-20261023/example' / uuid4().hex
    work.mkdir(parents=True)
    raw = combined_config()
    (work / 'plan.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')
    result = AnalysisRunner().run(AnalysisPlan.from_dict(raw), work_dir=work / 'run')
    budget = result.spool.budget
    try:
        summary = check_result(result)
        summary['output'] = str(result.write(work / 'output').output_dir)
    finally:
        result.close()
    assert budget.ram_bytes == 0
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
