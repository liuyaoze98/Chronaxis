# chronaxis.timebase

集中导出时间转换和标准库整数时间运算。

输入为明确单位的数值、ISO日期文本或整数纳秒序列；输出转换诊断或新的整数
序列。此文件只重导出conversion的接口，不执行计算、不读取文件、不加载NumPy。
实际入口检查int64范围、明确时区和最终纳秒舍入；不会推断输入时间单位或
机器时区。恰好半纳秒时采用最近偶数舍入，避免统一向同一方向进位。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[TimeConversion](chronaxis.timebase.conversion.md#api-TimeConversion)、[TimeOverflowError](chronaxis.timebase.conversion.md#api-TimeOverflowError)

## 对象导航

|对象|用途|
|---|---|

## 导出名称

`TimeConversion`, `TimeOverflowError`, `checked_add_ns`, `convert_time`, `parse_datetime_ns`, `parse_duration`, `shift_times_reference`, `time_deltas_reference`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from .conversion import TimeConversion, TimeOverflowError, checked_add_ns, convert_time, parse_datetime_ns, parse_duration, shift_times_reference, time_deltas_reference
```

</details>
