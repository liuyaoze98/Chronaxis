# chronaxis.configuration.imports

展开明确列出的一层本地公共定义，供分析文件和INI映射文件加载使用。

主配置按imports顺序引入sources/signals/derived，最后追加本地声明；重复名称
直接拒绝。导入文件不能再导入文件，也不能声明运行、规则或输出字段。
仅打开配置文件，数据/DBC路径按各自声明文件转为按声明目录形成的绝对路径（不解析链接真实目标）；不读取业务输入。
位置随本次加载保留，成功计划不持有原文或第二份配置，不执行环境替换或模板。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConfigurationDocument](chronaxis.configuration.models.md#api-ConfigurationDocument)、[ConfigurationOrigin](chronaxis.configuration.models.md#api-ConfigurationOrigin)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`_reject`](#api-_reject)|在实际声明处拒绝导入。|
|[`_source_paths`](#api-_source_paths)|固定一项来源中的公开文件路径。|
|[`_append_definitions`](#api-_append_definitions)|追加一个文件的定义并迁移字段位置。|
|[`expand_document_imports`](#api-expand_document_imports)|展开分析配置或映射中analysis的公共定义。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from . import load_configuration
from .diagnostics import locate_error
from .models import ConfigurationDocument, ConfigurationOrigin, field_path_text
```

</details>

<a id="api-_reject"></a>
## `_reject`

在实际声明处拒绝导入。

```python
_reject(document, path, message, code='invalid_import', hint=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`document`|[ConfigurationDocument](chronaxis.configuration.models.md#api-ConfigurationDocument)|是|无|位置或关键字。本次解析后的配置文档，包含原生值、声明文件路径及仅在加载期使用的行列。|
|`path`|tuple[str &#124; int, ...]|是|无|位置或关键字。字段键和数组索引组成的内部路径，根为()；不执行其中的文本。|
|`message`|str|是|无|位置或关键字。违反的导入约束，作为错误的具体原因。|
|`code`|str|否|'invalid_import'|位置或关键字。机器错误码，默认invalid_import；重复名传duplicate_definition。|
|`hint`|str &#124; None|否|None|位置或关键字。修正建议；默认None，不自动猜测替代值。|

### 返回说明

不返回。

### 异常说明

PlanValidationError。

源码：[`src/chronaxis/configuration/imports.py:19`](../../../src/chronaxis/configuration/imports.py#L19)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_source_paths"></a>
## `_source_paths`

固定一项来源中的公开文件路径。

```python
_source_paths(source, base, path, document)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|dict|是|无|位置或关键字。一项来源的独立副本；仅其中path、paths、dbc_by_channel会原地改为绝对定位。|
|`base`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。这项来源实际声明文件的父目录。|
|`path`|tuple[str &#124; int, ...]|是|无|位置或关键字。字段键和数组索引组成的内部路径，根为()；不执行其中的文本。|
|`document`|[ConfigurationDocument](chronaxis.configuration.models.md#api-ConfigurationDocument)|是|无|位置或关键字。本次解析后的配置文档，包含原生值、声明文件路径及仅在加载期使用的行列。|

### 返回说明

None。

### 异常说明

字段错误。

只改本次副本，metadata内任意path不解释为文件；不调用stat或resolve。

源码：[`src/chronaxis/configuration/imports.py:25`](../../../src/chronaxis/configuration/imports.py#L25)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_append_definitions"></a>
## `_append_definitions`

追加一个文件的定义并迁移字段位置。

```python
_append_definitions(data, prefix, document, source_prefix, merged, locations, origins, names)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|dict|是|无|位置或关键字。当前文件的sources/signals数组及derived名称对象；原内容不修改。|
|`prefix`|tuple[str &#124; int, ...]|是|无|位置或关键字。合并后定义的父路径；分析配置为()，INI映射为(analysis,)。|
|`document`|[ConfigurationDocument](chronaxis.configuration.models.md#api-ConfigurationDocument)|是|无|位置或关键字。本次解析后的配置文档，包含原生值、声明文件路径及仅在加载期使用的行列。|
|`source_prefix`|tuple[str &#124; int, ...]|是|无|位置或关键字。原文件中的分析父路径；公共文件为()，主映射文件为(analysis,)。|
|`merged`|dict|是|无|位置或关键字。本次合并的定义容器，按声明顺序追加，不覆盖同名项。|
|`locations`|dict|是|无|位置或关键字。合并字段路径到原文行列的临时映射，在本次调用中追加。|
|`origins`|dict|是|无|位置或关键字。合并路径到ConfigurationOrigin的临时映射，计划完成后释放。|
|`names`|dict|是|无|位置或关键字。按来源或信号/派生名字空间登记首个定义位置；用于拒绝重复。|

### 返回说明

None。

### 异常说明

定义/重复错误。

names保存首个同名声明的位置；所有修改仅发生在本次展开容器，无全局状态。

源码：[`src/chronaxis/configuration/imports.py:46`](../../../src/chronaxis/configuration/imports.py#L46)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-expand_document_imports"></a>
## `expand_document_imports`

展开分析配置或映射中analysis的公共定义。

```python
expand_document_imports(document)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`document`|[ConfigurationDocument](chronaxis.configuration.models.md#api-ConfigurationDocument)|是|无|位置或关键字。本次解析后的配置文档，包含原生值、声明文件路径及仅在加载期使用的行列。|

### 返回说明

可直接静态检查的文档。

### 异常说明

配置/读取错误。

未声明imports时原样返回，不增加复制或文件读取。批量文件通过每个子计划
自行使用imports；纯字典API不调用此函数。版本错误由原入口拒绝，不读其导入。

源码：[`src/chronaxis/configuration/imports.py:98`](../../../src/chronaxis/configuration/imports.py#L98)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
