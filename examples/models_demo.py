"""构造信号与时间范围，展示有效零值、无效观测和末点的不同含义。

输入为合成相对时钟synthetic-run-v1，两行在0、2纳秒处记录raw.value=0；
来源和会话范围从0到2纳秒。main建立数据集、来源引用与信号样本：
有效0保留为0；NaN观测标记为无效，输出诊断而不把NaN写进JSON。
Interval(0,2)连续区间不含2纳秒，点查询point=True可以包含真实末点，
所以continuous_contains_end为False，point_contains_end为True，时长为2纳秒。
本例只检查模型，不执行有效期保持、表达式或统计。只向标准输出打印，
无文件读写；运行先设置PYTHONPATH=src。实际导入是否依赖NumPy须以环境为准，
不能由本例未调用数组计算推断整个包的导入依赖。
"""

# 标准库仅用于输出已有模型事实，避免写不完整schema文件。
import json

# 模型要求明确的输入类型；来源身份和质量原因必须由调用者提供。
from chronaxis.core import (
    DatasetSpec, Interval, MemoryRow, QualityFlag, SessionSpec, SignalDType,
    SignalSample, SourceRef, SourceSpec, TimebaseSpec, TimeType,
)


def main() -> None:
    """检查有效零值与无效样本，并打印连续范围和点范围差别。

    参数: 无；全部数据来自文件顶部的合成模型。
    返回: None；JSON打印零值、质量、2纳秒时长及末点是否包含。
    异常: 模型结构、归属或类型错误传播；不把NaN本体写进JSON。
    """
    # 相对起点明确为示例run，不从机器时区或其他任务推断。
    timebase = TimebaseSpec("demo_clock", TimeType.RELATIVE, "synthetic-run-v1")
    # 原字段文本保留点号，尚未绑定成表达式别名。
    rows = (MemoryRow(0, {"raw.value": 0}, 0), MemoryRow(2, {"raw.value": 0}, 1))
    # 来源原范围明确、偏移0，仍不证明任何实际多源同步。
    source = SourceSpec("sensor", timebase, rows, observation_start_ns=0, observation_end_ns=2)
    # 连续域[0,2)；真实观测在2可用于点上下文。
    session = SessionSpec("demo_session", timebase, 0, 2, (source,))
    # 实体只表示试验对象，不加入领域信号目录。
    dataset = DatasetSpec("demo_dataset", "specimen", session)
    # 完整内存来源引用与表达式别名reading分开。
    reference = SourceRef("demo_session", "sensor", "raw.value")
    # 0是明确有效观测，不因truthiness变成缺失。
    valid = SignalSample("reading", 2, 0, True, QualityFlag.NONE, reference, 1)
    # dtype校验不隐式cast，原值严格是int64可表示整数。
    valid.validate_dtype(SignalDType.INT64)
    # 身份及来源/会话点范围检查通过，尚不运行分析引擎。
    session.validate_sample(valid)
    # 无效NaN保留原因，用正常样本字段描述而不补0。
    invalid = SignalSample("reading", 1, float("nan"), False, QualityFlag.NONFINITE, reference, 0)
    # invalid占位不参与数值域，仍明确采用float64定义。
    invalid.validate_dtype(SignalDType.FLOAT64)
    # 半开区间与点视图以同一端点分别核对。
    domain = Interval(0, 2)
    # JSON只展示诊断事实，禁止非标准NaN序列化或伪造产品结果。
    print(json.dumps({"sample_id": "models-demo-v1", "dataset_id": dataset.dataset_id,
                      "session_id": session.session_id, "origin": timebase.origin,
                      "valid_zero": valid.value, "invalid_quality": int(invalid.quality),
                      "invalid_usable": invalid.valid, "duration_ns": domain.duration_ns(),
                      "continuous_contains_end": domain.contains(2),
                      "point_contains_end": domain.contains(2, point=True)}, ensure_ascii=False, allow_nan=False, indent=2))


# 导入只提供示例函数，直接运行才有标准输出。
if __name__ == "__main__":
    # 此例只演示模型构建，不执行分析任务。
    main()
