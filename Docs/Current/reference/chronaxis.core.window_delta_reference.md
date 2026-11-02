# chronaxis.core.window_delta_reference

用独立Python遍历计算完整窗口变化量，作为数组实现的数值参考。

输入是有界ZOH片段和一个查询时刻，输出数值、三值条件和覆盖率。
首尾使用点值，窗内使用实际观测及连续片段；缺口不插值、不延长有效期。
本模块不依赖NumPy，不读文件，不保存跨调用状态或触发锁存。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[Truth](chronaxis.core.types.md#api-Truth)、[WindowDeltaResult](chronaxis.core.window_delta.md#api-WindowDeltaResult)

## 对象导航

|对象|用途|
|---|---|
|[`window_delta_reference`](#api-window_delta_reference)|逐段求完整窗口首尾差和方向单调性。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .types import QualityFlag as Q, SignalDType as D, Truth
from .window_delta import WindowDeltaResult, validate_delta_input
```

</details>

<a id="api-window_delta_reference"></a>
## `window_delta_reference`

逐段求完整窗口首尾差和方向单调性。

```python
window_delta_reference(spec, spans, time_ns, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|WindowDeltaSpec|是|无|位置或关键字。固定长度窗口、增加或减少方向及阈值设置，完整配置见[窗口增量](../rules.md)。|
|`spans`|tuple[DeltaSpan, ...]|是|无|位置或关键字。按时间排列的数值保持片段，窗口必须有完整有效覆盖才能比较两端。|
|`time_ns`|int|是|无|位置或关键字。判断窗口增量的纳秒时刻，窗口向前延伸spec规定的长度。|
|`dtype`|SignalDType|是|无|位置或关键字。原信号声明的数值类型，用来保持整数比较或浮点计算规则。|

### 返回说明

WindowDeltaResult；阈值比较包含等于，UNKNOWN不伪装False。

### 异常说明

输入结构错误；定宽数值溢出以质量结果返回。

源码：[`src/chronaxis/core/window_delta_reference.py:13`](../../../src/chronaxis/core/window_delta_reference.py#L13)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
