"""用两套合成字段/单位/方向映射演示充电与报警v1的同一公共组合。

范围[0,6)s：电流10A在[0,2)、20A在[3,5)，400V，模式编码1。
持续1s的两活动分别8000J/16000J、20As/40As，预设按Wh/Ah输出。
合成alarm的TRUE仅表示本例演示谓词成立；rising在1/4/6s，末点窗口部分观测。
第一套原值V/A，第二套mV/mA且原电流正向放电，明确反转后正向充电。
两个预设只构建声明，随后直接组合既有独立参考/NumPy公共算子；不是完整AnalysisRunner。
输入/中间/输出完整内存，打印JSON，无旧链/日志读取、文件写出或真实故障结论。
"""

# 演示输出只包含合成结果与定位身份，禁止打印私有真实日志。
import json
from chronaxis import PresetSpec, build_preset
from chronaxis.core import (Interval, MemoryRow, CalculationDefinition, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType as D, SourceSpec, TemporalRule, TimebaseSpec, TimeType,
                            compile_expression, compute_memory_reference, detect_memory_reference, build_segments_reference)
from chronaxis.core.calculations_memory_numpy import compute_memory_numpy
from chronaxis.core.temporal_memory_numpy import detect_memory_numpy
from chronaxis.core.windows_numpy import build_segments_numpy


def build_bindings(converted=False):
    """建立两套物理含义等价的已解码合成输入与完整转换声明。

    参数: converted为bool，True使用mV/mA、不同别名/字段/来源及显式电流反转。
    返回: SignalBindings，不登记派生；构建预设后由调用者加入生成名称。
    异常: 模型/单位/方向声明错误直接传播，不猜原值或采样周期。
    """
    # 相同合成公共起点，不是实际设备同步证明。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'preset-demo-v1')
    source_name = 'mapped_sensor' if converted else 'sensor'
    aliases = ('operating', 'charge_current', 'pack_voltage', 'warning') if converted else ('mode', 'current', 'voltage', 'alarm')
    fields = ('code', 'milli_current', 'milli_voltage', 'warning_bit') if converted else ('raw_mode', 'raw_current', 'raw_voltage', 'raw_alarm')
    # 原生时间保留ns；6s的真实alarm更新可产生点但不增加面积。
    data = ((0, 10., False), (1, 10., True), (2, 0., False), (3, 20., False),
            (4, 20., True), (5, 0., False), (6, 0., True))
    rows = tuple(MemoryRow(time*1_000_000_000, {fields[0]: 1,
                 fields[1]: current*(-1000 if converted else 1), fields[2]: 400_000. if converted else 400.,
                 fields[3]: alarm}, index) for index, (time, current, alarm) in enumerate(data))
    source = SourceSpec(source_name, clock, rows, observation_start_ns=0, observation_end_ns=6_000_000_000)
    session = SessionSpec('session', clock, 0, 6_000_000_000, (source,))
    # 所有方向/转换证据明确保留，scale只在归一化应用一次。
    signals = (SignalDefinition(aliases[0], source_name, fields[0], D.INT64, '1', 10_000_000_000),
               SignalDefinition(aliases[1], source_name, fields[1], D.FLOAT64, 'A', 10_000_000_000,
                    input_unit='mA' if converted else 'A', scale=-.001 if converted else 1,
                    direction_factor=-1 if converted else 1, input_sign_convention='positive_is_discharge' if converted else None,
                    sign_convention='positive_is_charge', measurement_location='pack_terminal', mapping_version='map-b' if converted else 'map-a'),
               SignalDefinition(aliases[2], source_name, fields[2], D.FLOAT64, 'V', 10_000_000_000,
                    input_unit='mV' if converted else 'V', scale=.001 if converted else 1, measurement_location='pack_terminal'),
               SignalDefinition(aliases[3], source_name, fields[3], D.BOOL, '1', 10_000_000_000))
    return SignalBindings(session, signals)


