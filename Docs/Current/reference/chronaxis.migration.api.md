# chronaxis.migration.api

提供纯字节旧INI导入与显式配置文件的加载入口，不读取分析数据。

共享流程检查原生JSON mapping、保存身份、复制analysis并固定按声明目录形成的绝对路径（不解析链接真实目标），
按模式转换后调用公开AnalysisPlan.from_dict/validate_analysis_plan。配置语义错误返回
整份失败报告；API类型、文件I/O、内存与取消错误保持原生异常，不伪装成成功。
支持Sclicer single/start_only、显式slope/start_end迁移和当前消息legacy_sum；不承诺旧完整缓存等价。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[ConfigurationError](chronaxis.configuration.models.md#api-ConfigurationError)、[ImportProblem](chronaxis.migration.ini.md#api-ImportProblem)、[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)、[LegacyImportReport](chronaxis.migration.models.md#api-LegacyImportReport)、[LegacyImportResult](chronaxis.migration.models.md#api-LegacyImportResult)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`_arguments`](#api-_arguments)|先核公开API类型，不把编程错误包成迁移拒绝。|
|[`_report`](#api-_report)|封装整份结果；|
|[`_prepare_mapping`](#api-_prepare_mapping)|检查完整mapping合同并复制为独立可修改分析配置。|
|[`import_legacy_ini`](#api-import_legacy_ini)|从原INI字节和显式mapping生成完整静态计划或整份拒绝报告。|
|[`load_legacy_ini`](#api-load_legacy_ini)|只读INI、映射及显式一层公共定义，来源路径基准按实际声明文件确定。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from pathlib import Path
from ..configuration import load_configuration, ConfigurationError, field_path_text
from ..configuration.diagnostics import locate_error, field_path_parts
from ..planning import AnalysisPlan, PlanValidationError, validate_analysis_plan
from ..planning.checks import absolute_path, require_json_value
from .ini import ImportProblem, parse_ini, problem
from .models import LegacyImportIssue, LegacyImportReport, LegacyImportResult
from .sclicer import convert_sclicer
from .legacy_sum import convert_legacy_sum
```

</details>

<a id="api-_arguments"></a>
## `_arguments`

先核公开API类型，不把编程错误包成迁移拒绝。

```python
_arguments(content, mapping, mode, base_dir, source_name, device_label)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`content`|bytes|是|无|位置或关键字。旧INI的原始bytes，保留BOM与换行，不先转成已改写配置。|
|`mapping`|dict|是|无|位置或关键字。INI映射对象，必填mapping_version和analysis。path_base、io_policy采用固定默认值；aliases可由唯一原字段名推导，single/start_only/start_end的sections可省略并生成名称；legacy_sum和slope仍需计算单位或模式参数。见[迁移字段表](../migration.md)。|
|`mode`|str|是|无|位置或关键字。选择legacy_sum、sclicer_single、sclicer_start_only、sclicer_start_end或sclicer_slope。每种模式转换的内容和必填映射见[迁移](../migration.md)。|
|`base_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。mapping中相对来源路径的解析基准目录。|
|`source_name`|str|是|无|位置或关键字。报告中记录的原配置名称；只是来源标识，不参与信号选择。|
|`device_label`|str|是|无|位置或关键字。产出记录的设备标签，例如已核实的"home"或"work"；未确定时用"pending"。这是来源说明，不参与数值计算，也不根据文件路径猜测。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

TypeError为原生类型错误；ValueError为未知mode。

本函数直接报告的具体错误：

- `TypeError`：content需要bytes，mapping需要原生dict。
- `TypeError`：mode/source_name/device_label需要原生str。
- `TypeError`：base_dir需要str或Path。

源码：[`src/chronaxis/migration/api.py:26`](../../../src/chronaxis/migration/api.py#L26)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_report"></a>
## `_report`

封装整份结果；

```python
_report(content, mode, source_name, device_label, mapping_identity, fields, issues, plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`content`|bytes|是|无|位置或关键字。旧INI文件的原始字节，保留BOM和换行，用于记录原文及其摘要。|
|`mode`|str|是|无|位置或关键字。选择legacy_sum、sclicer_single、sclicer_start_only、sclicer_start_end或sclicer_slope。每种模式转换的内容和必填映射见[迁移](../migration.md)。|
|`source_name`|str|是|无|位置或关键字。报告中记录的原配置名称；只是来源标识，不参与信号选择。|
|`device_label`|str|是|无|位置或关键字。产出记录的设备标签，例如已核实的"home"或"work"；未确定时用"pending"。这是来源说明，不参与数值计算，也不根据文件路径猜测。|
|`mapping_identity`|str|是|无|位置或关键字。规范化迁移mapping的身份摘要，表示采用了哪份映射；不表示实际日志已经读取。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`issues`|list[[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)]|是|无|位置或关键字。接收本次转换的差异、警告和拒绝原因；调用者随后将它们写入迁移报告。|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。本次冻结AnalysisPlan，提供来源、规则、范围与执行预算。|

### 返回说明

LegacyImportResult；

### 异常说明

资源错误原样传播。

源码：[`src/chronaxis/migration/api.py:41`](../../../src/chronaxis/migration/api.py#L41)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_prepare_mapping"></a>
## `_prepare_mapping`

检查完整mapping合同并复制为独立可修改分析配置。

```python
_prepare_mapping(mapping, base)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`mapping`|dict|是|无|位置或关键字。INI映射对象，必填mapping_version和analysis。path_base、io_policy采用固定默认值；aliases可由唯一原字段名推导，single/start_only/start_end的sections可省略并生成名称；legacy_sum和slope仍需计算单位或模式参数。见[迁移字段表](../migration.md)。|
|`base`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。base词法绝对目录。|

### 返回说明

(独立mapping, identity)。

### 异常说明

ImportProblem/PlanValidationError为配置问题。目录输入会展开文件集合，缺省CAN声明会读取DBC。

源码：[`src/chronaxis/migration/api.py:49`](../../../src/chronaxis/migration/api.py#L49)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-import_legacy_ini"></a>
## `import_legacy_ini`

从原INI字节和显式mapping生成完整静态计划或整份拒绝报告。

```python
import_legacy_ini(content: bytes, mapping: dict, *, mode, base_dir, source_name='input.ini', device_label='pending') -> LegacyImportResult
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`content`|bytes|是|无|位置或关键字。原INI文件的完整bytes内容。保留原字节用于摘要和迁移报告，不传已经拆分的配置字典。|
|`mapping`|dict|是|无|位置或关键字。INI映射对象，必填mapping_version和analysis。path_base、io_policy采用固定默认值；aliases可由唯一原字段名推导，single/start_only/start_end的sections可省略并生成名称；legacy_sum和slope仍需计算单位或模式参数。见[迁移字段表](../migration.md)。|
|`mode`|str|是|无|仅关键字。选择legacy_sum、sclicer_single、sclicer_start_only、sclicer_start_end或sclicer_slope。每种模式转换的内容和必填映射见[迁移](../migration.md)。|
|`base_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|仅关键字。base_dir 为mapping目录|
|`source_name`|str|否|'input.ini'|仅关键字。报告中记录的原配置名称；只是来源标识，不参与信号选择。|
|`device_label`|str|否|'pending'|仅关键字。产出记录的设备标签，例如已核实的"home"或"work"；未确定时用"pending"。这是来源说明，不参与数值计算，也不根据文件路径猜测。|

### 返回说明

LegacyImportResult，
original_ini保同一bytes，失败plan为None。

### 异常说明

API类型/未知mode、OSError、
MemoryError及取消保持原对象；配置语义与UTF-8错误进入report，不返回部分计划。

返回类型：[LegacyImportResult](chronaxis.migration.models.md#api-LegacyImportResult)。

源码：[`src/chronaxis/migration/api.py:160`](../../../src/chronaxis/migration/api.py#L160)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-load_legacy_ini"></a>
## `load_legacy_ini`

只读INI、映射及显式一层公共定义，来源路径基准按实际声明文件确定。

```python
load_legacy_ini(ini_path, mapping_path, *, mode, device_label='pending') -> LegacyImportResult
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ini_path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。原INI文件路径；读取原字节并保留它，不覆盖原文件。|
|`mapping_path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。映射JSON/YAML路径；支持analysis内的imports和受限覆盖，来源路径按声明文件解释。按需要枚举目录及读取缺省信号的DBC元数据，不读取业务报文。|
|`mode`|str|是|无|仅关键字。选择legacy_sum、sclicer_single、sclicer_start_only、sclicer_start_end或sclicer_slope。每种模式转换的内容和必填映射见[迁移](../migration.md)。|
|`device_label`|str|否|'pending'|仅关键字。产出记录的设备标签，例如已核实的"home"或"work"；未确定时用"pending"。这是来源说明，不参与数值计算，也不根据文件路径猜测。|

### 返回说明

LegacyImportResult，非法JSON/YAML给mapping定位。

### 异常说明

API类型、未知mode、文件读取OSError、MemoryError及取消按原接口传播；配置语义错误进入迁移报告。目录和DBC访问取决于声明，不承诺加载完全无I/O。

返回类型：[LegacyImportResult](chronaxis.migration.models.md#api-LegacyImportResult)。

源码：[`src/chronaxis/migration/api.py:217`](../../../src/chronaxis/migration/api.py#L217)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
