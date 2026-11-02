# chronaxis.shift_times_reference

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.timebase.conversion.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [shift_times_reference](#api-shift_times_reference)

<a id="api-shift_times_reference"></a>
## `shift_times_reference`

逐项独立计算固定偏移，作为数组内核的整数真值参考。

```python
shift_times_reference(times: Sequence[int], offset_ns: int) -> tuple[int, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|Sequence[int]|是|无|位置或关键字。已声明纳秒坐标，不要求排序。|
|`offset_ns`|int|是|无|位置或关键字。合法int64固定偏移。|

### 返回说明

tuple[int,...]: 新整数序列，空输入返回空tuple。

### 异常说明

TypeError/TimeOverflowError: 参数类型或任一坐标/结果超界。

### 副作用说明

无；不导入或调用NumPy实现，不修改输入。

返回类型：tuple[int, ...]。

源码：[`src/chronaxis/timebase/conversion.py:319`](../../../src/chronaxis/timebase/conversion.py#L319)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
