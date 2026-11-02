# chronaxis.convert_time

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.timebase.conversion.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [convert_time](#api-convert_time)

<a id="api-convert_time"></a>
## `convert_time`

按明确单位换算纳秒，并在最终结果处取最近偶数舍入。

```python
convert_time(value: int | float | str | Decimal, unit: str) -> TimeConversion
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; str &#124; Decimal|是|无|位置或关键字。有限整数、十进制文本、Decimal或已有float，允许负时间坐标。|
|`unit`|str|是|无|位置或关键字。大小写敏感的s、ms、us或ns；没有默认单位。|

### 返回说明

TimeConversion: 整数纳秒、输入表示与单位，以及是否发生纳秒舍入和
    是否受已有浮点精度限制的诊断。

### 异常说明

TypeError或ValueError: 输入类型、文本语法、有效数字长度或单位不合法。
    TimeOverflowError: 舍入后的结果超出int64范围。

### 处理流程说明

分离符号、系数和指数，在整数域缩放或求商余数，再舍入到整纳秒。
    极大正指数提前拒绝；极大负指数直接判定舍为0，避免无界分配。

### 副作用说明

无，不修改输入、Decimal上下文或时间基准。

返回类型：[TimeConversion](TimeConversion.md#api-TimeConversion)。

源码：[`src/chronaxis/timebase/conversion.py:143`](../../../src/chronaxis/timebase/conversion.py#L143)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
