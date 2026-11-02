"""集中导出时间转换和标准库整数时间运算。

输入为明确单位的数值、ISO日期文本或整数纳秒序列；输出转换诊断或新的整数
序列。此文件只重导出conversion的接口，不执行计算、不读取文件、不加载NumPy。
实际入口检查int64范围、明确时区和最终纳秒舍入；不会推断输入时间单位或
机器时区。恰好半纳秒时采用最近偶数舍入，避免统一向同一方向进位。
"""

# 标量与独立整数参考内核可在未安装NumPy/CAN时导入。
from .conversion import (
    TimeConversion, TimeOverflowError, checked_add_ns, convert_time,
    parse_datetime_ns, parse_duration, shift_times_reference, time_deltas_reference,
)

# 数组实现独立放numpy_ops，由调用者显式选择。
__all__ = [
    "TimeConversion", "TimeOverflowError", "checked_add_ns", "convert_time",
    "parse_datetime_ns", "parse_duration", "shift_times_reference", "time_deltas_reference",
]
