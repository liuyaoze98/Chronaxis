# `chronaxis.planning.inputs`

检查来源和信号配置，建立静态定位与显式转换声明。

输入是当前配置的sources、signals数组和相对路径基准，输出SourcePlan
与SignalPlan元组。内存原行已在配置中，可核对原顺序和已出现字段；CSV
只保存有序路径和格式，不读取文件表头。时间使用明确单位、公共起点或时区，
原字段保持原文，整数值不先转浮点。valid_for声明有效值最多保持的时间，
省略时取本信号period或运行期DBC周期的三倍。
CAN支持既有单BLF profile与新ASC/原始CSV静态规格，完整原定位保存为规范字段键；
旧表格profile仍报告capability_unavailable。仅需补齐信号元数据时读取DBC，不读日志。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[DBCDefaults](chronaxis.planning.dbc_defaults.md#api-DBCDefaults)、[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)、[MemoryRow](chronaxis.core.models.md#api-MemoryRow)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)、[SignalPlan](chronaxis.planning.models.md#api-SignalPlan)、[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)、[SourceSpec](chronaxis.core.models.md#api-SourceSpec)、[TimeType](chronaxis.core.types.md#api-TimeType)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

## 对象导航

|对象|用途|
|---|---|
|[`parse_sources`](#api-parse_sources)|按声明顺序解析内存、已解码CSV或原始CAN规格，不读取分析文件。|
|[`parse_signals`](#api-parse_signals)|检查原字段到简单别名的转换与有效期声明。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from pathlib import Path
from ..core.binding import SignalDefinition
from ..core.unit_conversion import affine_conversion, converted_dtype, require_config_version
from ..core.models import MemoryRow, SourceSpec, TimebaseSpec
from ..core.types import SignalDType, TimeType
from ..sources.csv_spec import SignalCSVSpec
from ..sources.can_spec import LegacyCANSpec
from ..sources.text_can_spec import CANTextSpec
from ..legacy.records import PROFILE_ID, field_from_dict
from .diagnostic_collection import usable_node, collect_node_error
from .checks import PlanValidationError, absolute_path, array_at, canonical, choice_at, coordinate_at, duration_at, metadata_at, model_at, number_at, object_at, text_at, timezone_at
from .models import SignalPlan, SourcePlan
from .signal_validity import declared_valid_for
from .input_defaults import source_defaults, source_reference
from .input_paths import expand_source_files
from .dbc_defaults import DBCDefaults
```

</details>

<a id="api-parse_sources"></a>
## `parse_sources`

按声明顺序解析内存、已解码CSV或原始CAN规格，不读取分析文件。

```python
parse_sources(value, base: Path) -> tuple[SourcePlan, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list|是|无|位置或关键字。sources配置数组，每项含名称、来源种类和时间声明。|
|`base`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。相对CSV、BLF及DBC路径的词法解释基准。|

### 返回说明

tuple[SourcePlan, ...]。至少含一个来源；路径转为绝对定位并保留原顺序。
    内存原行按声明顺序构造，CSV/CAN仅构造配置，文件、表头及DBC尚未核实。

### 异常说明

PlanValidationError: 字段、格式、名称、时序、时间基准或来源能力错误，
        保存对应配置位置；未接入来源使用capability_unavailable错误码。

### 副作用说明

不打开CSV或DBC；地区时区解析可能访问本机时区数据库。

返回类型：tuple[[SourcePlan](chronaxis.planning.models.md#api-SourcePlan), ...]。

源码：[`src/chronaxis/planning/inputs.py:36`](../../../src/chronaxis/planning/inputs.py#L36)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-parse_signals"></a>
## `parse_signals`

检查原字段到简单别名的转换与有效期声明。

```python
parse_signals(value, sources: tuple[SourcePlan, ...], *, config_version: int=4, enum_codes=()) -> tuple[SignalPlan, ...]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list|是|无|位置或关键字。signals配置数组，显式声明来源、原字段、类型、单位和valid_for。|
|`sources`|tuple[[SourcePlan](chronaxis.planning.models.md#api-SourcePlan), ...]|是|无|位置或关键字。当前计划已经解析的来源。|
|`config_version`|int|否|4|仅关键字。当前仅支持4；只在两个系数都缺省时自动推导。|
|`enum_codes`|tuple|否|()|仅关键字。被 enum_code 明确引用的枚举别名；普通标签比较不需要原码。|

### 返回说明

tuple[SignalPlan, ...]。保持信号顺序，choices原编码类型保留，
    valid_for转为正整数纳秒；缺省且等待DBC时保存None，转换和可选语义按核心模型检查。

### 异常说明

PlanValidationError: 结构、来源、字段、类型、单位、有效期或转换契约错误。

### 边界说明

非空内存可检查字段；CSV/CAN日志不读。缺省CAN元数据只读取DBC。
    本函数保存有效期声明，不保持信号值或执行过期判断。

返回类型：tuple[[SignalPlan](chronaxis.planning.models.md#api-SignalPlan), ...]。

源码：[`src/chronaxis/planning/inputs.py:218`](../../../src/chronaxis/planning/inputs.py#L218)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
