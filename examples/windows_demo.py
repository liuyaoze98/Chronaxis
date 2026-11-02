"""用合成活动展示退出延迟片段、固定边沿窗口和两种能量scope。

0秒TRUE、1秒FALSE、2秒TRUE、3秒FALSE、6秒真实TRUE，观测[0,6)秒，
BOOL有效期十秒。立即确认产生[0,1)和[2,3)两活动；退出延迟三秒形成[0,6)片段。
功率恒定4000W，各原活动4000J，片段上下文24000J，不把中间FALSE改成TRUE。
start_only允许初始TRUE、固定三秒：触发0和真实末点6，2秒边沿被抑制。
末点窗口请求[6,9)，实际[6,6)，不贡献持续时间。
流程分别运行独立参考和NumPy内存检测、窗口与指标链，核对手算后打印JSON。
运行：PYTHONPATH=src时执行python -B examples/windows_demo.py。
不读取日志或DBC，不调用旧writer；完整内存小例不证明AnalysisRunner预算或旧模式文件迁移。
"""

# JSON只写标准输出，例子不发布文件。
import json
# typed输入与标准库参考实际入口。
from chronaxis.core import (Interval, MemoryRow, CalculationDefinition, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType as D, SourceSpec, TemporalRule, TimebaseSpec, TimeType,
                            WindowSpec, build_segments_reference, compile_expression, compute_memory_reference,
                            detect_memory_reference)
# 两个独立数组数值/边沿/窗口入口。
from chronaxis.core.temporal_memory_numpy import detect_memory_numpy
from chronaxis.core.windows_numpy import build_segments_numpy
from chronaxis.core.calculations_memory_numpy import compute_memory_numpy


def main():
    """运行两条完整内存链，按原活动和片段scope核对不同结果。

    参数: 无。
    返回: None；打印JSON说明原活动、片段和固定边沿请求。
    异常: 输入检查传播；手算或独立后端不符时抛RuntimeError。
    """
    # 原字段输入与公共合成起点显式声明，末点是真实更新。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'windows-demo-v1')
    data = ((0, {'active': True, 'power': 4000.}), (1_000_000_000, {'active': False}),
            (2_000_000_000, {'active': True}), (3_000_000_000, {'active': False}),
            (6_000_000_000, {'active': True, 'power': 4000.}))
    source = SourceSpec('table', clock, tuple(MemoryRow(time, value, index) for index, (time, value) in enumerate(data)),
                        observation_start_ns=0, observation_end_ns=6_000_000_000)
    bindings = SignalBindings(SessionSpec('session', clock, 0, 6_000_000_000, (source,)),
                              (SignalDefinition('active', 'table', 'active', D.BOOL, '1', 10_000_000_000),
                               SignalDefinition('power', 'table', 'power', D.FLOAT64, 'W', 10_000_000_000)))
    condition, power = compile_expression('active', bindings), compile_expression('power', bindings)
    domain = Interval(0, 6_000_000_000)
    # 立即确认仍保存两个真实活动，不用退出delay延长TRUE状态。
    rule = TemporalRule('activity', 'dataset', 'session', 'condition_duration')
    events = detect_memory_reference(condition, rule, batch_rows=1)
    array_events = detect_memory_numpy(condition, rule, batch_rows=2)
    window = WindowSpec('single', 'activity', 'activity', merge='exit_delay', exit_delay_ns=3_000_000_000)
    segments = build_segments_reference(events, window, domain)
    array_segments = build_segments_numpy(array_events, window, domain)
    if events != array_events or segments != array_segments or len(events) != 2 or len(segments) != 1:
        raise RuntimeError('活动或片段独立后端/手算不符')
    # 相同功率按不同明确scope归约，两条链分别运行。
    energy = []
    for scope, interval in [('event', Interval(event.start_ns, event.end_ns)) for event in events] + [('segment', segments[0].actual)]:
        spec = CalculationDefinition('energy', 'integral', interval, scope=scope)
        reference, array = compute_memory_reference(power, spec), compute_memory_numpy(power, spec)
        if reference != array or reference.value != (4000. if scope == 'event' else 24000.):
            raise RuntimeError('活动/片段能量与手算不符')
        energy.append(reference.value)
    # 固定窗口只由真实边沿触发，2秒处的候选丢弃，6秒末点可以产生point。
    rule = TemporalRule('pulse', 'dataset', 'session', 'start_only', emit_initial=True, window_duration_ns=3_000_000_000)
    pulses = detect_memory_reference(condition, rule, batch_rows=1)
    array_pulses = detect_memory_numpy(condition, rule, batch_rows=3)
    window = WindowSpec('fixed', 'pulse', 'point', post_ns=3_000_000_000)
    fixed = build_segments_reference(pulses, window, domain)
    if pulses != array_pulses or fixed != build_segments_numpy(array_pulses, window, domain) or tuple(event.start_ns for event in pulses) != (0, 6_000_000_000):
        raise RuntimeError('固定边沿窗口与独立后端/手算不符')
    # 小例只输出可解释事实，关联ID实际保存在Event/Segment模型。
    output = {'sample_kind': 'synthetic', 'backends_equal': True,
              'activities_ns': [[event.start_ns, event.end_ns] for event in events],
              'single_requested_ns': [segments[0].requested.start_ns, segments[0].requested.end_ns],
              'single_parent_count': len(segments[0].parent_event_ids), 'energy_j': energy,
              'start_only_points_ns': [event.start_ns for event in pulses],
              'fixed_windows': [{'requested_ns': [segment.requested.start_ns, segment.requested.end_ns],
                                 'actual_ns': None if segment.actual is None else [segment.actual.start_ns, segment.actual.end_ns],
                                 'coverage': segment.requested_coverage, 'status': segment.status} for segment in fixed]}
    print(json.dumps(output, ensure_ascii=False, indent=2))


# 导入时不运行或持有跨任务状态，直接执行才打印合成结果。
if __name__ == '__main__':
    main()
