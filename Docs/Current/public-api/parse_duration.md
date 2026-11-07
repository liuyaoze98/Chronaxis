# chronaxis.parse_duration

使用`from chronaxis import parse_duration`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.timebase.conversion.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`parse_duration`](#api-parse_duration)

<a id="api-parse_duration"></a>
## `parse_duration`

解析带单位的非负持续参数，允许显式零长度。

```python
parse_duration(text: str) -> TimeConversion
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。完整数值后缀，如500ms、3s、0ns。|

### 返回说明

TimeConversion: 纳秒持续时间，原带单位文本保留。

### 异常说明

TypeError: 非文本。
    ValueError: 缺单位、非法语法或原数值为负，即使负小值会舍为0。
    TimeOverflowError: 换算/舍入超int64。

返回类型：[TimeConversion](TimeConversion.md#api-TimeConversion)。

源码：[`src/chronaxis/timebase/conversion.py:204`](../../../src/chronaxis/timebase/conversion.py#L204)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
