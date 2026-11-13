# chronaxis.TimeConversion

使用`from chronaxis import TimeConversion`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.timebase.conversion.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`TimeConversion`](#api-TimeConversion)

<a id="api-TimeConversion"></a>
## `TimeConversion`

保存规范时间及来源精度，避免跨任务修改转换诊断。

time_ns经入口校验为int64；quantized表示实际纳秒舍入发生，浮点限制
与量化分别记录。input_text保留转换所见表示，不证明上游原始精度。
source_timezone仅记录日期采用的时区，不替代多源同步依据。

```python
TimeConversion(time_ns: int, input_representation: str, input_unit: str, input_text: str, quantized: bool, precision_limited: bool = False, rounding: str = 'round_half_even', source_timezone: str | None = None) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|核心坐标或时长，单位纳秒，有符号64位范围。|
|`input_representation`|str|是|无|integer/decimal_text/decimal/binary_float/ISO8601等实际来源。|
|`input_unit`|str|是|无|明确声明的s/ms/us/ns，日期入口使用ISO8601。|
|`input_text`|str|是|无|当前入口所见文本；不记录用户日志或假设更高源精度。|
|`quantized`|bool|是|无|原精确表示不能整纳秒表示时为True，包括舍为0。|
|`precision_limited`|bool|否|False|标记输入是否为已有二进制float：True表示不能恢复转为float之前的精度；1.0也为True，即使quantized=False。整数/十进制文本/Decimal为False；False不表示多个时钟已同步。|
|`rounding`|str|否|'round_half_even'|最终纳秒固定采用最近偶数舍入。|
|`source_timezone`|str &#124; None|否|None|日期实际采用的tzinfo说明，纯数值不猜。|

源码：[`src/chronaxis/timebase/conversion.py:47`](../../../src/chronaxis/timebase/conversion.py#L47)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
