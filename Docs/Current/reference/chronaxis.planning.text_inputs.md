# chronaxis.planning.text_inputs

把ASC或原始报文CSV来源配置转换成读取规格，明确文件顺序、时间格式、偏移和DBC通道；不会自动猜日期或格式。见[文本输入](../text-inputs.md)。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ASCSpec](chronaxis.sources.asc.md#api-ASCSpec)、[BLFSpec](chronaxis.sources.blf.md#api-BLFSpec)、[CANCSVLayout](chronaxis.sources.raw_csv_layout.md#api-CANCSVLayout)、[CANCSVSpec](chronaxis.sources.raw_csv.md#api-CANCSVSpec)、[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[CSVTimeSpec](chronaxis.sources.raw_csv.md#api-CSVTimeSpec)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)、[SourcePlan](chronaxis.planning.models.md#api-SourcePlan)、[TimeType](chronaxis.core.types.md#api-TimeType)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

## 对象导航

|对象|用途|
|---|---|
|[`parse_text_source`](#api-parse_text_source)|建立一个明确的新文本CAN来源。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from ..core.models import TimebaseSpec
from ..core.types import TimeType
from ..sources.asc import ASCSpec
from ..sources.blf import BLFSpec
from ..sources.raw_csv import CANCSVSpec, CSVTimeSpec
from ..sources.raw_csv_layout import CANCSVLayout
from ..sources.text_can_spec import CANTextSpec
from ..timebase.conversion import checked_add_ns
from .checks import PlanValidationError, absolute_path, array_at, canonical, choice_at, coordinate_at, duration_at, metadata_at, model_at, object_at, text_at, timezone_at
```

</details>

<a id="api-parse_text_source"></a>
## `parse_text_source`

建立一个明确的新文本CAN来源。

```python
parse_text_source(raw, base, path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict[str, object]|是|无|位置或关键字。原始can_asc或raw_can_csv来源配置，字段说明见[文本CAN输入](../text-inputs.md)。|
|`base`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。当前配置文件所在目录，来源中的相对路径以此为基准。|
|`path`|str|是|无|位置或关键字。来源对象在JSON中的位置，用于错误提示，例如$.sources[0]。|

### 返回说明

SourcePlan。

### 异常说明

PlanValidationError定位配置问题；不发生原始输入I/O。

源码：[`src/chronaxis/planning/text_inputs.py:22`](../../../src/chronaxis/planning/text_inputs.py#L22)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
