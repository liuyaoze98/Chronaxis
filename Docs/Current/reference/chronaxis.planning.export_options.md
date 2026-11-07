# `chronaxis.planning.export_options`

把JSON中的signal_csv/can_frames选项转换成输出规格，检查信号、来源和窗口引用；只检查配置，不读日志或DBC。全部填写方式见[导出](../exports.md)。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[FrameExportSpec](chronaxis.results.frame_exports.md#api-FrameExportSpec)、[FrameGridSpec](chronaxis.results.frame_rebuild.md#api-FrameGridSpec)、[FrameRebuildRule](chronaxis.results.frame_patch.md#api-FrameRebuildRule)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[SignalCSVExportSpec](chronaxis.results.signal_exports.md#api-SignalCSVExportSpec)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalGridSpec](chronaxis.results.signal_grid.md#api-SignalGridSpec)

## 对象导航

|对象|用途|
|---|---|
|[`SignalCSVOutput`](#api-SignalCSVOutput)|保存信号表输出规格及范围，不拥有运行时历史或文件。|
|[`SignalCSVOutput.__post_init__`](#api-SignalCSVOutput-__post_init__)|校验冻结声明，带有明确类型的构造同样受约束。|
|[`CANFramesOutput`](#api-CANFramesOutput)|保存一个来源的原始/重建帧输出规格，与信号表的网格和开关独立。|
|[`CANFramesOutput.__post_init__`](#api-CANFramesOutput-__post_init__)|校验来源、独立规格和重建规则。|
|[`_typed_scope`](#api-_typed_scope)|核带有明确类型的范围与窗口配对。|
|[`require_export_options`](#api-require_export_options)|核带有明确类型的选项引用当前来源/信号/窗口，不读DBC。|
|[`_scope`](#api-_scope)|核会话或单个显式窗口引用。|
|[`_grid`](#api-_grid)|解析显式单位的全局网格。|
|[`_signal_grid_driver`](#api-_signal_grid_driver)|同一信号网格使用一个明确DBC周期；多报文不能擅自选最快周期。|
|[`parse_signal_output`](#api-parse_signal_output)|核显式信号选择及连续量分类。|
|[`_require_frame_direction`](#api-_require_frame_direction)|只有原帧导出/重建需要收发方向；分析可保留未知方向。|
|[`parse_frame_output`](#api-parse_frame_output)|核帧来源、日期和可选重建规则。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.types import SignalDType
from ..results.signal_exports import SignalCSVExportSpec
from ..results.signal_grid import SignalGridSpec
from ..results.frame_exports import FrameExportSpec
from ..results.frame_rebuild import FrameGridSpec
from ..results.frame_patch import FrameRebuildRule
from .checks import PlanValidationError, array_at, choice_at, coordinate_at, duration_at, model_at, object_at, text_at
from ..core.validation import require_identifier
```

</details>

<a id="api-SignalCSVOutput"></a>
## `SignalCSVOutput`

保存信号表输出规格及范围，不拥有运行时历史或文件。

```python
class SignalCSVOutput
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[SignalCSVExportSpec](chronaxis.results.signal_exports.md#api-SignalCSVExportSpec)|是|无|SignalCSVExportSpec，包含导出的原信号别名及可选SignalGridSpec。|
|`scope`|str|否|'session'|`"session"`导出本次分析范围；`"segments"`按某个窗口生成的每个片段分别导出。|
|`window`|str &#124; None|否|None|已有窗口的id，例如 `"context"`。scope为session时省略或填null，不填写窗口名。|
|`period_driver`|str &#124; None|否|None|仅DBC信号网格，已解析的原始报文别名。|

源码：[`src/chronaxis/planning/export_options.py:21`](../../../src/chronaxis/planning/export_options.py#L21)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-SignalCSVOutput-__post_init__"></a>
### `SignalCSVOutput.__post_init__`

校验冻结声明，带有明确类型的构造同样受约束。

```python
SignalCSVOutput.__post_init__()
```

参数：无显式参数。


#### 参数说明

字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/范围错。

本函数直接报告的具体错误：

- `TypeError`：signal_csv需要SignalCSVExportSpec。

源码：[`src/chronaxis/planning/export_options.py:29`](../../../src/chronaxis/planning/export_options.py#L29)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANFramesOutput"></a>
## `CANFramesOutput`

保存一个来源的原始/重建帧输出规格，与信号表的网格和开关独立。

```python
class CANFramesOutput
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|本计划CAN来源名，如bus；不能填写信号CSV来源。|
|`spec`|[FrameExportSpec](chronaxis.results.frame_exports.md#api-FrameExportSpec)|是|无|FrameExportSpec，描述ASC/BLF格式、原时间解释和日期。|
|`scope`|str|否|'session'|`"session"`导出本次分析范围；`"segments"`按某个窗口生成的每个片段分别导出。|
|`window`|str &#124; None|否|None|已有窗口的id，例如 `"context"`。scope为session时省略或填null，不填写窗口名。|
|`resampling`|[FrameGridSpec](chronaxis.results.frame_rebuild.md#api-FrameGridSpec) &#124; None|否|None|可选FrameGridSpec；None保留原始采样，不创建网格帧。|
|`rules`|tuple[[FrameRebuildRule](chronaxis.results.frame_patch.md#api-FrameRebuildRule), ...]|否|()|FrameRebuildRule元组；每项声明报文身份、连续字段和禁止修改的字段。|

源码：[`src/chronaxis/planning/export_options.py:42`](../../../src/chronaxis/planning/export_options.py#L42)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANFramesOutput-__post_init__"></a>
### `CANFramesOutput.__post_init__`

校验来源、独立规格和重建规则。

```python
CANFramesOutput.__post_init__()
```

参数：无显式参数。


#### 参数说明

字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/范围错。

本函数直接报告的具体错误：

- `TypeError`：can_frames需要冻结帧规格与可选网格。
- `TypeError`：重建规则需要有限FrameRebuildRule tuple。
- `ValueError`：未启用重采样不能配置重建规则。
- `ValueError`：重建规则重复或没有可执行规则。

源码：[`src/chronaxis/planning/export_options.py:52`](../../../src/chronaxis/planning/export_options.py#L52)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_typed_scope"></a>
## `_typed_scope`

核带有明确类型的范围与窗口配对。

```python
_typed_scope(scope, window, *, allow_all=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`scope`|str|是|无|位置或关键字。"session"导出会话范围，"segments"逐个导出指定窗口产生的片段。|
|`window`|str|是|无|位置或关键字。segments时必须是有效窗口ID；session时必须为None。|
|`allow_all`|bool|否|False|仅关键字。是否允许segments省略具体窗口以导出全部窗口片段；不是新增scope=all选项，session含义不变。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

不支持或组合错误。

本函数直接报告的具体错误：

- `ValueError`：导出范围错误。

源码：[`src/chronaxis/planning/export_options.py:67`](../../../src/chronaxis/planning/export_options.py#L67)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-require_export_options"></a>
## `require_export_options`

核带有明确类型的选项引用当前来源/信号/窗口，不读DBC。

```python
require_export_options(plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已构造的AnalysisPlan；核对其中导出的来源、信号、窗口及数值类型，不读输入文件。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

声明或引用错误。

本函数直接报告的具体错误：

- `ValueError`：导出窗口未在当前计划声明。
- `ValueError`：导出信号未在当前计划声明。
- `ValueError`：状态/枚举信号不能线性插值。
- `ValueError`：报文导出需要本计划CAN来源。
- `ValueError`：重建报文通道与来源不同。

源码：[`src/chronaxis/planning/export_options.py:76`](../../../src/chronaxis/planning/export_options.py#L76)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_scope"></a>
## `_scope`

核会话或单个显式窗口引用。

```python
_scope(raw, path, windows, *, allow_all=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict[str, object]|是|无|位置或关键字。导出配置对象，读取scope和window字段；完整填写方式见[导出](../exports.md)。|
|`path`|str|是|无|位置或关键字。该对象在JSON中的路径，例如$.outputs.signal_csv，用于准确定位错误。|
|`windows`|WindowPlan|是|无|位置或关键字。本计划的WindowPlan序列；只能引用其中已经定义的窗口。|
|`allow_all`|bool|否|False|仅关键字。是否允许segments省略具体窗口以导出全部窗口片段；不是新增scope=all选项，session含义不变。|

### 返回说明

(scope,window)。

### 异常说明

配置错。

源码：[`src/chronaxis/planning/export_options.py:106`](../../../src/chronaxis/planning/export_options.py#L106)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_grid"></a>
## `_grid`

解析显式单位的全局网格。

```python
_grid(raw, path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict[str, object]|是|无|位置或关键字。重采样网格配置，含period、max_gap和可选origin；时长使用带单位字符串。|
|`path`|str|是|无|位置或关键字。网格配置在JSON中的路径，用于指出哪项时长或起点错误。|

### 返回说明

period/origin/max_gap整数ns。

### 异常说明

时间错。

源码：[`src/chronaxis/planning/export_options.py:120`](../../../src/chronaxis/planning/export_options.py#L120)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_signal_grid_driver"></a>
## `_signal_grid_driver`

同一信号网格使用一个明确DBC周期；多报文不能擅自选最快周期。

```python
_signal_grid_driver(definitions, sources, continuous, driver, path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|Mapping[str, SignalDefinition]|是|无|位置或关键字。以信号别名为键的定义，提供来源、类型、单位和有效期；不会在这里重新加载DBC。|
|`sources`|Sequence[SourcePlan]|是|无|位置或关键字。当前计划的来源定义，用于检查绑定来源类型及原始报文定位；不在此函数打开输入。|
|`continuous`|bool|是|无|位置或关键字。是否按连续持有状态求值；False用于真实记录更新，不额外把边界当作新样本。|
|`driver`|str &#124; None|是|无|位置或关键字。推进该计算的原信号别名；None按实际更新组求值，固定/DBC模式使用已解析的唯一别名。|
|`path`|str|是|无|位置或关键字。配置中的字段路径，用于在错误中指出具体位置，例如intervals.default。|

### 返回说明

唯一原始别名。

### 异常说明

类型/格式/歧义。

源码：[`src/chronaxis/planning/export_options.py:127`](../../../src/chronaxis/planning/export_options.py#L127)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_signal_output"></a>
## `parse_signal_output`

核显式信号选择及连续量分类。

```python
parse_signal_output(value, signals, windows, *, sources=())
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object] &#124; None|是|无|位置或关键字。outputs.signal_csv配置；None表示不导出信号表，字段见[导出](../exports.md)。|
|`signals`|SignalPlan|是|无|位置或关键字。当前计划的SignalPlan序列，用于核对导出别名及数值类型。|
|`windows`|WindowPlan|是|无|位置或关键字。当前计划WindowPlan序列；segments范围只能引用其中的window_id。|
|`sources`|Sequence[SourcePlan]|否|()|仅关键字。当前计划的来源定义，用于检查绑定来源类型及原始报文定位；不在此函数打开输入。|

### 返回说明

SignalCSVOutput或None。

### 异常说明

定位配置错。

源码：[`src/chronaxis/planning/export_options.py:150`](../../../src/chronaxis/planning/export_options.py#L150)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_require_frame_direction"></a>
## `_require_frame_direction`

只有原帧导出/重建需要收发方向；分析可保留未知方向。

```python
_require_frame_direction(source)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|SourcePlan|是|无|位置或关键字。选定原帧导出来源，检查原始CSV是否提供报文方向所需声明。|

源码：[`src/chronaxis/planning/export_options.py:185`](../../../src/chronaxis/planning/export_options.py#L185)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_frame_output"></a>
## `parse_frame_output`

核帧来源、日期和可选重建规则。

```python
parse_frame_output(value, sources, windows)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object] &#124; None|是|无|位置或关键字。outputs.can_frames配置；None表示不导出CAN报文，字段见[导出](../exports.md)。|
|`sources`|SourcePlan|是|无|位置或关键字。当前计划SourcePlan序列，用于核对CAN来源名和通道。|
|`windows`|WindowPlan|是|无|位置或关键字。当前计划WindowPlan序列；segments范围只能引用其中的window_id。|

### 返回说明

CANFramesOutput或None。

### 异常说明

定位配置错。

源码：[`src/chronaxis/planning/export_options.py:193`](../../../src/chronaxis/planning/export_options.py#L193)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
