# `chronaxis.sources.descriptions`

把显式信号定义转成来源的静态字段描述。

输入是来源名称、SignalDefinition元组和可选定位信息，输出FieldDescription
元组。每项保留表达式别名、原字段、输出类型与单位，并保存转换、有效期、
可选语义、方向、测量位置和枚举标签。内存来源与已解码CSV共用该转换。
本模块不读取输入文件或DBC，也不核实声明是否与实际表头或物理测量一致。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[FieldDescription](chronaxis.sources.models.md#api-FieldDescription)、[FieldLocation](chronaxis.sources.models.md#api-FieldLocation)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

## 对象导航

|对象|用途|
|---|---|
|[`source_timebase_identity`](#api-source_timebase_identity)|为实际适配器使用的时基种类/原点/固定偏移生成独立摘要。|
|[`describe_fields`](#api-describe_fields)|逐项保存字段定位和转换声明，不把声明当作实际数据核实。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from hashlib import sha256
from ..core.binding import SignalDefinition, _identity
from ..core.models import TimebaseSpec
from ..timebase.conversion import require_int64_ns
from ..core.types import SignalDType
from .models import FieldDescription, FieldLocation, JsonValue
```

</details>

<a id="api-source_timebase_identity"></a>
## `source_timebase_identity`

为实际适配器使用的时基种类/原点/固定偏移生成独立摘要。

```python
source_timebase_identity(timebase: TimebaseSpec, offset_ns: int) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|位置或关键字。timebase已校验TimebaseSpec|
|`offset_ns`|int|是|无|位置或关键字。offset_ns为整数纳秒偏移。|

### 返回说明

SHA256文本，仅标识配置，不证明物理时钟同步已核实。

### 异常说明

TypeError/OverflowError为未声明时基或非法偏移；不读取输入。

本函数直接报告的具体错误：

- `TypeError`：时基身份需要TimebaseSpec。

返回类型：str。

源码：[`src/chronaxis/sources/descriptions.py:23`](../../../src/chronaxis/sources/descriptions.py#L23)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-describe_fields"></a>
## `describe_fields`

逐项保存字段定位和转换声明，不把声明当作实际数据核实。

```python
describe_fields(source: str, signals: tuple[SignalDefinition, ...], locator: Mapping[str, JsonValue] | None=None) -> tuple[FieldDescription, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|位置或关键字。当前来源名称。|
|`signals`|tuple[[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。该来源已解析的显式信号定义。|
|`locator`|Mapping[str, JsonValue] &#124; None|否|None|位置或关键字。可附加的静态定位信息，默认None，使用空对象。|

### 返回说明

tuple[FieldDescription, ...]。保持定义顺序，元数据和定位映射深度冻结。
    valid_for_ns是有效值最多保持的时长声明；本函数不在此执行保持或过期判断。
    原始CAN的None表示等待同次DBC周期解析，不表示无限保持。

### 异常说明

TypeError或ValueError: 字段描述或定位信息不符合公共模型要求。

### 副作用说明

无输入扫描；同一原字段的多个别名分别保留自己的显式转换。

返回类型：tuple[[FieldDescription](chronaxis.sources.models.md#api-FieldDescription), ...]。

源码：[`src/chronaxis/sources/descriptions.py:38`](../../../src/chronaxis/sources/descriptions.py#L38)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
