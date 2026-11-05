# `chronaxis.core.window_delta`

定义最近一段完整时间内的首尾变化量、方向和单调限制；变化量单位仍是信号单位，不是每秒变化率。详见[window_delta](../rules.md)。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`WindowDeltaSpec`](#api-WindowDeltaSpec)|保存窗口长度、方向、阈值及单调要求；只接受完整覆盖政策。|
|[`WindowDeltaSpec.__post_init__`](#api-WindowDeltaSpec-__post_init__)|检查明确参数，不从名字猜时长或单位。|
|[`DeltaSpan`](#api-DeltaSpan)|保存一段常值和起点点值；零长度仅用于真实末点。|
|[`DeltaSpan.__post_init__`](#api-DeltaSpan-__post_init__)|规范纳秒和点质量，并检查有值证据。|
|[`WindowDeltaResult`](#api-WindowDeltaResult)|保存一次窗口结果；value与方向一致，condition额外考虑单调要求。|
|[`validate_delta_input`](#api-validate_delta_input)|检查两个数值核共用的结构及dtype，不计算变化量或单调性。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from .types import QualityFlag as Q, SignalDType as D, Truth
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-WindowDeltaSpec"></a>
## `WindowDeltaSpec`

保存窗口长度、方向、阈值及单调要求；只接受完整覆盖政策。

```python
class WindowDeltaSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`window_ns`|int|是|无|完整回看长度，必须为正。|
|`threshold`|int &#124; float|是|无|非负门槛，单位与输入相同，包含等于门槛。|
|`direction`|str|否|'any'|rise末减首，fall首减末，any取绝对差。|
|`monotonic`|bool|否|False|rise非降、fall非升、any二者任一。|
|`coverage_policy`|str|否|'full'|样本兼容口径不在本核心隐式启用。|

源码：[`src/chronaxis/core/window_delta.py:16`](../../../src/chronaxis/core/window_delta.py#L16)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowDeltaSpec-__post_init__"></a>
### `WindowDeltaSpec.__post_init__`

检查明确参数，不从名字猜时长或单位。

```python
WindowDeltaSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、非有限或范围错误。

本函数直接报告的具体错误：

- `ValueError`：window_delta窗口须为正，方向须为rise/fall/any。
- `TypeError`：monotonic需bool，threshold需数值且不能为bool。
- `ValueError`：threshold须为非负有限数值。
- `ValueError`：当前window_delta仅支持full覆盖政策。

源码：[`src/chronaxis/core/window_delta.py:25`](../../../src/chronaxis/core/window_delta.py#L25)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DeltaSpan"></a>
## `DeltaSpan`

保存一段常值和起点点值；零长度仅用于真实末点。

quality适用于[start_ns,end_ns)，point_quality适用于start_ns。
值为None时两种质量都须说明无效原因。时间到期不能通过延长end_ns补齐。

```python
class DeltaSpan
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_ns`|int|是|无|当前更新或有效性边界。|
|`end_ns`|int|是|无|连续值排除的右端。|
|`value`|int &#124; float &#124; None|是|无|规范后的原生数值，未知可为None。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|否|Q.NONE|连续区间无效原因。|
|`point_quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag) &#124; None|否|None|默认与连续质量相同。|
|`partial`|bool|否|False|本段连续取值是否依赖覆盖不全的变换结果。|
|`point_partial`|bool|否|False|此段起点单独采用的点值是否只具有部分覆盖，与段内连续值分别记录。|

源码：[`src/chronaxis/core/window_delta.py:42`](../../../src/chronaxis/core/window_delta.py#L42)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-DeltaSpan-__post_init__"></a>
### `DeltaSpan.__post_init__`

规范纳秒和点质量，并检查有值证据。

```python
DeltaSpan.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、倒序或未知无原因。

本函数直接报告的具体错误：

- `ValueError`：DeltaSpan终点不得早于起点。
- `TypeError`：DeltaSpan质量需QualityFlag。
- `TypeError`：DeltaSpan点质量需QualityFlag。
- `ValueError`：没有数值必须注明未知原因。
- `TypeError`：DeltaSpan值需原生int/float或None。

源码：[`src/chronaxis/core/window_delta.py:57`](../../../src/chronaxis/core/window_delta.py#L57)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-WindowDeltaResult"></a>
## `WindowDeltaResult`

保存一次窗口结果；value与方向一致，condition额外考虑单调要求。

valid_duration_ns只计完整窗口内已知连续时间；端点无效也会令条件UNKNOWN，
即使连续覆盖率恰好为1。monotonic是对应方向的实测结果，未知时为None。

```python
class WindowDeltaResult
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|当前判断时刻。|
|`window_start_ns`|int|是|无|精确Python整数，不因回看低于int64下限回绕。|
|`value`|int &#124; float &#124; None|是|无|定宽差值或None，绝不以0替代未知。|
|`condition`|[Truth](chronaxis.core.types.md#api-Truth)|是|无|TRUE/FALSE/UNKNOWN。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|UNKNOWN原因；已知为NONE。|
|`valid_duration_ns`|int|是|无|已知连续时间长度。|
|`coverage`|float|是|无|已知时间/完整窗口时长。|
|`monotonic`|bool &#124; None|是|无|对应方向是否单调。|

源码：[`src/chronaxis/core/window_delta.py:80`](../../../src/chronaxis/core/window_delta.py#L80)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-validate_delta_input"></a>
## `validate_delta_input`

检查两个数值核共用的结构及dtype，不计算变化量或单调性。

```python
validate_delta_input(spec, spans, time_ns, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[WindowDeltaSpec](chronaxis.core.window_delta.md#api-WindowDeltaSpec)|是|无|位置或关键字。固定长度窗口、增加或减少方向及阈值设置，完整配置见[窗口增量](../rules.md)。|
|`spans`|tuple[[DeltaSpan](chronaxis.core.window_delta.md#api-DeltaSpan), ...]|是|无|位置或关键字。按时间排列的数值保持片段，窗口必须有完整有效覆盖才能比较两端。|
|`time_ns`|int|是|无|位置或关键字。判断窗口增量的纳秒时刻，窗口向前延伸spec规定的长度。|
|`dtype`|SignalDType|是|无|位置或关键字。原信号声明的数值类型，用来保持整数比较或浮点计算规则。|

### 返回说明

规范int判断时间。

### 异常说明

类型、重叠、非法值或dtype范围错误。

本函数直接报告的具体错误：

- `TypeError`：窗口需要WindowDeltaSpec及DeltaSpan tuple。
- `TypeError`：window_delta只支持数值信号。
- `TypeError`：窗口输入需DeltaSpan。
- `ValueError`：窗口片段必须严格有序且不重叠。
- `ValueError`：有效float64输入须为有限原生float。
- `TypeError`：有效整数信号不能隐式转浮点。
- `ValueError`：有效数值超出声明dtype。

源码：[`src/chronaxis/core/window_delta.py:97`](../../../src/chronaxis/core/window_delta.py#L97)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
