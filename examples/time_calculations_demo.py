"""用2W与8W的合成信号展示时间统计、TRUE时长及选择行诊断。

输入为0秒2W、1秒8W、4秒0W，信号有效期五秒，观测范围[0,4)秒。
功率时间均值=(2*1+8*3)/4=6.5W，样本均值=(2+8)/2=5W；BOOL报警
仅首秒TRUE，因此duration=1秒。选择条件首秒TRUE，1秒实际更新为未知，
行流保留0秒TRUE行与1秒UNKNOWN诊断行，4秒末点不输出。
流程分别编译当前绑定、通过两个独立内存桥接计算、比较完整结果并打印JSON。
运行：PYTHONPATH=src时执行python -B examples/time_calculations_demo.py。
依赖NumPy；不读写文件或调用旧解码，不证明AnalysisRunner预算、性能或真实日志验收。
"""

# JSON只写标准输出，未发布任何文件。
import json
# 输入typed模型及独立标准库入口。
from chronaxis.core import (Interval, MemoryRow, CalculationDefinition, SessionSpec, SignalBindings,
                            SignalDefinition, SignalDType as D, SourceSpec, TimebaseSpec, TimeType,
                            compile_expression, compute_memory_reference, select_memory_reference)
# 独立NumPy完整原行链，不能用参考结果作输入。
from chronaxis.core.calculations_memory_numpy import compute_memory_numpy, select_memory_numpy


def main():
    """运行合成小样本，核对手算与两后端，再输出可读结果。

    参数: 无。
    返回: None；JSON写到标准输出。
    异常: 模型错误传播；两后端或手算不一致时抛RuntimeError。
    """
    # 原字段和实际时间明确，末点不增加时长或样本。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'time-calculations-demo-v1')
    data = ((0, {'power': 2., 'alarm': True, 'keep': True}),
            (1_000_000_000, {'power': 8., 'alarm': False, 'keep': None}),
            (4_000_000_000, {'power': 0., 'alarm': False, 'keep': False}))
    source = SourceSpec('table', clock, tuple(MemoryRow(time, value, index) for index, (time, value) in enumerate(data)),
                        observation_start_ns=0, observation_end_ns=4_000_000_000)
    # 有效期只作为合成设定，不推荐实际工程阈值。
    bindings = SignalBindings(SessionSpec('session', clock, 0, 4_000_000_000, (source,)),
                              (SignalDefinition('power', 'table', 'power', D.FLOAT64, 'W', 5_000_000_000),
                               SignalDefinition('alarm', 'table', 'alarm', D.BOOL, '1', 5_000_000_000),
                               SignalDefinition('keep', 'table', 'keep', D.BOOL, '1', 5_000_000_000)))
    # 所有计划在本次真实绑定编译，不继承上次值。
    power = compile_expression('power', bindings)
    alarm = compile_expression('alarm', bindings)
    condition = compile_expression('keep', bindings)
    window = Interval(0, 4_000_000_000)
    output = {}
    # 数值归约都调用独立内存链，完整结果与明示手算一起核对。
    for operation, root, expected in (('time_weighted_mean', power, 6.5), ('sample_mean', power, 5.),
                               ('min_time', power, 2.), ('max_time', power, 8.), ('duration', alarm, 1.)):
        spec = CalculationDefinition(operation, operation, window, minimum_coverage=.9)
        reference = compute_memory_reference(root, spec)
        array = compute_memory_numpy(root, spec)
        if reference != array or reference.value != expected:
            raise RuntimeError('时间指标与独立后端或手算不符')
        output[operation] = {'value': reference.value, 'unit': reference.unit, 'coverage_status': reference.coverage_status}
    # 小示例为了展示JSON消费行流；生产输出不需要物化所有行。
    spec = CalculationDefinition('rows', 'select', window)
    reference = tuple(select_memory_reference(power, spec, condition=condition))
    array = tuple(select_memory_numpy(power, spec, condition=condition))
    if reference != array:
        raise RuntimeError('选择行流独立后端不一致')
    output['rows'] = [{'time_ns': row.time_ns, 'value': row.value.value, 'valid': row.value.valid,
                       'unit': row.unit, 'selection': row.selection.value, 'quality': int(row.quality)} for row in reference]
    # 来源是明示合成输入；输出身份保留在实际行模型，不冒充真实日志验证。
    output['sample_kind'] = 'synthetic'
    output['backends_equal'] = True
    print(json.dumps(output, ensure_ascii=False, indent=2))


# 导入示例时不运行，直接执行才产生标准输出。
if __name__ == '__main__':
    main()
