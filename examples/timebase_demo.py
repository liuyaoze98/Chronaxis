"""把时间文本转换为整数纳秒，并检查大时间坐标上仍能保留1纳秒差值。

合成输入0.123456789秒应转换为123456789纳秒；带+08:00偏移的
1970-01-01T08:00:00表示UTC纪元起点。1.5ns按最近偶数舍入为2纳秒，
量化原因保留在转换诊断。另使用2**53附近四个整数纳秒坐标，其中两个相同，
相邻差值应为[1,0,1]；先转成浮点可能丢失这样的1纳秒差值。
main比较独立Python整数计算和NumPy计算，不一致时抛AssertionError，
成功时打印转换诊断与时间差JSON。需NumPy及PYTHONPATH=src；
只向标准输出打印，不读写文件，也不使用机器默认时区。
"""

# 标准库只负责将冻结诊断转换为可检查JSON。
import json
from dataclasses import asdict

# 数组后端显式选择，不把它隐式加载到标准库入口。
import numpy as np
from chronaxis import convert_time, parse_datetime_ns, parse_duration, time_deltas_reference
from chronaxis.timebase.numpy_ops import time_deltas_numpy


def main() -> None:
    """执行合成示例并输出实际诊断和两个独立结果。

    参数: 无；输入在示例中明确声明，不读取配置或机器时区。
    返回: None；JSON写标准输出，不保存文件。
    异常: AssertionError在后端不一致时失败；转换/数组错误直接传播。
    副作用: 仅标准输出和局部数组分配；不改变输入或全局后端状态。
    """
    # T01文本不经过浮点，有完整9位秒分数。
    conversion = convert_time("0.123456789", "s")
    # 显式+8偏移表示epoch，绝不使用本机时区。
    date = parse_datetime_ns("1970-01-01T08:00:00+08:00")
    # 半纳秒固定最近偶数舍入为2ns，量化诊断保留。
    duration = parse_duration("1.5ns")
    # 覆盖大坐标1ns间隔及合法同时间0差，形状为(N,)、int64。
    times = np.array([2 ** 53 - 1, 2 ** 53, 2 ** 53, 2 ** 53 + 1], dtype=np.int64)
    # 参考路径逐项Python整数，与数组路径算法独立。
    reference = time_deltas_reference(times)
    # NumPy在减法前以比较/掩码证明不会wrap。
    numpy_result = time_deltas_numpy(times)
    # 手算与两后端都需一致才能输出成功示例。
    if reference != (1, 0, 1) or numpy_result.tolist() != [1, 0, 1]:
        # 示例不吞异常或输出错误结果为正常示范。
        raise AssertionError("合成时间差与手算结果不一致")
    # 纳秒结果、输入身份和转换诊断一并输出，未声称真实分析完成。
    print(json.dumps({"sample_id": "timebase-demo-v1", "conversion": asdict(conversion),
                      "date": asdict(date), "duration": asdict(duration),
                      "times_ns": times.tolist(), "reference_delta_ns": reference,
                      "numpy_delta_ns": numpy_result.tolist()}, ensure_ascii=False, indent=2))


# 直接运行才输出示例，导入不会产生I/O。
if __name__ == "__main__":
    # 进入有实际验证的示例入口，没有未实现产品API。
    main()
