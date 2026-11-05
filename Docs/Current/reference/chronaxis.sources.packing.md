# `chronaxis.sources.packing`

把一批已解码标量归一化为可传送的独立信号列。

输入是一个SignalDefinition、整数纳秒时间、原行序号及原值记录，另有
当前来源引用和后端选择。输出SignalSeries包含数值、有效性掩码、质量原因、
时间、序号和逐样本来源；原始值另存为诊断，不依靠无效值占位判断有效性。

reference逐样本调用独立标量归一化函数。numpy先按最多五种原生类型
组织同质数组，再批量归一化，最后按索引放回原输入位置。
分组循环负责布局和身份，不使用object数组进行数值计算。
pack_message_values只返回没有时间轴的NumericArray，供固定周期逐消息累计；
它不构造虚假时间、原序号或来源列。两个入口共享布局及归一化选择，保留
reference与NumPy数值实现独立。输出复制为自身拥有的只读数组；
本模块不读取文件或调用旧解码路径。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SignalSeries](chronaxis.sources.models.md#api-SignalSeries)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`_pack_numeric_columns`](#api-_pack_numeric_columns)|把原值批次归一化为数值、有效性、质量及枚举标签，不建立时间轴。|
|[`pack_message_values`](#api-pack_message_values)|归一化逐消息原值，供无需时间轴的固定周期累计复用现有数值核。|
|[`pack_decoded`](#api-pack_decoded)|归一化当前有限批次，保留同时间的不同观测及原始诊断。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.binding import SignalDefinition
from ..core.models import SourceRef
from ..core.numeric import normalize_reference
from ..core.numeric_numpy import DTYPES, NumericArray
from ..core.normalize_numpy import normalize_numpy
from ..core.types import QualityFlag, SignalDType
from ..core.validation import require_scalar
from .models import SignalSeries
```

</details>

<a id="api-_pack_numeric_columns"></a>
## `_pack_numeric_columns`

把原值批次归一化为数值、有效性、质量及枚举标签，不建立时间轴。

```python
_pack_numeric_columns(definition: SignalDefinition, originals: tuple, backend: str) -> tuple
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。当前别名的输出类型、单位及显式转换。|
|`originals`|tuple|是|无|位置或关键字。原生标量或None的有限批次，位置保持输入顺序。|
|`backend`|str|是|无|位置或关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|

### 返回说明

tuple: values、valid、quality三个可写独立数组及labels枚举域；
    数组形状为(N,)，后续输出模型负责复制冻结，无效占位不能当正常值。

### 异常说明

TypeError或ValueError: 原值不合法；调用者已校验声明、tuple与后端。
    OverflowError或MemoryError: 数值转换或批次数组分配失败。

### 副作用说明

分配批次数组，不修改输入原值；不读取时间、来源或原序号。

返回类型：tuple。

源码：[`src/chronaxis/sources/packing.py:36`](../../../src/chronaxis/sources/packing.py#L36)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-pack_message_values"></a>
## `pack_message_values`

归一化逐消息原值，供无需时间轴的固定周期累计复用现有数值核。

```python
pack_message_values(definition: SignalDefinition, originals: tuple, backend: str) -> NumericArray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。别名的显式dtype、单位与转换规则。|
|`originals`|tuple|是|无|位置或关键字。原生不可变标量或None，顺序为实际求值顺序。|
|`backend`|str|是|无|位置或关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|

### 返回说明

NumericArray: 形状(N,)的只读values、valid、quality以及固定枚举标签；
    空批次合法，不包含时间、来源、序号或虚假SignalSeries。

### 异常说明

TypeError或ValueError: 声明、后端、tuple或原值不合法。
    OverflowError或MemoryError: 转换或数组分配失败，原输入不变。

### 副作用说明

仅分配并冻结输出数组，不读写文件，不建立跨批缓存。

返回类型：[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)。

源码：[`src/chronaxis/sources/packing.py:108`](../../../src/chronaxis/sources/packing.py#L108)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-pack_decoded"></a>
## `pack_decoded`

归一化当前有限批次，保留同时间的不同观测及原始诊断。

```python
pack_decoded(definition: SignalDefinition, records: tuple[tuple[int, int, int | float | bool | str | None], ...], source_ref: SourceRef | tuple[SourceRef, ...], backend: str, *, retain_original=True, clock_only=False) -> SignalSeries
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definition`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。当前别名的输出类型、单位及显式转换。|
|`records`|tuple[tuple[int, int, int &#124; float &#124; bool &#124; str &#124; None], ...]|是|无|位置或关键字。每项为(time_ns, sequence, 原值)，时间为纳秒。|
|`source_ref`|[SourceRef](chronaxis.core.models.md#api-SourceRef) &#124; tuple[[SourceRef](chronaxis.core.models.md#api-SourceRef), ...]|是|无|位置或关键字。共用引用或等长逐样本引用。|
|`backend`|str|是|无|位置或关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。须明确选择一种。|
|`retain_original`|bool|否|True|仅关键字。是否保留解析前原始文本；关闭时仍解析并检查输入，只是不保存原文副本。|
|`clock_only`|tuple[str, ...]|否|False|仅关键字。仅作为时间驱动的信号别名集合；保留真实更新时刻，不解析或构造该信号的数值样本。|

### 返回说明

SignalSeries: (N,)数值、有效性、质量、时间、序号及逐样本来源；
    原值仅在请求时保留，空批保留声明的类型与枚举域。

### 异常说明

TypeError或ValueError: 输入结构、后端、原值、列布局或身份不合法。
    OverflowError或MemoryError: 转换、时间装箱或批次数组分配失败。

### 副作用说明

分配独立只读批次，不修改输入；有效期保持由后续时间驱动层执行。

返回类型：[SignalSeries](chronaxis.sources.models.md#api-SignalSeries)。

源码：[`src/chronaxis/sources/packing.py:133`](../../../src/chronaxis/sources/packing.py#L133)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
