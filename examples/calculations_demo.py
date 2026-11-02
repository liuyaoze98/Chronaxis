"""在功率部分缺失的三秒内计算能量，区分部分结果、严格结果和空选择。

合成功率在0秒为4000 W、1秒为6000 W、3秒为0 W，有效期为1秒。
分析范围[0,3)秒：前两秒分别贡献4000 J和6000 J，最后一秒数据过期，
所以可核实能量为10000 J，数值覆盖率为2/3，未知范围为[2,3)秒。
3秒末点不增加积分面积。按上次值保持到有效期边界的方式称为零阶保持。
main对照参考和NumPy结果；partial_policy='strict'要求完整数据，返回null。
另以恒定False为选择条件：没有任何时间被选中且条件完全可判断，积分返回0；
这个0与缺失数据导致的null含义不同。JSON同时打印覆盖率和未知范围。
需NumPy及PYTHONPATH=src；只向标准输出打印，不读写日志，不作性能结论。
"""

# JSON只打印可核实数值/覆盖与null，不写缓存。
import json
# 冻结政策局部变体不改原任务。
from dataclasses import replace
# 当前typed模型、标准库参考完整执行。
from chronaxis.core import (Interval, MemoryRow, CalculationDefinition, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType, SourceSpec, TimebaseSpec, TimeType, compile_expression, compute_memory_reference)
# 数组依赖显式加载，不影响通用core标准库入口。
from chronaxis.core.calculations_memory_numpy import compute_memory_numpy


def main():
    """打印部分能量、严格完整政策结果和已知空选择积分。

    参数: 无；输入功率、1秒有效期及[0,3)秒范围见文件顶部。
    返回: None；打印10000 J的可核实部分、覆盖率、严格null及空选择0。
    异常: 模型、配置、单位或计算错误传播；缺失面积不会补零。
    """
    # 合成时钟原点明确，不推测真实来源同步。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'calculations-demo-v1')
    # 真实最后0W只提供边界，不能追加周期。
    source = SourceSpec('sensor', clock, (MemoryRow(0, {'raw_power': 4000.}, 0), MemoryRow(1_000_000_000, {'raw_power': 6000.}, 1),
                                        MemoryRow(3_000_000_000, {'raw_power': 0.}, 2)), observation_start_ns=0, observation_end_ns=3_000_000_000)
    # 连续域[0,3)，最后一秒因TTL1未知。
    session = SessionSpec('session', clock, 0, 3_000_000_000, (source,))
    # 原值已经W，不能重复factor或乘旧period。
    bindings = SignalBindings(session, (SignalDefinition('power', 'sensor', 'raw_power', SignalDType.FLOAT64, 'W', 1_000_000_000),))
    # 简单别名与明确全FALSE条件，不用eval/车型本体。
    numeric, condition = compile_expression('power', bindings), compile_expression('False', bindings)
    # 请求范围/政策是当前计划声明。
    spec = CalculationDefinition('energy', 'integral', Interval(0, 3_000_000_000))
    # 各链从原行独立执行，未知不自动补0。
    reference, array = compute_memory_reference(numeric, spec), compute_memory_numpy(numeric, spec)
    # 严格请求不返回部分值，事实覆盖仍保存。
    strict = compute_memory_reference(numeric, replace(spec, partial_policy='strict'))
    # 全FALSE充分可判断，即使值局部未知也能证明没有选中集合。
    empty = compute_memory_numpy(numeric, spec, condition=condition)
    # 各字段区分完整、部分、未知与空选择，而非只给总数。
    result = {'input_id': 'calculations-demo-v1', 'backends_equal': reference == array,
              'value': reference.value, 'unit': reference.unit, 'status': reference.status,
              'value_coverage': reference.value_coverage, 'requested_coverage': reference.requested_coverage,
              'value_unknown_ranges_ns': [[interval.start_ns, interval.end_ns] for interval in reference.value_unknown_ranges],
              'strict_value': strict.value, 'empty_selection_value': empty.value, 'empty_selection_reason': empty.reason}
    # JSON null保持unknown/strict与正常0的区别。
    print(json.dumps(result, ensure_ascii=False))


# 导入示例不自动执行，只直接运行时输出。
if __name__ == '__main__':
    # 当前合成输入全部已授权，无外部写入副作用。
    main()
