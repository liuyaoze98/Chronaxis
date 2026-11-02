# chronaxis.time_deltas_reference

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.timebase.conversion.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [time_deltas_reference](#api-time_deltas_reference)

<a id="api-time_deltas_reference"></a>
## `time_deltas_reference`

计算非递减整数时间的相邻跨度，允许同时间不同样本。

```python
time_deltas_reference(times: Sequence[int]) -> tuple[int, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|Sequence[int]|是|无|位置或关键字。来源顺序的int64纳秒，允许重复坐标。|

### 返回说明

tuple[int,...]: 长度max(N-1,0)的非负int64跨度。

### 异常说明

TypeError/ValueError: 非整数或来源内时间回退。
    TimeOverflowError: 输入或跨度超界，即使两端各自合法。

本函数直接报告的具体错误：

- `ValueError`：时间序列必须非递减。

### 副作用说明

无；Python整数参考不调用NumPy内核，也不排序或去重。

返回类型：tuple[int, ...]。

源码：[`src/chronaxis/timebase/conversion.py:338`](../../../src/chronaxis/timebase/conversion.py#L338)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
