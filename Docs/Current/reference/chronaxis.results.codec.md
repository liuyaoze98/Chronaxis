# `chronaxis.results.codec`

编码和严格解码当前扁平结果JSONL；内部叶子格式另用于历史和导出。

公开结果只登记当前行类型和编号。内部_pack/_unpack保留整数、tuple、枚举、
来源与非有限诊断标记；它们不提供旧结果包装或公开v1—v6读取。
最大行字节与递归深度显式限制；调用方须先预留编码与解析临时空间。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANSourceRef](chronaxis.sources.can_spec.md#api-CANSourceRef)、[CANTextSourceRef](chronaxis.sources.text_can_ref.md#api-CANTextSourceRef)、[CSVSourceRef](chronaxis.sources.csv_spec.md#api-CSVSourceRef)、[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationResult](chronaxis.core.calculations.md#api-CalculationResult)、[Event](chronaxis.core.temporal.md#api-Event)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[Segment](chronaxis.core.windows.md#api-Segment)、[SelectionRow](chronaxis.core.selection.md#api-SelectionRow)、[SequenceResult](chronaxis.core.sequence.md#api-SequenceResult)、[SequenceRule](chronaxis.core.sequence.md#api-SequenceRule)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow)、[TemporalRule](chronaxis.core.temporal.md#api-TemporalRule)、[Truth](chronaxis.core.types.md#api-Truth)、[WindowSpec](chronaxis.core.windows.md#api-WindowSpec)

## 对象导航

|对象|用途|
|---|---|
|[`_pack`](#api-_pack)|递归编码固定模型、枚举、tuple和原生标量。|
|[`_unpack`](#api-_unpack)|只从已登记标签重建冻结对象。|
|[`_unique_object`](#api-_unique_object)|拒绝重复JSON键，避免解析时后值覆盖前值。|
|[`_reject_constant`](#api-_reject_constant)|拒绝非标准JSON NaN/Infinity，诊断只能使用明确标签。|
|[`estimate_row_bytes`](#api-estimate_row_bytes)|保守估计结果树、JSON转换与编码期间的新层RAM开销。|
|[`_estimate`](#api-_estimate)|累计原生对象及字段容器成本，重复引用也保守重复计数。|
|[`encode_row`](#api-encode_row)|生成一条确定JSONL，包含行结束符且限制字节数。|
|[`decode_row`](#api-decode_row)|从单行版本化JSONL恢复并重新校验所有模型。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import fields
from enum import Enum
from math import isfinite
from sys import getsizeof
from ..core.models import Interval, SourceRef
from ..core.numeric import ScalarValue
from ..core.calculations import CalculationResult, CalculationDefinition
from ..core.selection import SelectionRow
from ..core.temporal import Event, TemporalRule
from ..core.sequence import SequenceRule, SequenceResult
from ..core.windows import Segment, WindowSpec
from ..core.types import QualityFlag, SignalDType, Truth
from ..sources.csv_spec import CSVSourceRef
from ..sources.can_spec import CANSourceRef
from ..sources.text_can_ref import CANTextSourceRef
from .rows import ResultRow, row_table
from .errors import ResultFormatError
from .summary import SummaryCalculationRow, SUMMARY_FIELDS, summary_fields, SUMMARY_MODELS
```

</details>

<a id="api-_pack"></a>
## `_pack`

递归编码固定模型、枚举、tuple和原生标量。

```python
_pack(value, depth: int=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。已登记结果模型、枚举、元组或原生标量组成的树；编码时保留模型和枚举类型标签。|
|`depth`|int|否|0|位置或关键字。当前递归层数。顶层为0，每进入一个嵌套对象增加1，用于限制过深的数据结构。|

### 返回说明

仅JSON结构的树。

### 异常说明

ResultFormatError表示类型或深度不受支持。

本函数直接报告的具体错误：

- `ResultFormatError`：结果行嵌套超过32层。

源码：[`src/chronaxis/results/codec.py:35`](../../../src/chronaxis/results/codec.py#L35)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_unpack"></a>
## `_unpack`

只从已登记标签重建冻结对象。

```python
_unpack(value, depth: int=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JSON值|是|无|位置或关键字。已经解析的结果JSON树；依据类型标签恢复登记模型，遇到未知标签报错。|
|`depth`|int|否|0|位置或关键字。当前递归层数。顶层为0，每进入一个嵌套对象增加1，用于限制过深的数据结构。|

### 返回说明

带有明确类型的值。

### 异常说明

ResultFormatError/TypeError/ValueError为结构或模型校验错误。

本函数直接报告的具体错误：

- `ResultFormatError`：未知或多余结果类型标签。
- `ResultFormatError`：结果行嵌套超过32层。
- `ResultFormatError`：非有限结果必须使用诊断标签。
- `ResultFormatError`：结果结构需要明确类型标签。
- `ResultFormatError`：枚举底层值类型错误。
- `ResultFormatError`：结果模型字段缺失或出现未知字段。

源码：[`src/chronaxis/results/codec.py:75`](../../../src/chronaxis/results/codec.py#L75)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_unique_object"></a>
## `_unique_object`

拒绝重复JSON键，避免解析时后值覆盖前值。

```python
_unique_object(pairs)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pairs`|list[tuple[str, object]]|是|无|位置或关键字。JSON解析器按原顺序提供的键值对；先检查是否有重复键，再建立字典，避免同名项被静默覆盖。|

### 返回说明

dict。

### 异常说明

ResultFormatError为重复字段。

源码：[`src/chronaxis/results/codec.py:124`](../../../src/chronaxis/results/codec.py#L124)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_reject_constant"></a>
## `_reject_constant`

拒绝非标准JSON NaN/Infinity，诊断只能使用明确标签。

```python
_reject_constant(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。解析器发现的NaN或Infinity常量文本；拒绝这些非标准JSON常量。|

### 返回说明

无。

### 异常说明

ResultFormatError始终抛出。

源码：[`src/chronaxis/results/codec.py:151`](../../../src/chronaxis/results/codec.py#L151)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-estimate_row_bytes"></a>
## `estimate_row_bytes`

保守估计结果树、JSON转换与编码期间的新层RAM开销。

```python
estimate_row_bytes(row: ResultRow) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|ResultRow|是|无|位置或关键字。row为冻结行。|

### 返回说明

正整数bytes估算，含容器/标签和字符串转义余量。

### 异常说明

ResultFormatError为未登记类型或过深结构；不测量全进程RSS。

返回类型：int。

源码：[`src/chronaxis/results/codec.py:160`](../../../src/chronaxis/results/codec.py#L160)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_estimate"></a>
## `_estimate`

累计原生对象及字段容器成本，重复引用也保守重复计数。

```python
_estimate(value, depth: int=0) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。已登记结果模型及其字段组成的树；递归估算完整编码所需字节数。|
|`depth`|int|否|0|位置或关键字。当前估算过程的递归层数。顶层为0，进入嵌套对象后增加1。|

### 返回说明

基础bytes估算。

### 异常说明

ResultFormatError为类型/深度不支持。

本函数直接报告的具体错误：

- `ResultFormatError`：不能估算未登记结果对象。
- `ResultFormatError`：结果行嵌套超过32层。

返回类型：int。

源码：[`src/chronaxis/results/codec.py:173`](../../../src/chronaxis/results/codec.py#L173)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-encode_row"></a>
## `encode_row`

生成一条确定JSONL，包含行结束符且限制字节数。

```python
encode_row(row: ResultRow, max_bytes: int) -> bytes
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|ResultRow|是|无|位置或关键字。row为带有明确类型的行|
|`max_bytes`|int|是|无|位置或关键字。max_bytes为正原生int。|

### 返回说明

UTF-8 bytes，整数不经过浮点数转换。

### 异常说明

ResultFormatError/ValueError为类型、大小或格式错误。

本函数直接报告的具体错误：

- `ValueError`：max_bytes需正原生int。
- `ResultFormatError`：结果行超过max_bytes。

返回类型：bytes。

源码：[`src/chronaxis/results/codec.py:197`](../../../src/chronaxis/results/codec.py#L197)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-decode_row"></a>
## `decode_row`

从单行版本化JSONL恢复并重新校验所有模型。

```python
decode_row(payload: bytes, max_bytes: int) -> ResultRow
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。payload为UTF-8 bytes|
|`max_bytes`|int|是|无|位置或关键字。max_bytes为正原生int。|

### 返回说明

当前登记的平坦结果行；旧版本1—6不再读取。

### 异常说明

ResultFormatError为解析/版本/模型错误，ValueError为限额配置错误。

本函数直接报告的具体错误：

- `ValueError`：max_bytes需正原生int。
- `ResultFormatError`：结果行类型或字节限额错误。
- `ResultFormatError`：结果行外层字段错误。
- `ResultFormatError`：不支持的结果行版本。
- `ResultFormatError`：v2/v3仅接受独立legacy结果根。
- `ResultFormatError`：结果行版本与实际分桶事实不符。
- `ResultFormatError`：v4仅接受直接legacy汇总根。
- `ResultFormatError`：v5仅接受直接legacy汇总根。

返回类型：ResultRow。

源码：[`src/chronaxis/results/codec.py:220`](../../../src/chronaxis/results/codec.py#L220)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
