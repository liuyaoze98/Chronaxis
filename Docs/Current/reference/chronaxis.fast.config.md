# `chronaxis.fast.config`

把独立原始报文配置编译成每文件任务，共用 Chronaxis 的单位、类型与来源位置规则。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ASCSpec](chronaxis.sources.asc.md#api-ASCSpec)、[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[ConfigurationError](chronaxis.configuration.models.md#api-ConfigurationError)、[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`_unsupported`](#api-_unsupported)|构造可由已有配置诊断和 CLI 消费的错误。|
|[`_capabilities`](#api-_capabilities)|仅检查显式请求，避免把通用计划的默认设置误判为用户要求。|
|[`_source`](#api-_source)|取得唯一文件及其时钟参数，保持 ASC 与 BLF 各自的时间解释。|
|[`_flag`](#api-_flag)|合并同一公式中每个信号和选择器的身份限制；显式矛盾不可合并。|
|[`_metric`](#api-_metric)|静态验证本次请求的信号及原单位，将已检查的表达式树编码为简单数值指令。|
|[`_compile_plan`](#api-_compile_plan)|编译公共静态计划的独立文件任务，仅需加载本计划的 DBC 元数据。|
|[`compile_template_plan`](#api-compile_template_plan)|为 batch.template_jobs 展开的一个真实文件编译 fast 任务。|
|[`compile_config`](#api-compile_config)|读取配置和导入定义，验证 DBC 与 fast 子集。默认返回可序列化单文件任务。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import asdict
from pathlib import Path
from ..configuration import ConfigurationError, load_configuration
from ..configuration.diagnostics import locate_error
from ..configuration.imports import expand_document_imports
from ..legacy.binding import dbc_candidates
from ..planning.checks import PlanValidationError, configuration_error
from ..planning.dbc_defaults import load_dbc, scoped_dbc_cache
from ..planning.plan import AnalysisPlan
from ..sources.asc import ASCSpec
from ..sources.can_spec import LegacyCANSpec, can_field_from_key
from .compute import encode_program, prepare_metric
```

</details>

<a id="api-_unsupported"></a>
## `_unsupported`

构造可由已有配置诊断和 CLI 消费的错误。

```python
_unsupported(path, message)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|位置或关键字。不受支持设置的配置字段路径，如 $.outputs.contributions。|
|`message`|str|是|无|位置或关键字。当前字段为什么不能按 fast 方式执行的具体原因。|

源码：[`src/chronaxis/fast/config.py:17`](../../../src/chronaxis/fast/config.py#L17)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_capabilities"></a>
## `_capabilities`

仅检查显式请求，避免把通用计划的默认设置误判为用户要求。

```python
_capabilities(raw)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。显式声明的配置字段，在加默认值前检查 fast 能力限制。|

源码：[`src/chronaxis/fast/config.py:22`](../../../src/chronaxis/fast/config.py#L22)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_source"></a>
## `_source`

取得唯一文件及其时钟参数，保持 ASC 与 BLF 各自的时间解释。

```python
_source(plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。公开解析器构建的计划，含静态信号绑定及逐消息计算项。|

源码：[`src/chronaxis/fast/config.py:67`](../../../src/chronaxis/fast/config.py#L67)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_flag"></a>
## `_flag`

合并同一公式中每个信号和选择器的身份限制；显式矛盾不可合并。

```python
_flag(selector, fields, name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`selector`|MessageSelector|是|无|位置或关键字。逐消息触发报文的身份声明。|
|`fields`|Iterable|是|无|位置或关键字。本公式涉及的信号字段，用于与选择器合并帧型限制。|
|`name`|str|是|无|位置或关键字。要合并的帧型字段，取 is_extended 或 is_fd。|

源码：[`src/chronaxis/fast/config.py:95`](../../../src/chronaxis/fast/config.py#L95)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_metric"></a>
## `_metric`

静态验证本次请求的信号及原单位，将已检查的表达式树编码为简单数值指令。

```python
_metric(plan, item, database)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。公开解析器构建的计划，含静态信号绑定及逐消息计算项。|
|`item`|MessageCalculationPlan|是|无|位置或关键字。一个已解析的逐消息累计项，含选择器、公式和方向规则。|
|`database`|cantools.database.Database &#124; None|是|无|位置或关键字。预检时加载的 DBC，可交本次执行复用。|

源码：[`src/chronaxis/fast/config.py:103`](../../../src/chronaxis/fast/config.py#L103)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_compile_plan"></a>
## `_compile_plan`

编译公共静态计划的独立文件任务，仅需加载本计划的 DBC 元数据。

```python
_compile_plan(plan, with_database)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。公开解析器构建的计划，含静态信号绑定及逐消息计算项。|
|`with_database`|bool|是|无|位置或关键字。是否将已加载的数据库交给当前进程继续执行。|

源码：[`src/chronaxis/fast/config.py:146`](../../../src/chronaxis/fast/config.py#L146)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-compile_template_plan"></a>
## `compile_template_plan`

为 batch.template_jobs 展开的一个真实文件编译 fast 任务。

只使用原模板中显式声明的选项判断能力冲突，不把通用缺省值解释为用户要求。
模板绑定错误带模板路径及当前文件说明。此步骤不执行分析或打开原始日志。

```python
compile_template_plan(plan, *, template_path=None, _with_database=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。公开解析器构建的计划，含静态信号绑定及逐消息计算项。|
|`template_path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|仅关键字。原始模板路径，用于保持显式设置和拒绝位置。|
|`_with_database`|bool|否|False|仅关键字。启用时附上本次 DBC 对象供同进程复用，默认产出可传递的普通参数。|

源码：[`src/chronaxis/fast/config.py:178`](../../../src/chronaxis/fast/config.py#L178)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-compile_config"></a>
## `compile_config`

读取配置和导入定义，验证 DBC 与 fast 子集。默认返回可序列化单文件任务。

参数 path 是 JSON/YAML 文件路径；_with_database 仅给同进程立即执行时复用数据库。
错误带配置路径。此入口只准备计算，不打开日志或创建输出目录。

```python
compile_config(path, *, _with_database=False)
```

装饰器：`scoped_dbc_cache()`。

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。要读取的文件路径。|
|`_with_database`|bool|否|False|仅关键字。启用时附上本次 DBC 对象供同进程复用，默认产出可传递的普通参数。|

源码：[`src/chronaxis/fast/config.py:205`](../../../src/chronaxis/fast/config.py#L205)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