def run_example(converted=False, backend='reference', batch_rows=1):
    """将同一预设规则直接组合公共检测/窗口/积分入口，保存原活动和来源。

    参数: converted选择映射；backend严格reference/numpy；batch_rows为检测批大小。
    返回: (bindings, charge_fragment, activities, calculation_rows, alarm_events, segments)。
    异常: 预设/公共模型/表达式/数值异常传播；未知后端ValueError，不静默回退。
    """
    if backend not in ('reference', 'numpy'):
        raise ValueError('backend须为reference/numpy')
    bindings = build_bindings(converted)
    mode, current, voltage, alarm = bindings.signals
    # 只提供本例工程值，预设不内置阈值或决定实际设备合格。
    charge = build_preset(PresetSpec('charge', 'charge_session', '1',
             {'mode': mode.name, 'current': current.name, 'voltage': voltage.name},
             {'mode_value': 1, 'current_min': 5, 'minimum_duration': '1s', 'compute_energy': True,
              'compute_charge': True, 'minimum_coverage': .95}), bindings.signals)
    fault = build_preset(PresetSpec('fault', 'fault_context', '1', {'alarm': alarm.name},
                                   {'pre': '1s', 'post': '2s'}), bindings.signals)
    bindings = SignalBindings(bindings.session, bindings.signals, tuple(item.name for item in charge.derived))
    detector = detect_memory_reference if backend == 'reference' else detect_memory_numpy
    compute = compute_memory_reference if backend == 'reference' else compute_memory_numpy
    windows = build_segments_reference if backend == 'reference' else build_segments_numpy
    # 原活动从onset积分，持续确认不裁掉起始1s。
    declaration = charge.rules[0]
    condition = compile_expression(declaration.condition, bindings, derived=charge.derived)
    activities = detector(condition, TemporalRule(declaration.id, 'demo', 'session', 'condition_duration', declaration.minimum_duration_ns), batch_rows=batch_rows)
    calculations = []
    for event in activities:
        for declaration in charge.calculations:
            compiled = compile_expression(declaration.signal, bindings, derived=charge.derived)
            spec = CalculationDefinition(declaration.id, 'integral', Interval(event.start_ns, event.end_ns),
                              output_unit=declaration.unit, scope='event', partial_policy=declaration.partial_policy or 'report',
                              minimum_coverage=declaration.minimum_coverage)
            calculations.append(compute(compiled, spec))
    # 报警条件本身是明确BOOL，不需要无关电池契约。
    declaration = fault.rules[0]
    alarm_condition = compile_expression(declaration.condition, bindings, derived=charge.derived)
    alarm_events = detector(alarm_condition, TemporalRule(declaration.id, 'demo', 'session', 'rising_edge',
                            emit_initial=declaration.emit_initial), batch_rows=batch_rows)
    segments = windows(alarm_events, fault.windows[0], Interval(0, 6_000_000_000))
    return bindings, charge, activities, tuple(calculations), alarm_events, segments


def main():
    """运行两映射/两后端并检查手算事实，输出可读合成摘要。

    参数: 无。
    返回: None，向stdout打印JSON；不创建文件或发布分析结果。
    异常: 后端不一致或手算错误AssertionError，原公共入口错误传播。
    """
    expected = (8000/3600, 20/3600, 16000/3600, 40/3600)
    outputs = []
    for converted in (False, True):
        reference = run_example(converted, 'reference', 1)
        numpy = run_example(converted, 'numpy', 3)
        # 相同映射比较完整事件/指标/片段与元数据，两个后端没有共享数值内核。
        assert reference[2:] == numpy[2:]
        assert tuple((event.start_ns, event.end_ns) for event in reference[2]) == ((0, 2_000_000_000), (3_000_000_000, 5_000_000_000))
        assert all(abs(row.value-value) < 1e-12 for row, value in zip(reference[3], expected))
        assert tuple(event.start_ns for event in reference[4]) == (1_000_000_000, 4_000_000_000, 6_000_000_000)
        assert abs(reference[5][-1].requested_coverage-1/3) < 1e-15
        outputs.append({'mapping': 'converted' if converted else 'native', 'binding_identity': reference[0].identity,
                        'calculations': [{'name': row.spec.calculation_id, 'value': row.value, 'unit': row.unit,
                                     'coverage_status': row.coverage_status} for row in reference[3]],
                        'alarm_points_ns': [event.start_ns for event in reference[4]],
                        'context': [{'requested': [row.requested.start_ns, row.requested.end_ns],
                                     'actual': [row.actual.start_ns, row.actual.end_ns],
                                     'coverage': row.requested_coverage} for row in reference[5]]})
    assert outputs[0]['binding_identity'] != outputs[1]['binding_identity']
    print(json.dumps({'device_label': 'work', 'synthetic': True, 'results': outputs}, ensure_ascii=False, indent=2))


# 只有直接运行才执行合成验收；导入供测试复用不读写文件。
if __name__ == '__main__':
    main()
