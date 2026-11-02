# chronaxis.checked_add_ns

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.timebase.conversion.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [checked_add_ns](#api-checked_add_ns)

<a id="api-checked_add_ns"></a>
## `checked_add_ns`

为一个纳秒坐标添加固定偏移，并检查结果是否仍在int64范围内。

```python
checked_add_ns(time_ns: int, offset_ns: int) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。已满足int64范围的原时间坐标，单位为纳秒。|
|`offset_ns`|int|是|无|位置或关键字。已满足int64范围的固定偏移，单位为纳秒。|

### 返回说明

int: 精确的新坐标；成功相加不表示不同来源已经同步。

### 异常说明

TypeError: 任一输入不是非布尔整数。
    TimeOverflowError: 任一输入或相加结果超出int64范围。

返回类型：int。

源码：[`src/chronaxis/timebase/conversion.py:301`](../../../src/chronaxis/timebase/conversion.py#L301)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
