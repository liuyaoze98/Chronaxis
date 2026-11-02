"""将原电流换算成A，判断是否大于5 A，并展示数据未知时的逻辑结果。

合成输入在0、1、2纳秒分别为5500 mA、None、4500 mA，观测到4纳秒。
原字段raw.current绑定为pack_current，乘0.001转换成A，有效期为2纳秒。
None是收到了一次无效更新，不能继续使用上次5.5 A；因此这三个查询点上
pack_current>5应依次为True、未知、False。未知在输出values中显示为null，
原因保留在quality和dependency_quality，数组的无效占位值不能当正常值。
main还计算False and pack_current>5：结果可判断为False，但依赖诊断保留。
两后端各自转换原值、保持状态并执行受限表达式，打印质量与身份对照JSON。
本例依赖NumPy，只向标准输出打印，无文件或DBC读写。运行先设置PYTHONPATH=src。
"""

# stdout仅展示明示合成输入的事实。
import json
# NumPy明确作为独立批量后端依赖。
import numpy as np
# 已接线标准库编译与参考入口，不用未实现AnalysisRunner。
from chronaxis.core import (MemoryRow, SessionSpec, SignalBindings, SignalDefinition, SignalDType,
                            SourceSpec, TimebaseSpec, TimeType, compile_expression, evaluate_memory_reference)
# 明确数组原行转换/对齐/表达式入口。
from chronaxis.core.expression_numpy import evaluate_memory_numpy


def main() -> None:
    """计算电流阈值及恒定False与未知数据组合的逻辑结果。

    参数: 无；使用文件顶部三个合成原值与2纳秒有效期。
    返回: None；JSON显示True、null、False和保留的质量原因。
    异常: 编译、绑定或数值错误传播；不把未知占位当有效False。
    """
    # 同一明确相对时钟，无真实跨源同步推断。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'expression-demo-v1')
    # None是真实无效更新，不过滤后保持旧5.5A。
    rows = tuple(MemoryRow(index, {'raw.current': value}, index) for index, value in enumerate((5500, None, 4500)))
    # 观测结束4ns明示，样本时间仍原顺序。
    source = SourceSpec('sensor', clock, rows, observation_start_ns=0, observation_end_ns=4)
    # 每次使用完整会话，输入binding不在全局保存。
    session = SessionSpec('demo_session', clock, 0, 4, (source,))
    # 字段/可选semantic/simplealias分开，只应用额外单位换算。
    definition = SignalDefinition('pack_current', 'sensor', 'raw.current', SignalDType.FLOAT64, 'A', 2,
                                  input_unit='mA', scale=.001, semantic_id='battery.current')
    # 当前完整实际绑定进入可执行身份。
    bindings = SignalBindings(session, (definition,))
    # DSL只引用已绑定简单别名，阈值5采用A单位。
    plan = compile_expression('pack_current>5', bindings)
    # 标量独立归一化/保持/求值，保留未知原诊断。
    reference = evaluate_memory_reference(plan, (0, 1, 2))
    # NumPy真实同质列转换、searchsorted、ufunc表达式。
    array = evaluate_memory_numpy(plan, np.array([0, 1, 2], dtype=np.int64))
    # 三值knownFalse可以决定and，原未知原因仍应在诊断。
    decided = evaluate_memory_numpy(compile_expression('False and pack_current>5', bindings), np.array([0, 1, 2], dtype=np.int64))
    # normal值只在valid位置解释，不能把invalid占位当False。
    values = [bool(value) if valid else None for value, valid in zip(array.value.values, array.value.valid)]
    # 完整质量与诊断对照，而非只比较正常数值。
    equal = [item.value.valid for item in reference] == array.value.valid.tolist() and [int(item.value.quality) for item in reference] == array.value.quality.tolist() and [int(item.dependency_quality) for item in reference] == array.dependency_quality.tolist()
    # 所有输出是本样例事实，identity不是发布版本或性能证明。
    result = {'sample_id': 'expression-demo-v1', 'values': values, 'quality': array.value.quality.tolist(),
              'dependencies': list(plan.dependencies), 'binding_identity': bindings.identity, 'expression_identity': plan.identity,
              'backends_equal': equal, 'known_false_and_valid': decided.value.valid.tolist(), 'dependency_quality': decided.dependency_quality.tolist()}
    # 没有文件/旧链写入副作用。
    print(json.dumps(result, ensure_ascii=False, indent=2))


# 直接执行才运行合成数值示例。
if __name__ == '__main__':
    # 编译/求值异常保留供真实诊断。
    main()
