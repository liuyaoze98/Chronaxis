# `chronaxis.sources.models`

规定读取来源时怎样描述字段、提出读取请求，以及怎样返回一批信号数据。ReadRequest.batch_rows是所有信号样本数之和，例如一行CSV包含两个信号更新，就占两个样本。这里的数据对象帮助读取器和分析器按同一格式交接。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`freeze_metadata`](#api-freeze_metadata)|递归复制JSON元数据，避免共享调用者的可变容器。|
|[`FieldLocation`](#api-FieldLocation)|保存原字段在来源中的位置，区分原字段与表达式别名。|
|[`FieldLocation.__post_init__`](#api-FieldLocation-__post_init__)|检查来源和原字段，冻结附加定位信息。|
|[`FieldDescription`](#api-FieldDescription)|描述一个可请求的输出别名及其原字段、类型和单位。|
|[`FieldDescription.__post_init__`](#api-FieldDescription-__post_init__)|校验字段描述，并冻结用于跨批核对的元数据。|
|[`SourceCapabilities`](#api-SourceCapabilities)|逐项记录来源适配器声明的能力和限制。|
|[`SourceCapabilities.__post_init__`](#api-SourceCapabilities-__post_init__)|检查能力开关及诊断、限制文本的结构。|
|[`SourceDescription`](#api-SourceDescription)|保存一个来源的静态字段、时钟及能力声明。|
|[`SourceDescription.__post_init__`](#api-SourceDescription-__post_init__)|检查描述归属、别名唯一性和已知的观测范围。|
|[`ReadRequest`](#api-ReadRequest)|说明本次会话要读取的信号别名、分析范围和批次上限。|
|[`ReadRequest.__post_init__`](#api-ReadRequest-__post_init__)|检查请求会话、唯一别名、时间范围和正整数批次上限。|
|[`SignalSeries`](#api-SignalSeries)|保存一批中的单个信号列及每个样本的来源身份。|
|[`SignalSeries.__post_init__`](#api-SignalSeries-__post_init__)|检查单列布局、有效性和样本身份，再复制为只读数组。|
|[`SignalSeries.nbytes`](#api-SignalSeries-nbytes)|统计本列五个数组的存储字节数。|
|[`SignalBatch`](#api-SignalBatch)|传送一个来源在当前会话中的异步信号列和读取进度。|
|[`SignalBatch.__post_init__`](#api-SignalBatch-__post_init__)|检查批次归属、列名称和观测终点，不可修改的数据列映射。|
|[`SignalBatch.sample_count`](#api-SignalBatch-sample_count)|按所有列的样本数总和计算本批大小。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import TypeAlias
from ..core.models import Interval, SourceRef
from ..core.numeric_numpy import NumericArray
from ..core.types import SignalDType
from ..core.validation import require_identifier, require_scalar, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-freeze_metadata"></a>
## `freeze_metadata`

递归复制JSON元数据，避免共享调用者的可变容器。

```python
freeze_metadata(value: JsonValue) -> JsonValue
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JsonValue|是|无|位置或关键字。JSON标量、字符串键映射、list或tuple；不接受任意对象。|

### 返回说明

JsonValue。映射变为新的只读Mapping，数组变为tuple，标量保持原值。

### 异常说明

TypeError: 出现非JSON对象或非字符串键。
    ValueError: 浮点元数据包含NaN或无穷值。

本函数直接报告的具体错误：

- `TypeError`：metadata仅接受JSON类型。
- `ValueError`：metadata浮点必须有限。
- `TypeError`：metadata键必须为字符串。

### 副作用说明

无。复制容器，不修改传入结构。

返回类型：JsonValue。

源码：[`src/chronaxis/sources/models.py:42`](../../../src/chronaxis/sources/models.py#L42)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-FieldLocation"></a>
## `FieldLocation`

保存原字段在来源中的位置，区分原字段与表达式别名。

source是来源名，field保存表列或内存字段原文，允许含点号。
locator保存额外的JSON定位信息，并在构造时深度冻结。
定位信息只说明如何查找字段，不能证明对应文件或旧来源能力已经核实。

```python
class FieldLocation
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|来源名，不从路径猜测。|
|`field`|str|是|无|列或已解码字段原文，允许点号。|
|`locator`|Mapping[str, JsonValue]|否|{}|profile额外定位证据。|

源码：[`src/chronaxis/sources/models.py:80`](../../../src/chronaxis/sources/models.py#L80)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-FieldLocation-__post_init__"></a>
### `FieldLocation.__post_init__`

检查来源和原字段，冻结附加定位信息。

```python
FieldLocation.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。读取source、field和locator。

#### 返回说明

None。将locator替换为独立的只读快照。

#### 异常说明

TypeError或ValueError: 名称、字段文本或JSON定位信息不合法。

本函数直接报告的具体错误：

- `TypeError`：locator必须为Mapping。

返回类型：None。

源码：[`src/chronaxis/sources/models.py:92`](../../../src/chronaxis/sources/models.py#L92)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-FieldDescription"></a>
## `FieldDescription`

描述一个可请求的输出别名及其原字段、类型和单位。

name是输出别名，field保留原定位；dtype与unit描述归一化后的输出。
metadata保存只读转换和可选语义声明，不强制普通分析加入领域目录。
枚举类型必须在metadata.labels中声明非空、唯一的标签集合，供跨批核对。
同一原字段可以有不同显式转换，各别名分别保存描述。

```python
class FieldDescription
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|iter_batches可请求的输出别名。|
|`field`|[FieldLocation](chronaxis.sources.models.md#api-FieldLocation)|是|无|完整原定位，区别于semantic_id。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`unit`|str|是|无|已归一化输出单位，未知标签不自动verified。|
|`metadata`|Mapping[str, JsonValue]|否|{}|可选声明与转换证据。|

源码：[`src/chronaxis/sources/models.py:115`](../../../src/chronaxis/sources/models.py#L115)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-FieldDescription-__post_init__"></a>
### `FieldDescription.__post_init__`

校验字段描述，并冻结用于跨批核对的元数据。

```python
FieldDescription.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。读取name、field、dtype、unit和metadata。

#### 返回说明

None。metadata成为只读快照；不会读取来源来核实单位或定位。

#### 异常说明

TypeError或ValueError: 名称、定位、类型、单位文本、JSON结构或枚举标签域错误。

本函数直接报告的具体错误：

- `TypeError`：field需要FieldLocation和SignalDType。
- `TypeError`：metadata必须为Mapping。
- `ValueError`：enum描述metadata需要非空唯一labels。

返回类型：None。

源码：[`src/chronaxis/sources/models.py:130`](../../../src/chronaxis/sources/models.py#L130)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SourceCapabilities"></a>
## `SourceCapabilities`

逐项记录来源适配器声明的能力和限制。

decoded_output、raw_export、repeat_scan和random_access分别表示已解码输出、
原始导出、可重复读取和随机访问能力，必须使用真实布尔值。
diagnostics与limitations是不可变说明元组。模型只校验声明结构，
不会运行来源来证明能力，也不因repeat_scan为True自动增加旧日志扫描。

```python
class SourceCapabilities
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`decoded_output`|bool|是|无|是否实际能返回逐次已解码信号。|
|`raw_export`|bool|是|无|原路径已支持原始导出时才可为True。|
|`repeat_scan`|bool|是|无|可重复调用的能力，不授权多次旧扫描。|
|`random_access`|bool|是|无|是否可随机定位，普通迭代不等同此能力。|
|`diagnostics`|tuple[str, ...]|否|()|已实际暴露的诊断。|
|`limitations`|tuple[str, ...]|否|()|未获得的元数据或兼容限制。|

源码：[`src/chronaxis/sources/models.py:167`](../../../src/chronaxis/sources/models.py#L167)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SourceCapabilities-__post_init__"></a>
### `SourceCapabilities.__post_init__`

检查能力开关及诊断、限制文本的结构。

```python
SourceCapabilities.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。读取四个能力开关、diagnostics和limitations。

#### 返回说明

None。保留原声明，不推断或测试来源能力。

#### 异常说明

TypeError或ValueError: 开关不是bool，文本列表不是tuple，或说明文本为空。

本函数直接报告的具体错误：

- `TypeError`：capability必须为bool。
- `TypeError`：diagnostics/limitations必须为tuple。

返回类型：None。

源码：[`src/chronaxis/sources/models.py:183`](../../../src/chronaxis/sources/models.py#L183)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SourceDescription"></a>
## `SourceDescription`

保存一个来源的静态字段、时钟及能力声明。

name标识来源，fields保存唯一输出别名，timebase_id标识声明的时间基准。
observation_start_ns和observation_end_ns保存已知观测边界，未知端点各自为None。
capabilities记录能力说明，legacy_profile可保存旧来源的契约标识。
metadata_status区分'verified'已核实、'declared'仅声明和'unavailable'不可用。
模型校验不会读取来源，也不会自动将声明状态升级为已核实。

```python
class SourceDescription
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|当前计划来源名。|
|`fields`|tuple[[FieldDescription](chronaxis.sources.models.md#api-FieldDescription), ...]|是|无|已描述的输出别名和原定位。|
|`timebase_id`|str|是|无|明确来源时基ID。|
|`observation_start_ns`|int &#124; None|是|无|未知开始保留None。|
|`observation_end_ns`|int &#124; None|是|无|未知终点不补周期。|
|`capabilities`|[SourceCapabilities](chronaxis.sources.models.md#api-SourceCapabilities)|是|无|逐项审核能力。|
|`legacy_profile`|str &#124; None|否|None|仅旧来源需要冻结profile身份。 None表示不是通过旧解码实现接入的来源。|
|`metadata_status`|str|否|'declared'|verified/declared/unavailable。|

源码：[`src/chronaxis/sources/models.py:210`](../../../src/chronaxis/sources/models.py#L210)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SourceDescription-__post_init__"></a>
### `SourceDescription.__post_init__`

检查描述归属、别名唯一性和已知的观测范围。

```python
SourceDescription.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。读取来源名称、字段元组、时钟、观测端点、能力和证据状态。

#### 返回说明

None。已知双端点按时间区间检查，未知端点保持None。

#### 异常说明

TypeError或ValueError: 描述类型、归属、重复名称、状态或旧契约标识错误。
    OverflowError: 时间坐标或区间跨度超出范围。

#### 副作用说明

无输入读取；名称合法不表示来源实际存在。

返回类型：None。

源码：[`src/chronaxis/sources/models.py:229`](../../../src/chronaxis/sources/models.py#L229)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReadRequest"></a>
## `ReadRequest`

说明本次会话要读取的信号别名、分析范围和批次上限。

session_id绑定当前会话，signal_names指定列顺序并允许空投影。
domain_start_ns与domain_end_ns是分析请求坐标，不表示来源实际观测范围。
batch_rows限制每批全部信号列的样本数之和，不能按宽表行数计算。
请求范围不授权修改旧读取链；适配器保留分析开始前的必要更新及真实终点。
同一时间组可以跨批，分批上限不代表该组已经完整。

```python
class ReadRequest
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`session_id`|str|是|无|明确会话身份。|
|`signal_names`|tuple[str, ...]|是|无|当前绑定输出别名，允许空投影。|
|`domain_start_ns`|int &#124; None|是|无|分析域起点；纯消息整文件请求可未声明。|
|`domain_end_ns`|int &#124; None|是|无|分析域终点；与起点同时未声明。|
|`batch_rows`|int|是|无|所有series样本数总和上限。|

源码：[`src/chronaxis/sources/models.py:275`](../../../src/chronaxis/sources/models.py#L275)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ReadRequest-__post_init__"></a>
### `ReadRequest.__post_init__`

检查请求会话、唯一别名、时间范围和正整数批次上限。

```python
ReadRequest.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。读取session_id、signal_names、domain_start_ns、domain_end_ns和batch_rows。

#### 返回说明

None。保持别名顺序，不去重或裁剪来源数据。

#### 异常说明

TypeError或ValueError: 名称、容器、重复别名、时间范围或批次大小错误。
    OverflowError: 时间范围超出整数纳秒约束。

返回类型：None。

源码：[`src/chronaxis/sources/models.py:291`](../../../src/chronaxis/sources/models.py#L291)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalSeries"></a>
## `SignalSeries`

保存一批中的单个信号列及每个样本的来源身份。

time_ns、values、valid、quality和sequence都是等长一维数组，形状为(N,)。
time_ns与sequence使用int64，时间单位为纳秒；时间非递减，序号非负且列内唯一。
valid明确值是否有效，quality保存原因；不能凭values中的占位判断有效性。
name、dtype和unit说明别名、逻辑类型及输出单位；枚举用整数码和labels表示。
source_ref与可选original_values均与样本等长，保留位置及原始诊断。

构造时复制数组并设为只读，调用者修改原数组不影响本列。
本类不折叠同时间冲突，也不执行valid_for保持或过期判断；这些属于后续时间驱动。

```python
class SignalSeries
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|简单表达式别名。|
|`dtype`|[SignalDType](chronaxis.core.types.md#api-SignalDType)|是|无|SignalDType枚举成员：INT64是有符号64位整数，UINT64是无符号64位整数，FLOAT64是双精度浮点，BOOL是真/假，ENUM是预先声明的状态标签。这里传枚举成员，不传字符串；当前运算支持哪些类型仍见本对象的约束。|
|`unit`|str|是|无|已显式归一化输出单位。|
|`time_ns`|np.ndarray|是|无|shape(N,), int64，当前会话分析坐标ns。|
|`values`|np.ndarray|是|无|shape(N,), 精确dtype。|
|`valid`|np.ndarray|是|无|shape(N,), bool，不能单用值占位判断。|
|`quality`|np.ndarray|是|无|shape(N,), uint16九位原因。|
|`sequence`|np.ndarray|是|无|shape(N,), int64，原来源稳定非负序号。|
|`source_ref`|tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|每行实际来源/字段/会话。|
|`labels`|tuple[str, ...]|否|()|enum固定域，其他类型为空。|
|`original_values`|tuple[int &#124; float &#124; bool &#124; str &#124; None, ...] &#124; None|否|None|原无效诊断可保留。 None表示未附加原始诊断值列，仍保留标准值列的质量标记。|
|`code`|[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray) &#124; None|否|None|请求 enum_code 时携带同坐标整数原码。|

源码：[`src/chronaxis/sources/models.py:325`](../../../src/chronaxis/sources/models.py#L325)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalSeries-__post_init__"></a>
### `SignalSeries.__post_init__`

检查单列布局、有效性和样本身份，再复制为只读数组。

```python
SignalSeries.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。读取信号描述、五个数组、source_ref、labels和original_values。

#### 返回说明

None。时间、序号及数值数组成为本模型独立拥有的只读数据。

#### 异常说明

TypeError或ValueError: 名称、数组形状或类型、质量、时间顺序、序号、
        来源引用或原始诊断不符合要求；不通过广播或隐式转换修正。

#### 副作用说明

分配数组副本，不修改调用者输入。无效原浮点可保留在诊断中。

返回类型：None。

源码：[`src/chronaxis/sources/models.py:351`](../../../src/chronaxis/sources/models.py#L351)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalSeries-nbytes"></a>
### `SignalSeries.nbytes`

统计本列五个数组的存储字节数。

```python
SignalSeries.nbytes: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。读取time_ns、values、valid、quality和sequence的nbytes。

#### 返回说明

int。数组字节总和；不含枚举标签、来源引用、原诊断或其他Python容器。

#### 异常说明

无主动异常；数组结构已在构造时检查。

返回类型：int。

源码：[`src/chronaxis/sources/models.py:412`](../../../src/chronaxis/sources/models.py#L412)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalBatch"></a>
## `SignalBatch`

传送一个来源在当前会话中的异步信号列和读取进度。

source与session_id确定归属，series按输出别名保存列，允许零列。
watermark_ns是进度承诺：后续不会再出现小于或等于该坐标的更新。
它可以落后于当前尚未完整的时间组，不能当作实际观测终点。
source_eof只表示整个配置来源耗尽；observed_end_ns保存观测终点事实，
未知时保留None。单批结构检查不替代BatchValidator的跨批校验。

```python
class SignalBatch
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|已解码来源名称。|
|`session_id`|str|是|无|本次读取的明确会话。|
|`series`|Mapping[str, [SignalSeries](chronaxis.sources.models.md#api-SignalSeries)]|是|无|输出别名到真实列，允许零列。|
|`watermark_ns`|int &#124; None|是|无|已完整的时间组进度，否则None。|
|`source_eof`|bool|是|无|整个来源终点，不能仅单文件EOF。|
|`observed_end_ns`|int &#124; None|是|无|观测未知保留None，不补周期。|

源码：[`src/chronaxis/sources/models.py:428`](../../../src/chronaxis/sources/models.py#L428)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalBatch-__post_init__"></a>
### `SignalBatch.__post_init__`

检查批次归属、列名称和观测终点，不可修改的数据列映射。

```python
SignalBatch.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。读取来源、会话、series、watermark_ns、source_eof和observed_end_ns。

#### 返回说明

None。series成为新只读映射，列数组保持已有独立所有权。

#### 异常说明

TypeError或ValueError: 映射或结束标记类型、别名、样本归属或观测边界错误。
    OverflowError: 已知时间坐标超出整数纳秒范围。

返回类型：None。

源码：[`src/chronaxis/sources/models.py:445`](../../../src/chronaxis/sources/models.py#L445)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalBatch-sample_count"></a>
### `SignalBatch.sample_count`

按所有列的样本数总和计算本批大小。

```python
SignalBatch.sample_count: int
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。读取series中各列的长度。

#### 返回说明

int。空批为0；同一时间的多个信号分别计数，用于核对batch_rows上限。

#### 异常说明

无主动异常；列结构已在构造时检查。

返回类型：int。

源码：[`src/chronaxis/sources/models.py:488`](../../../src/chronaxis/sources/models.py#L488)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
