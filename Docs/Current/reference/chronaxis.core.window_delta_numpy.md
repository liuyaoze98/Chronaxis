# `chronaxis.core.window_delta_numpy`

用数组掩码计算窗口覆盖、首尾位置和整窗单调性。

输入和输出与独立参考一致；实际使用searchsorted、区间裁剪、质量掩码和
相邻数组比较，不调用参考核。时间在整数域裁剪后才建立数组，避免下限回绕。
数值保留int64/uint64/float64，不将大整数转换成浮点。无文件和状态副作用。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[Truth](chronaxis.core.types.md#api-Truth)、[WindowDeltaResult](chronaxis.core.window_delta.md#api-WindowDeltaResult)

## 对象导航

|对象|用途|
|---|---|
|[`window_delta_numpy`](#api-window_delta_numpy)|通过真实数组运算计算一个窗口，不复用参考算法的数值函数。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .types import QualityFlag as Q, SignalDType as D, Truth
from .window_delta import WindowDeltaResult, validate_delta_input
```

</details>

<a id="api-window_delta_numpy"></a>
## `window_delta_numpy`

通过真实数组运算计算一个窗口，不复用参考算法的数值函数。

```python
window_delta_numpy(spec, spans, time_ns, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|WindowDeltaSpec|是|无|位置或关键字。固定长度窗口、增加或减少方向及阈值设置，完整配置见[窗口增量](../rules.md)。|
|`spans`|tuple[DeltaSpan, ...]|是|无|位置或关键字。按时间排列的数值保持片段，窗口必须有完整有效覆盖才能比较两端。|
|`time_ns`|int|是|无|位置或关键字。判断窗口增量的纳秒时刻，窗口向前延伸spec规定的长度。|
|`dtype`|SignalDType|是|无|位置或关键字。原信号声明的数值类型，用来保持整数比较或浮点计算规则。|

### 返回说明

WindowDeltaResult。

### 异常说明

输入错误；数值失败记录质量。

源码：[`src/chronaxis/core/window_delta_numpy.py:13`](../../../src/chronaxis/core/window_delta_numpy.py#L13)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
