"""演示整数加法溢出和电流单位换算，同时保留无效值的原因。

两组INT64加法输入分别是最大值2**63-1加1、0加1。第一组应标记溢出并
输出null，第二组输出1，不能让整数回绕成负数。合成电流在0纳秒为500 mA，
1纳秒为None；有效期为1纳秒，来源观测到2纳秒。显式乘0.001得到0.5 A，
None仍是无效原观测。main打印两后端的质量、有效性及换算结果是否一致。
NumPy数组中的无效占位0不能当正常0。输出device_label保留原有固定样例值
work，它不证明本次运行设备；实际执行来源另记在验证记录中。
本例依赖NumPy，只向标准输出打印，不读写日志；运行先设置PYTHONPATH=src。
"""

# JSON展示合成结果；输出中固定work标签沿用原样例，本次运行设备另记验证记录。
import json
# NumPy显式加载，承担真实typed列/ufunc与掩码计算。
import numpy as np

# 已实现的标准库入口与显式数组入口。
from chronaxis.core import (MemoryRow, ScalarValue, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType as D, SourceSpec, TimebaseSpec, TimeType, binary_reference, memory_series_reference)
# 使用已接线的chronaxis.core.numeric_numpy入口；不采用mock或未实现占位。
from chronaxis.core.numeric_numpy import NumericArray, binary_numpy
# 使用已接线的chronaxis.core.normalize_numpy入口；不采用mock或未实现占位。
from chronaxis.core.normalize_numpy import memory_series_numpy


def main() -> None:
    """执行两组整数加法和电流换算，核对质量与来源保留。

    参数: 无；输入为整数端点和500 mA、None两行合成数据。
    返回: None；JSON打印溢出标记、正常1及0.5 A换算结果。
    异常: 模型或计算错误传播；无效数组值按valid掩码输出为null。
    """
    # 两个正常输入分别发生上溢和正常0+1。
    left = np.array([2 ** 63 - 1, 0], dtype=np.int64)
    # 同dtype右列，禁止隐式promotion。
    right = np.array([1, 1], dtype=np.int64)
    # 标量独立精确运算。
    reference = [binary_reference('add', ScalarValue(int(a), D.INT64), ScalarValue(int(b), D.INT64)) for a, b in zip(left, right)]
    # 数组实际运行安全定宽检查及where ufuc，invalid占位0不正常使用。
    array = binary_numpy('add', NumericArray(D.INT64, left, np.ones(2, dtype=bool), np.zeros(2, dtype=np.uint16)),
                         NumericArray(D.INT64, right, np.ones(2, dtype=bool), np.zeros(2, dtype=np.uint16)))
    # 合成基准不是物理时间同步声明。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'numeric-demo-v1')
    # 原None保持缺失，不补正常0。
    source = SourceSpec('sensor', clock, (MemoryRow(0, {'raw': 500}, 0), MemoryRow(1, {'raw': None}, 1)), observation_start_ns=0, observation_end_ns=2)
    # 单一memory会话，没有跨源同步要求。
    session = SessionSpec('demo_session', clock, 0, 2, (source,))
    # 明示额外mA→A换算，不加载DBC。
    definition = SignalDefinition('current', 'sensor', 'raw', D.FLOAT64, 'A', 1, input_unit='mA', scale=.001)
    # 真实绑定隔离输入与策略。
    bindings = SignalBindings(session, (definition,))
    # 两种适配各自独立计算，原身份保留。
    normalized_ref, normalized_array = memory_series_reference(bindings, 'current'), memory_series_numpy(bindings, 'current')
    # 正常逻辑值解释必须带valid，invalid输出null。
    result = {'sample_id': 'numeric-demo-v1', 'device_label': 'work', 'valid': array.valid.tolist(), 'quality': array.quality.tolist(),
              'values': [array.values[index].item() if valid else None for index, valid in enumerate(array.valid)],
              'backends_equal': [int(item.quality) for item in reference] == array.quality.tolist(),
              'normalized_current_A': normalized_ref.samples[0].value, 'invalid_original': normalized_array.samples[1].value,
              'adapters_equal': normalized_ref.samples == normalized_array.samples}
    # stdout之外无文件/缓存副作用。
    print(json.dumps(result, ensure_ascii=False, indent=2))


# 只有直接运行示例才触发计算。
if __name__ == '__main__':
    # 当前入口已真实接线，配置异常不忽略。
    main()
