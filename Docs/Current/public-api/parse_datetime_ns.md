# chronaxis.parse_datetime_ns

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.timebase.conversion.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [parse_datetime_ns](#api-parse_datetime_ns)

<a id="api-parse_datetime_ns"></a>
## `parse_datetime_ns`

将ISO完整日期转换为UTC整数纳秒，保留亚微秒分数。

```python
parse_datetime_ns(text: str, source_timezone: tzinfo | None=None) -> TimeConversion
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。YYYY-MM-DDTHH:MM:SS[.fraction][Z/±HH:MM]，也允许空格分隔。|
|`source_timezone`|tzinfo &#124; None|否|None|位置或关键字。为没有时区偏移的日期指定时区对象；如from datetime import timezone后传timezone.utc，或timezone(timedelta(hours=8))。必须是tzinfo实例，不能传YAML用的字符串。日期已有偏移时以日期为准；None且日期无偏移会报错。|

### 返回说明

TimeConversion: UTC epoch纳秒、量化与实际采用时区，非机器默认。

### 异常说明

TypeError/ValueError: 文本/时区非法、naive缺时区、本地时刻模糊或不存在。
    TimeOverflowError: int64时间超界。
    OverflowError: 转到UTC时超出datetime历法边界。

### 副作用说明

无；不调用系统本地时区，不加载IANA名称或访问文件。

返回类型：[TimeConversion](TimeConversion.md#api-TimeConversion)。

源码：[`src/chronaxis/timebase/conversion.py:236`](../../../src/chronaxis/timebase/conversion.py#L236)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
