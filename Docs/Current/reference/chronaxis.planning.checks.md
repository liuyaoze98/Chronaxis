# `chronaxis.planning.checks`

检查JSON/YAML解析后的配置值，并在错误中保存具体字段位置。

输入为原生字典、列表、标量及JSON路径，输出合法原值、冻结元数据、
时间坐标或模型实例；错误统一关联为PlanValidationError。
字段和类型严格检查，不把True当整数，不忽略未知键或自动纠正数值。
时间必须声明单位或时区，路径只转为绝对定位，不检查文件内容或存在性。
本模块不读日志或DBC；地区时区解析可能读取系统时区数据库。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`PlanValidationError`](#api-PlanValidationError)|保存配置字段路径、原因和可选原文定位。diagnostics提供全部独立错误，单错也为一项；blocked_checks列出因上游声明无效而尚未执行的检查，其元素含path和reason，不是额外确认错误。|
|[`PlanValidationError.__init__`](#api-PlanValidationError-__init__)|建立明确路径错误，保留原异常链供load_analysis_plan诊断。|
|[`PlanValidationError.refresh_text`](#api-PlanValidationError-refresh_text)|重建人读消息。|
|[`PlanValidationError.to_dict`](#api-PlanValidationError-to_dict)|返回稳定机器诊断。|
|[`PlanValidationError.diagnostics`](#api-PlanValidationError-diagnostics)|返回各项独立诊断。|
|[`PlanValidationError.from_diagnostics`](#api-PlanValidationError-from_diagnostics)|合并错误并保留原类型兼容。|
|[`configuration_error`](#api-configuration_error)|把共享语法错误交给计划API的异常类型。|
|[`object_at`](#api-object_at)|检查JSON对象的类型、必填项和允许字段。|
|[`array_at`](#api-array_at)|要求明确JSON数组，不把文本或tuple当自由迭代器。|
|[`text_at`](#api-text_at)|检查非空文本或统一简单名称，保留原大小写。|
|[`choice_at`](#api-choice_at)|要求显式支持的原生类型值，禁止bool等价整数。|
|[`number_at`](#api-number_at)|检查有限原生数值及包含端点的范围，保留整数精度。|
|[`duration_at`](#api-duration_at)|把带单位的非负持续时间转为整数纳秒。|
|[`coordinate_at`](#api-coordinate_at)|解释带单位相对坐标或完整绝对日期，返回整数纳秒。|
|[`timezone_at`](#api-timezone_at)|解析显式UTC、固定offset或IANA名称，拒绝机器时区推断。|
|[`metadata_at`](#api-metadata_at)|深冻结唯一允许自由键的JSON元数据对象。|
|[`require_json_value`](#api-require_json_value)|在冻结之前检查原生JSON结构，并定位当前递归路径上的循环。|
|[`json_value`](#api-json_value)|将已深冻结JSON快照转回可序列化新结构。|
|[`canonical`](#api-canonical)|生成JSON配置的确定身份文本，不读取文件内容。|
|[`absolute_path`](#api-absolute_path)|相对于明确基准解释路径，不打开目标或核实存在性。|
|[`model_at`](#api-model_at)|用内部指定构造器创建模型，将校验错误关联到配置位置。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from datetime import timedelta, timezone
from math import isfinite
from pathlib import Path
from collections.abc import Mapping
from zoneinfo import ZoneInfo
from difflib import get_close_matches
from ..configuration.diagnostics import child_path, value_preview
from ..core.validation import require_identifier, require_text
from ..sources.models import freeze_metadata
from ..timebase import convert_time, parse_duration, parse_datetime_ns
```

</details>

<a id="api-PlanValidationError"></a>
## `PlanValidationError`

保存配置字段路径、原因和可选原文定位。diagnostics提供全部独立错误，单错也为一项；blocked_checks列出因上游声明无效而尚未执行的检查，其元素含path和reason，不是额外确认错误。

```python
PlanValidationError(path: str, message: str, code: str = 'invalid_config', *, hint=None, source=None, location=None, object_name=None, value=None)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/planning/checks.py:26`](../../../src/chronaxis/planning/checks.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PlanValidationError-__init__"></a>
### `PlanValidationError.__init__`

建立明确路径错误，保留原异常链供load_analysis_plan诊断。

```python
PlanValidationError.__init__(path: str, message: str, code: str='invalid_config', *, hint=None, source=None, location=None, object_name=None, value=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|位置或关键字。标识配置中的出错字段，例如$.signals[0].unit；由校验器根据实际声明位置生成。|
|`message`|str|是|无|位置或关键字。解释该字段违反的要求，例如需要正整数；用于面向用户的错误正文，不应包含完整私有输入数据。|
|`code`|str|否|'invalid_config'|位置或关键字。提供机器可识别的错误类别，默认invalid_config表示无效配置；读取异常时用code分类，不依赖中文message匹配。|
|`hint`|str 或 None|否|None|仅关键字。可选修正提示，例如有效枚举值或可用名称；提示不会自动修改原配置。|
|`source`|str 或 None|否|None|仅关键字。配置来源文件或显示名，与字段path分开；没有可靠来源时保留None。|
|`location`|ConfigurationLocation 或 None|否|None|仅关键字。可证明的原始行列；缺失时只给文件与字段，不猜位置。|
|`object_name`|str 或 None|否|None|仅关键字。错误所属的来源、信号或节点名称；只用于定位，不参与名称推断。|
|`value`|str 或 None|否|None|仅关键字。已截短的当前值说明，大容器仅显示类型与大小，避免打印整份配置。|

#### 返回说明

None；异常文本含路径和原因。

#### 异常说明

无；参数由校验器内部构造。

源码：[`src/chronaxis/planning/checks.py:32`](../../../src/chronaxis/planning/checks.py#L32)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PlanValidationError-refresh_text"></a>
### `PlanValidationError.refresh_text`

重建人读消息。

```python
PlanValidationError.refresh_text()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

无；附加定位后调用。

源码：[`src/chronaxis/planning/checks.py:58`](../../../src/chronaxis/planning/checks.py#L58)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PlanValidationError-to_dict"></a>
### `PlanValidationError.to_dict`

返回稳定机器诊断。

```python
PlanValidationError.to_dict()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

当前单项的原生dict；聚合异常的本方法只描述第一项。获取全部诊断时使用[item.to_dict() for item in error.diagnostics]。

#### 异常说明

无。

源码：[`src/chronaxis/planning/checks.py:78`](../../../src/chronaxis/planning/checks.py#L78)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PlanValidationError-diagnostics"></a>
### `PlanValidationError.diagnostics`

返回各项独立诊断。

```python
PlanValidationError.diagnostics
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple；单错也为一项。

#### 异常说明

无。

源码：[`src/chronaxis/planning/checks.py:86`](../../../src/chronaxis/planning/checks.py#L86)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PlanValidationError-from_diagnostics"></a>
### `PlanValidationError.from_diagnostics`

合并错误并保留原类型兼容。

```python
PlanValidationError.from_diagnostics(errors, blocked=())
```

装饰器：`classmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`errors`|Sequence[[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)]|是|无|位置或关键字。非空PlanValidationError序列；单项且没有阻断说明时原样返回。|
|`blocked`|Iterable[dict]|否|()|位置或关键字。可选阻断说明序列，每项是含path和reason的字典；默认空元组。|

#### 返回说明

异常。

#### 异常说明

空序列ValueError。

源码：[`src/chronaxis/planning/checks.py:91`](../../../src/chronaxis/planning/checks.py#L91)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-configuration_error"></a>
## `configuration_error`

把共享语法错误交给计划API的异常类型。

```python
configuration_error(error)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|配置异常实例|是|无|位置或关键字。需要补充来源位置的原异常，保留错误码及其原因链，不用新成功结果替代。|

### 返回说明

PlanValidationError。

维持文件路径与具体语法代码，文本补实际字段和可靠行列；不读取或重解析配置。

源码：[`src/chronaxis/planning/checks.py:105`](../../../src/chronaxis/planning/checks.py#L105)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-object_at"></a>
## `object_at`

检查JSON对象的类型、必填项和允许字段。

```python
object_at(value, path: str, required=(), optional=()) -> dict
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。待检查的JSON对象；必须是原生dict且键均为字符串，错误会带上当前JSON路径。|
|`path`|str|是|无|位置或关键字。当前配置位置。|
|`required`|tuple|否|()|位置或关键字。必填键，默认空元组。|
|`optional`|tuple|否|()|位置或关键字。可选键，默认空元组。|

### 返回说明

dict。原字典只在解析中读取，独立快照由计划入口另行创建。

### 异常说明

PlanValidationError: 对象类型错误、缺少必填项或含未知键。

返回类型：dict。

源码：[`src/chronaxis/planning/checks.py:121`](../../../src/chronaxis/planning/checks.py#L121)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-array_at"></a>
## `array_at`

要求明确JSON数组，不把文本或tuple当自由迭代器。

```python
array_at(value, path: str) -> list
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list|是|无|位置或关键字。待检查的JSON数组；tuple等Python容器不作为配置数组接受。|
|`path`|str|是|无|位置或关键字。path位置。|

### 返回说明

原list，仅解析期间读取。

### 异常说明

PlanValidationError为类型错误。

返回类型：list。

源码：[`src/chronaxis/planning/checks.py:157`](../../../src/chronaxis/planning/checks.py#L157)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-text_at"></a>
## `text_at`

检查非空文本或统一简单名称，保留原大小写。

```python
text_at(value, path: str, *, identifier=False) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。待检查的配置文本；是否可为空由此入口的参数决定，不自动把数值转成文本。|
|`path`|str|是|无|位置或关键字。path位置|
|`identifier`|bool|否|False|仅关键字。identifier是否安全标识符。|

### 返回说明

原str，不改点号字段或semantic字符串。

### 异常说明

PlanValidationError为类型/名称错误。

返回类型：str。

源码：[`src/chronaxis/planning/checks.py:172`](../../../src/chronaxis/planning/checks.py#L172)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-choice_at"></a>
## `choice_at`

要求显式支持的原生类型值，禁止bool等价整数。

```python
choice_at(value, choices: tuple, path: str)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。待检查的选项字符串；必须与choices中的一个完整选项相同，区分大小写。|
|`choices`|tuple|是|无|位置或关键字。choices允许值tuple|
|`path`|str|是|无|位置或关键字。path位置。|

### 返回说明

原值。

### 异常说明

PlanValidationError为未知值/类型。

源码：[`src/chronaxis/planning/checks.py:189`](../../../src/chronaxis/planning/checks.py#L189)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-number_at"></a>
## `number_at`

检查有限原生数值及包含端点的范围，保留整数精度。

```python
number_at(value, path: str, *, integer=False, minimum=None, maximum=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。待检查的有限数值；bool、NaN和无穷值不作为正常数字接受。|
|`path`|str|是|无|位置或关键字。当前配置位置。|
|`integer`|bool|否|False|仅关键字。默认False；True时只接受原生int。|
|`minimum`|int &#124; float &#124; None|否|None|仅关键字。包含端点的下限；None表示不限制下端。|
|`maximum`|int &#124; float &#124; None|否|None|仅关键字。包含端点的上限；None表示不限制上端。|

### 返回说明

int或float。保持原类型和位值，不截断或转成浮点。

### 异常说明

PlanValidationError: 类型错误、非有限浮点或超出范围。

源码：[`src/chronaxis/planning/checks.py:205`](../../../src/chronaxis/planning/checks.py#L205)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-duration_at"></a>
## `duration_at`

把带单位的非负持续时间转为整数纳秒。

```python
duration_at(value, path: str, *, positive=False) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。明确带时间单位的持续文本，不接受裸数。|
|`path`|str|是|无|位置或关键字。当前配置位置。|
|`positive`|bool|否|False|仅关键字。默认False；True时要求纳秒量化后仍大于0。|

### 返回说明

int。符合int64范围的纳秒时长，允许零时长时返回0。

### 异常说明

PlanValidationError: 语法、单位、范围错误，或正时长量化后为0。

返回类型：int。

源码：[`src/chronaxis/planning/checks.py:231`](../../../src/chronaxis/planning/checks.py#L231)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-coordinate_at"></a>
## `coordinate_at`

解释带单位相对坐标或完整绝对日期，返回整数纳秒。

```python
coordinate_at(value, path: str, *, absolute=False, tz=None) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。相对数值加s、ms、us或ns单位，或完整绝对日期文本。|
|`path`|str|是|无|位置或关键字。当前配置位置。|
|`absolute`|bool|否|False|仅关键字。默认False；True时按绝对日期解析。|
|`tz`|tzinfo &#124; None|否|None|仅关键字。默认None；绝对日期没有自身时区时使用此声明。|

### 返回说明

int。int64纳秒坐标；相对坐标允许负数，区别于非负持续时间。

### 异常说明

PlanValidationError: 文本、单位、时区、日期或数值范围错误。

本函数直接报告的具体错误：

- `ValueError`：坐标须为数值+s/ms/us/ns。

返回类型：int。

源码：[`src/chronaxis/planning/checks.py:259`](../../../src/chronaxis/planning/checks.py#L259)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-timezone_at"></a>
## `timezone_at`

解析显式UTC、固定offset或IANA名称，拒绝机器时区推断。

```python
timezone_at(value, path: str)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str &#124; None|是|无|位置或关键字。时区文字或None；例如"UTC"、"+08:00"，None表示没有显式时区声明。|
|`path`|str|是|无|位置或关键字。path位置。|

### 返回说明

tzinfo或None，仅IANA可能读取系统时区数据库，不读数据输入。

### 异常说明

PlanValidationError为非法offset/未知时区或依赖缺失。

源码：[`src/chronaxis/planning/checks.py:294`](../../../src/chronaxis/planning/checks.py#L294)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-metadata_at"></a>
## `metadata_at`

深冻结唯一允许自由键的JSON元数据对象。

```python
metadata_at(value, path: str)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。用户提供的JSON元数据对象，递归检查其键、值和有限数值后冻结保存。|
|`path`|str|是|无|位置或关键字。path位置。|

### 返回说明

深复制的只读Mapping/tuple，不影响调用者输入。

### 异常说明

PlanValidationError为非JSON/非有限/键类型错误。

源码：[`src/chronaxis/planning/checks.py:333`](../../../src/chronaxis/planning/checks.py#L333)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-require_json_value"></a>
## `require_json_value`

在冻结之前检查原生JSON结构，并定位当前递归路径上的循环。

```python
require_json_value(value, path: str, active=None) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JSON值|是|无|位置或关键字。dict、list或原生str、int、float、bool、None组成的树；float必须有限，不接受自定义实例。|
|`path`|str|是|无|位置或关键字。当前配置位置，递归时补字段名或数组下标。|
|`active`|set[int] &#124; None|否|None|位置或关键字。当前祖先容器身份；根调用省略。|

### 返回说明

None，结构合法；不复制、转换或修改输入。

### 异常说明

PlanValidationError: 非JSON对象、非文本对象键、非有限浮点或循环容器。

### 处理流程说明

先区分原生容器与标量，逐层检查后由调用者冻结；共享但不循环的
    容器允许重复出现。此检查不打开文件或执行任意Mapping方法。

返回类型：None。

源码：[`src/chronaxis/planning/checks.py:354`](../../../src/chronaxis/planning/checks.py#L354)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-json_value"></a>
## `json_value`

将已深冻结JSON快照转回可序列化新结构。

```python
json_value(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|冻结JSON值|是|无|位置或关键字。freeze_metadata产生的只读映射、元组及原生标量；转换回可输出JSON的dict和list。|

### 返回说明

新dict/list或原不可变标量。

### 异常说明

无；调用者保证已校验JSON类型。

源码：[`src/chronaxis/planning/checks.py:400`](../../../src/chronaxis/planning/checks.py#L400)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-canonical"></a>
## `canonical`

生成JSON配置的确定身份文本，不读取文件内容。

```python
canonical(value) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JSON值 &#124; 冻结JSON值|是|无|位置或关键字。已经校验的配置树，按固定键顺序编码，供计算配置身份摘要使用。|

### 返回说明

规范JSON文本，字典排序、数组原序、整数精度保持。

### 异常说明

TypeError/ValueError为内部非JSON结构。

返回类型：str。

源码：[`src/chronaxis/planning/checks.py:419`](../../../src/chronaxis/planning/checks.py#L419)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-absolute_path"></a>
## `absolute_path`

相对于明确基准解释路径，不打开目标或核实存在性。

```python
absolute_path(value, base: Path, path: str) -> Path
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。非空路径文本，不得含NUL字符。|
|`base`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。相对路径的解释基准。|
|`path`|str|是|无|位置或关键字。此字段在配置中的错误定位。|

### 返回说明

Path。绝对定位路径，不解析实际符号链接或读取文件内容。

### 异常说明

PlanValidationError: 路径文本非法或含NUL。
    OSError: 获取当前目录或系统路径转换发生错误时可传播。

返回类型：[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)。

源码：[`src/chronaxis/planning/checks.py:430`](../../../src/chronaxis/planning/checks.py#L430)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-model_at"></a>
## `model_at`

用内部指定构造器创建模型，将校验错误关联到配置位置。

```python
model_at(factory, path: str, *args, **kwargs)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`factory`|Callable|是|无|位置或关键字。程序指定的模型构造器或校验函数，例如SignalDefinition；不是配置中可填写的函数名称。|
|`path`|str|是|无|位置或关键字。当前配置位置。|
|`args`|tuple|否|()|可变位置。传给factory的位置实参，顺序与其签名一致。|
|`kwargs`|dict[str, object]|否|{}|可变关键字。传给factory的关键字实参；字段名和类型由对应模型定义。|

### 返回说明

构造器的实际返回值，通常是已检查的模型实例。

### 异常说明

PlanValidationError: 包装TypeError、ValueError、OverflowError或LookupError，
        保留原异常链；其他发生异常时直接交给调用者处理。

源码：[`src/chronaxis/planning/checks.py:453`](../../../src/chronaxis/planning/checks.py#L453)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
