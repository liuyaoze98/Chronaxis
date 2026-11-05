# `chronaxis.core.calculations`

定义“要算什么”和“算完得到什么”的数据对象。CalculationDefinition保存指标种类、时间范围和缺失数据处理选择；CalculationSeries保存参与计算的时间和值；CalculationResult保存计算值及数据不完整的原因。例如教程中功率恒为4000W，请求0—12秒而记录只到8秒：选择report时，同时保留32000J、partial和8/12的请求覆盖率；选择strict时，value为None。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`CalculationDefinition`](#api-CalculationDefinition)|一次指标计算的请求，指定运算、纳秒时间窗口、输出单位，以及数据不完整时保留部分数值还是返回空值。CalculationSeries提供实际输入，CalculationResult保存计算结果；三者分别表示要求、数据和结果。|
|[`CalculationDefinition.__post_init__`](#api-CalculationDefinition-__post_init__)|检查指标种类、时间范围和缺失数据处理方式。计算平均值时必须明确选择样本平均或时间加权平均。|
|[`CalculationSeries`](#api-CalculationSeries)|把一段时间内要计算的值排成时间序列。例如时间为0、1、4秒，值为0、10、0：0—1秒使用0，1—4秒使用10；4秒的末值本身没有持续时间。每个时间都有对应的值和标记，不能少一项或混入另一种数据类型。|
|[`CalculationSeries.__post_init__`](#api-CalculationSeries-__post_init__)|创建CalculationSeries时自动检查时间和值是否能一一对应。例如3个时间必须配3个值和3个更新标记，时间必须递增，首末时间必须与observation一致。|
|[`CalculationResult`](#api-CalculationResult)|保存一个指标及解释它所需的信息。value是数值，unit是单位；status/reason说明结果完整、只算出部分，还是无法判断。时间和覆盖率说明究竟缺了哪一部分，不能只取value而忽略它们。|
|[`CalculationResult.__post_init__`](#api-CalculationResult-__post_init__)|检查结果字段是否互相矛盾。例如观测范围只有8秒，却填写有效数据有9秒，或者把NaN、无穷大作为正常指标值，都会报错；不会替调用者修改这些值。|
|[`CalculationConversion`](#api-CalculationConversion)|保存归约结束后的一次单位转换，不保存样本或额外结果副本。|
|[`CalculationConversion.__post_init__`](#api-CalculationConversion-__post_init__)|检查不可变转换描述符，拒绝无效版本和不可执行系数。|
|[`CalculationConversion.dtype`](#api-CalculationConversion-dtype)|在执行前确定输出类型，不根据某条样本是否整除改变类型。|
|[`calculation_conversion`](#api-calculation_conversion)|取得完整输出换算，包括均值/极值允许的绝对温度偏移。|
|[`calculation_unit`](#api-calculation_unit)|提供没有加法偏移的单位/倍率接口，兼容旧调用和积分归约。|
|[`merge_ranges`](#api-merge_ranges)|合并同一种未知证据的相邻区间，仅用于诊断序列化。|
|[`classify_calculation_value`](#api-classify_calculation_value)|按既有政策分类数值，供完整结果和精简内部结果共用。|
|[`classify_coverage`](#api-classify_coverage)|只在请求门槛时判断三种真实覆盖，不影响report/strict的数值政策。|
|[`make_calculation_result`](#api-make_calculation_result)|结合计算值、有效时长和缺失信息，确定结果状态并创建CalculationResult。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from math import isfinite
from .models import Interval, SourceRef
from .moments import MOMENTS, moment_ddof, moment_source_unit
from .quantiles import SAMPLE_QUANTILES, quantile_probability
from .numeric import ScalarValue
from .types import SignalDType as D, QualityFlag as Q
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-CalculationDefinition"></a>
## `CalculationDefinition`

一次指标计算的请求，指定运算、纳秒时间窗口、输出单位，以及数据不完整时保留部分数值还是返回空值。CalculationSeries提供实际输入，CalculationResult保存计算结果；三者分别表示要求、数据和结果。

```python
class CalculationDefinition
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`calculation_id`|str|是|无|当前任务指标唯一简单名称。|
|`operation`|str|是|无|九种值：`integral`按所选计算间隔积分；`duration`累计条件成立的秒数；`select`返回满足条件的数据行；`sample_minimum/sample_maximum/sample_mean`分别计算真实样本最小值、最大值、算术平均；`min_time/max_time/time_weighted_mean`分别计算有持续时间的值的最小值、最大值、时间加权平均。详见[逐项数值例子](../calculations.md)。|
|`window`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|要计算的开始/结束时间，用Interval表示，单位为纳秒。例如0—12秒是Interval(0, 12000000000)。|
|`partial_policy`|str|否|'report'|`"report"`：数据不全时保留已知部分算出的数值，并标记partial；`"strict"`：所需范围内有数据缺失时返回None。它不会补出缺失数据。|
|`output_unit`|str &#124; None|否|None|想要的结果单位，例如J或Wh。None表示采用该计算支持的默认单位；不能凭填写标签执行未知换算。|
|`scope`|str|否|'session'|这次指标属于整个会话session、一次事件event还是一个上下文片段segment。|
|`minimum_coverage`|float|否|0.0|要求达到的最低覆盖比例，0～1且包含端点。0.9表示90%，不能填90；它影响质量判断，不补齐数据。|
|`config_version`|int|否|4|单位规则版本，不改变旧位置参数。|
|`ddof`|int &#124; None|否|None|只对方差/标准差有含义。|
|`q`|int &#124; float &#124; None|否|None|仅sample_quantile显式指定概率。|

源码：[`src/chronaxis/core/calculations.py:39`](../../../src/chronaxis/core/calculations.py#L39)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CalculationDefinition-__post_init__"></a>
### `CalculationDefinition.__post_init__`

检查指标种类、时间范围和缺失数据处理方式。计算平均值时必须明确选择样本平均或时间加权平均。

```python
CalculationDefinition.__post_init__()
```

参数：无显式参数。


#### 参数说明

无；读取当前冻结声明字段。

#### 返回说明

None，保持原请求窗口与scope。

#### 异常说明

TypeError/ValueError为ID/窗口/未知算子或政策。

本函数直接报告的具体错误：

- `ValueError`：指标需明确已实现算子及Interval。
- `ValueError`：未知partial_policy或scope。
- `ValueError`：minimum_coverage需0—1有限数值。

源码：[`src/chronaxis/core/calculations.py:63`](../../../src/chronaxis/core/calculations.py#L63)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CalculationSeries"></a>
## `CalculationSeries`

把一段时间内要计算的值排成时间序列。例如时间为0、1、4秒，值为0、10、0：0—1秒使用0，1—4秒使用10；4秒的末值本身没有持续时间。每个时间都有对应的值和标记，不能少一项或混入另一种数据类型。

```python
class CalculationSeries
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|实际连续分析域，不外推EOF。|
|`times_ns`|tuple[int, ...]|是|无|严格递增，完整首/末端；零域一点。|
|`values`|tuple[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue), ...]|是|无|同一dtype；BOOL用于duration/select，ENUM只用于select。|
|`actual_value_updates`|tuple[bool, ...]|是|无|同长真实数值依赖更新标志。|
|`unit`|str|是|无|当前分析值单位，已经归一化，不能重复DBC factor。|
|`conditions`|tuple[[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue), ...] &#124; None|否|None|可选BOOL三值选择。|
|`diagnostics`|tuple[[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag), ...]|否|()|原依赖质量，与逻辑结果质量分开。|
|`binding_identity`|str|否|'explicit-synthetic'|当前输入执行身份/外部合成声明。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|否|()|所有实际依赖原字段关联。|

源码：[`src/chronaxis/core/calculations.py:101`](../../../src/chronaxis/core/calculations.py#L101)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CalculationSeries-__post_init__"></a>
### `CalculationSeries.__post_init__`

创建CalculationSeries时自动检查时间和值是否能一一对应。例如3个时间必须配3个值和3个更新标记，时间必须递增，首末时间必须与observation一致。

```python
CalculationSeries.__post_init__()
```

参数：无显式参数。


#### 参数说明

无需直接传参或手动调用；检查创建CalculationSeries时传入的字段。

#### 返回说明

None；全部检查通过后对象创建成功。省略diagnostics时，会根据值及条件已有的质量标记生成诊断。

#### 异常说明

字段类型不对会抛TypeError；时间回退、列长度不一致或首末范围不符会抛ValueError；时间超出int64范围会抛OverflowError。不会自动排序、补值或截短数组。

源码：[`src/chronaxis/core/calculations.py:123`](../../../src/chronaxis/core/calculations.py#L123)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CalculationResult"></a>
## `CalculationResult`

保存一个指标及解释它所需的信息。value是数值，unit是单位；status/reason说明结果完整、只算出部分，还是无法判断。时间和覆盖率说明究竟缺了哪一部分，不能只取value而忽略它们。

```python
class CalculationResult
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|原计算请求，例如算哪段时间、输出什么单位、数据不全时用report还是strict。|
|`value`|int &#124; float &#124; None|是|无|计算得到的int/float，或None（无法给出数值）。0可以是正确答案；NaN和正负无穷不接受。|
|`unit`|str|是|无|该结果使用的单位。数值已经完成单位换算，读取时不要再乘同一换算倍率。|
|`status`|str|是|无|complete表示完整；partial表示只算出已知部分；indeterminate表示无法给出所需结果。|
|`reason`|str|是|无|更具体的原因，例如partial_coverage表示覆盖不完整，empty_selection表示没有数据满足筛选条件。|
|`actual_window`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|请求范围与实际观测范围相交的部分。请求0—12秒、记录只到8秒时，它是0—8秒；没有交集时为None。|
|`window_duration_ns`|int|是|无|actual_window的长度，以纳秒计。上例为8000000000，而不是请求的12000000000。|
|`value_valid_duration_ns`|int|是|无|实际窗口内，信号值可用于该指标计算的总时长，以纳秒计。不能大于窗口本身。|
|`condition_known_duration_ns`|int|是|无|实际窗口内能确定条件为真或假的总时长；条件为假仍算“已知”，未知才不算。没有条件时等于实际窗口长度。|
|`selected_duration_ns`|int|是|无|同时满足有效值和True筛选条件的时长；duration指标还要求主布尔信号为True。|
|`value_coverage`|float &#124; None|是|无|value_valid_duration_ns除以window_duration_ns。窗口为0时用None，不能用NaN。|
|`condition_coverage`|float &#124; None|是|无|condition_known_duration_ns除以window_duration_ns；没有实际窗口时为None。|
|`requested_coverage`|float &#124; None|是|无|实际窗口长度除以请求窗口长度。例如8秒/12秒约为0.667；请求长度为0时为None。|
|`valid_sample_count`|int|是|无|真正更新过数值、数值有效且通过筛选的样本个数。程序为窗口边界补的时间点不因此成为新样本。|
|`value_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|实际分析中数值无法使用的时间区间，例如某段功率缺失或已过期。|
|`condition_unknown_ranges`|tuple[[Interval](chronaxis.core.models.md#api-Interval), ...]|是|无|无法判断条件真假的时间区间；已知条件为False的时间不放在这里。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|来源和计算出现的问题标记，例如缺值、过期或除零。可以同时记录多种原因。|
|`binding_identity`|str|是|无|标识本次实际使用的信号与来源对应关系，用于追查输入是否改变。|
|`source_refs`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|用于定位原始数据的来源信息，例如来源名、原字段及对应记录位置。|
|`coverage_status`|str|否|'sufficient'|sufficient表示三种覆盖比例都达到minimum_coverage；否则为indeterminate。它与status分别记录，不会改变已经算出的部分数值。|

源码：[`src/chronaxis/core/calculations.py:186`](../../../src/chronaxis/core/calculations.py#L186)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CalculationResult-__post_init__"></a>
### `CalculationResult.__post_init__`

检查结果字段是否互相矛盾。例如观测范围只有8秒，却填写有效数据有9秒，或者把NaN、无穷大作为正常指标值，都会报错；不会替调用者修改这些值。

```python
CalculationResult.__post_init__()
```

参数：无显式参数。


#### 参数说明

没有需要手动传给此方法的参数。创建CalculationResult时，Python自动调用它检查各字段；所有时长字段均使用整数纳秒。

#### 返回说明

None。合法字段保持原样；不会把错误的9秒自动改成8秒，也不会重新计算指标。

#### 异常说明

对象/字段类型不符时抛TypeError；数值为NaN/无穷大、状态名称不支持、时长超过窗口、覆盖率不在0—1内或范围长度不一致时抛ValueError。

源码：[`src/chronaxis/core/calculations.py:217`](../../../src/chronaxis/core/calculations.py#L217)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CalculationConversion"></a>
## `CalculationConversion`

保存归约结束后的一次单位转换，不保存样本或额外结果副本。

factor和offset为输出值=归约值*factor+offset，整数系数保持精确整数。
version固定为当前规则；实例在一次计划中不可修改。

```python
class CalculationConversion
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`unit`|str|是|无|输出单位，与转换后的数值一起使用。|
|`factor`|int &#124; float|是|无|一次乘法系数，不重复上游DBC或绑定缩放。|
|`offset`|int &#124; float|否|0|绝对温度归约可用；积分输出不允许偏移。|
|`version`|int|否|4|当前单位规则，旧版本明确拒绝。|

源码：[`src/chronaxis/core/calculations.py:280`](../../../src/chronaxis/core/calculations.py#L280)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CalculationConversion-__post_init__"></a>
### `CalculationConversion.__post_init__`

检查不可变转换描述符，拒绝无效版本和不可执行系数。

```python
CalculationConversion.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取unit、factor、offset和version。

#### 返回说明

None。

#### 异常说明

TypeError/ValueError为文本、类型、有限性或版本错误。

源码：[`src/chronaxis/core/calculations.py:292`](../../../src/chronaxis/core/calculations.py#L292)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CalculationConversion-dtype"></a>
### `CalculationConversion.dtype`

在执行前确定输出类型，不根据某条样本是否整除改变类型。

```python
CalculationConversion.dtype(input_dtype)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`input_dtype`|SignalDType|是|无|位置或关键字。转换前的数值类型；据此区分可保留的整数与须提升的浮点结果。|

#### 返回说明

保持原类型，或在小数倍率/偏移时返回FLOAT64。

#### 异常说明

ValueError为BOOL/ENUM请求数值单位变换。

源码：[`src/chronaxis/core/calculations.py:306`](../../../src/chronaxis/core/calculations.py#L306)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-calculation_conversion"></a>
## `calculation_conversion`

取得完整输出换算，包括均值/极值允许的绝对温度偏移。

```python
calculation_conversion(spec, input_unit)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。已校验的算子配置，由操作、输入尺度和可选目标共同决定结果换算。|
|`input_unit`|str|是|无|位置或关键字。运算输入当前使用的物理单位标签，作为单位推导或换算起点。|

### 返回说明

CalculationConversion，数值后端在归约后应用一次；空结果不转换。

### 异常说明

ValueError为不兼容量种、偏移积分或未知单位转换；TypeError为模型错误。

源码：[`src/chronaxis/core/calculations.py:323`](../../../src/chronaxis/core/calculations.py#L323)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-calculation_unit"></a>
## `calculation_unit`

提供没有加法偏移的单位/倍率接口，兼容旧调用和积分归约。

```python
calculation_unit(spec, input_unit)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。CalculationDefinition，提供算子和可选output_unit；input_unit为当前分析值单位。|
|`input_unit`|str|是|无|位置或关键字。输入值的单位，例如W；积分会据此得到W*s或按配置转换后的单位，其他运算按自身规则返回单位。|

### 返回说明

(输出单位, 一次乘法系数)。

### 异常说明

ValueError: 要求的单位不在同一已知维度，转换未注册或因子非有限。

本函数直接报告的具体错误：

- `ValueError`：指标单位转换非有限。
- `ValueError`：duration需无量纲BOOL输入及s输出。

源码：[`src/chronaxis/core/calculations.py:376`](../../../src/chronaxis/core/calculations.py#L376)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-merge_ranges"></a>
## `merge_ranges`

合并同一种未知证据的相邻区间，仅用于诊断序列化。

```python
merge_ranges(ranges)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ranges`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。按时间有序的Interval序列；表示待合并证据范围，不是待合并的活动事件。|

### 返回说明

Interval tuple，不修改原活动/条件或填平已知缺口。

### 异常说明

模型错误传播，无数值分析副作用。

源码：[`src/chronaxis/core/calculations.py:390`](../../../src/chronaxis/core/calculations.py#L390)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-classify_calculation_value"></a>
## `classify_calculation_value`

按既有政策分类数值，供完整结果和精简内部结果共用。

```python
classify_calculation_value(spec, value, observed_duration_ns, known_duration_ns, selected_duration_ns, selected_unknown_duration_ns, *, all_false=False, calculation_failed=False, sample_count=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。已核对的指标声明，包含算子、实际请求范围、数据不全时的处理方式和输出单位。|
|`value`|int &#124; float &#124; None|是|无|位置或关键字。计算所得的有限数值；None表示不能给出数值，需同时读取状态和原因，不能替换成0。|
|`observed_duration_ns`|int|是|无|位置或关键字。实际观测与请求窗口交集的纳秒长度；0不能冒充完整观测。|
|`known_duration_ns`|int|是|无|位置或关键字。实际窗口中条件可以判为真或假的总纳秒数，不包含条件未知的区间。|
|`selected_duration_ns`|int|是|无|位置或关键字。条件成立且数值有效的区间总纳秒数。|
|`selected_unknown_duration_ns`|int|是|无|位置或关键字。条件成立但数值不可用的总纳秒数，用于判定结果是否完整。|
|`all_false`|bool|否|False|仅关键字。条件在整个有效请求范围内均明确为假；此时条件积分可以得到正常0。|
|`calculation_failed`|bool|否|False|仅关键字。归约出现无法给出有效数值的错误；此标志防止把失败当成没有数据满足筛选条件的0。|
|`sample_count`|int|否|0|仅关键字。条件已知为真且有真实有效数值更新的次数，用于识别样本数不足和已知空集。|

### 返回说明

(value, status, reason)。

### 异常说明

内部参数错误原样传播；不构造范围或追溯记录。

源码：[`src/chronaxis/core/calculations.py:412`](../../../src/chronaxis/core/calculations.py#L412)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-classify_coverage"></a>
## `classify_coverage`

只在请求门槛时判断三种真实覆盖，不影响report/strict的数值政策。

```python
classify_coverage(spec, observed_duration_ns, value_duration_ns, known_duration_ns)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。已核对的指标声明，包含算子、实际请求范围、数据不全时的处理方式和输出单位。|
|`observed_duration_ns`|int|是|无|位置或关键字。实际观测与请求窗口交集的纳秒长度；0不能冒充完整观测。|
|`value_duration_ns`|int|是|无|位置或关键字。数值有效的总纳秒数，用于与覆盖门槛比较。|
|`known_duration_ns`|int|是|无|位置或关键字。实际窗口中条件可以判为真或假的总纳秒数，不包含条件未知的区间。|

### 返回说明

sufficient或indeterminate。

### 异常说明

无主动异常；内部量由各数值核独立求得，不构造区间明细。

源码：[`src/chronaxis/core/calculations.py:466`](../../../src/chronaxis/core/calculations.py#L466)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-make_calculation_result"></a>
## `make_calculation_result`

结合计算值、有效时长和缺失信息，确定结果状态并创建CalculationResult。

```python
make_calculation_result(spec, series, value, unit, actual, value_duration_ns, known_duration_ns, selected_duration_ns, selected_unknown_duration_ns, sample_count, value_unknown, condition_unknown, quality, *, all_false=False, calculation_failed=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。原指标设置，含请求范围、统计种类和部分结果处理方式。|
|`series`|[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)|是|无|位置或关键字。这次统计使用的数值和条件序列，提供单位、观测范围和输入来源。|
|`value`|int &#124; float &#124; None|是|无|位置或关键字。已计算出的候选指标值；没有可用值时为None。函数再结合覆盖情况和partial_policy决定是否保留这个值。|
|`unit`|str|是|无|位置或关键字。候选数值当前采用的结果单位，例如J；应与此前计算和单位转换一致。|
|`actual`|int|是|无|位置或关键字。请求与观测范围的交集，无交集时为None。 value_duration、known_duration、selected_duration: 值有效、条件已知、 有效值与TRUE选择相交的时长，均为整数纳秒；duration还要求主BOOL为TRUE。|
|`value_duration_ns`|int|是|无|位置或关键字。主数值有效的总时长，单位纳秒，不因条件为FALSE而删除这项覆盖事实。|
|`known_duration_ns`|int|是|无|位置或关键字。条件可以确定为TRUE或FALSE的总时长，单位纳秒；UNKNOWN部分不计入。|
|`selected_duration_ns`|int|是|无|位置或关键字。条件为TRUE且主值有效的总时长，单位纳秒；duration运算还要求主布尔值为TRUE。|
|`selected_unknown_duration_ns`|int|是|无|位置或关键字。条件已知为真、但数值未知的累计时长，单位纳秒，须大于等于0。|
|`sample_count`|int|是|无|位置或关键字。条件满足且数值有效的真实更新条数，不按保持区间的边界数量计算。|
|`value_unknown`|Iterable[[Interval](chronaxis.core.models.md#api-Interval)]|是|无|位置或关键字。数值失效的时间区间；函数会合并重叠区间，保存到结果中供查缺失位置。|
|`condition_unknown`|Iterable[[Interval](chronaxis.core.models.md#api-Interval)]|是|无|位置或关键字。无法判断筛选条件真假的时间区间；已知False的区间不属于这里。|
|`quality`|QualityFlag|是|无|位置或关键字。输入和计算过程中出现的质量原因，可组合多个位；完整含义见[质量标记](../results.md)。|
|`all_false`|bool|否|False|仅关键字。all_false默认False，表示是否已有全程FALSE证据。     calculation_failed: 默认False，表示归约或输出转换是否失败。|
|`calculation_failed`|bool|否|False|仅关键字。默认False，表示归约或输出转换是否失败。|

### 返回说明

CalculationResult，保留覆盖、来源与原因。完整观测且全程FALSE时积分为零，
    没有数据满足筛选条件的样本统计为None；其他缺失情形不能据空归约推断正常零。

### 异常说明

输出事实不满足CalculationResult要求时传播模型的TypeError或ValueError。

### 流程说明

先判断零窗口、无观测和计算失败，再处理没有数据满足筛选条件与未知数据；
    有部分候选值时，report保留并标partial，strict清为None。
    本函数不计算积分或样本归约，各时长和候选值由调用者独立计算。

源码：[`src/chronaxis/core/calculations.py:478`](../../../src/chronaxis/core/calculations.py#L478)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
