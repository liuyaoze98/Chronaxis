"""展示有效值、无效更新和有效期到期之后，各查询时刻能使用什么值。

合成原行在0纳秒为有效0，1纳秒为无效None，4纳秒为有效2；有效期为2纳秒，
来源观测到6纳秒。1纳秒无效更新会覆盖旧0，不能忽略这行后继续保持0。
共同时间轴保留原更新时间，并增加2、3、6纳秒的有效期边界；点查询仍检查
来源范围和过期条件。参考实现逐点查询，NumPy以时间索引和掩码查询。
main输出time_ns、valid、quality和actual_update，并核对两实现的有效性
与质量。无效数组位置只是存储占位，原诊断None保留在invalid_original。
需NumPy及PYTHONPATH=src；只向标准输出打印，不读取日志或调用旧解码链。
"""

# JSON只展示本合成小样本事实，不宣称产品manifest/schema。
import json

# 数组入口明确加载NumPy，不污染标准库core导入。
import numpy as np

# 使用已经接线的模型/状态模块，不用未实现的AnalysisPlan占位。
from chronaxis.core import (MemoryRow, QualityFlag, SessionSpec, SignalBindings, SignalDefinition,
                            SignalDType, SignalSample, SignalSeries, SourceSpec, TimebaseSpec, TimeType,
                            align_reference, common_timeline)
from chronaxis.core.state_numpy import align_numpy, build_signal_array


def main() -> None:
    """在共同时间轴查询两种保持实现，核对有效性与质量。

    参数: 无；0、1、4纳秒原行和2纳秒有效期见文件顶部。
    返回: None；打印查询轴、状态掩码、更新时间标记及原无效None。
    异常: 模型或对齐错误传播；数组中的无效占位不解释为正常值。
    """
    # 合成起点与真实设备无关，不自动校准时间。
    clock = TimebaseSpec("clock", TimeType.RELATIVE, "synthetic-state-v1")
    # 原行保留无效None，不能用0补齐。
    rows = (MemoryRow(0, {"raw.value": 0}, 0), MemoryRow(1, {"raw.value": None}, 1),
            MemoryRow(4, {"raw.value": 2}, 2))
    # 来源观测结束6ns明确，否则按真实末行4ns收尾。
    source = SourceSpec("sensor", clock, rows, observation_start_ns=0, observation_end_ns=6)
    # 一个会话/别名，无全局状态。
    session = SessionSpec("demo_session", clock, 0, 6, (source,))
    # STATE接已经规范化的int64值，不在这里施加单位转换。
    definition = SignalDefinition("value", "sensor", "raw.value", SignalDType.INT64, "1", 2)
    # 冻结当前输入引用/策略与来源身份。
    binding = SignalBindings(session, (definition,))
    # 原行0/2正常，行1明示decode error。
    samples = tuple(SignalSample("value", row.time_ns, row.values["raw.value"], row.sequence != 1,
                                 QualityFlag.DECODE_ERROR if row.sequence == 1 else QualityFlag.NONE,
                                 binding.source_ref("value"), row.sequence) for row in rows)
    # 规范序列检查原时间、字段、dtype和原序号。
    series = SignalSeries(binding, "value", samples)
    # 无新样本也生成2/3/6ns TTL边界，保留实际末点。
    axis = common_timeline((series,))
    # 参考用Python整数逐点查询，不调用数组内核。
    reference = align_reference(series, axis, point=True)
    # 实际NumPy用searchsorted和掩码执行相同输入。
    array = align_numpy(build_signal_array(series), np.array(axis, dtype=np.int64), point=True)
    # 对照值只在valid位置可用，完整quality也核对。
    same = [item.valid for item in reference] == array.valid.tolist() and [int(item.quality) for item in reference] == array.quality.tolist()
    # 输出原无效值保留、逐边界状态及实际后端一致性。
    result = {"sample_id": "state-demo-v1", "time_ns": list(axis),
              "valid": array.valid.tolist(), "quality": array.quality.tolist(),
              "actual_update": array.actual_update.tolist(), "backends_equal": same,
              "invalid_original": series.samples[1].value, "values_dtype": str(array.values.dtype)}
    # stdout之外无写入、缓存或文件副作用。
    print(json.dumps(result, ensure_ascii=False, indent=2))


# 仅直接运行示例才构造并查询状态。
if __name__ == "__main__":
    # 保持可执行最小实际入口。
    main()
