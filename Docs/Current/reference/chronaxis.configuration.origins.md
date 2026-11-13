# `chronaxis.configuration.origins`

按请求说明定义或叶字段来自哪个配置文件；不作为执行计划的持久状态。

只读主配置与明确的一层公共定义，先复用静态校验再生成小型来源记录。
默认报告定义位置及来源文件路径；fields模式列全部用户实际写入的最终取值字段，不虚构默认值来源。
不读取ASC/BLF/CSV中的数据记录；校验可能读取显式DBC以补齐信号元数据。
不写报告文件；调用者决定显示或重定向。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_at`](#api-_at)|读取存在的字段，跳过展开后已删除的imports位置。|
|[`_record`](#api-_record)|复制一项有限来源事实。|
|[`configuration_origins`](#api-configuration_origins)|读取实际定义或叶字段的声明位置。|
|[`render_origins`](#api-render_origins)|将有限来源记录显示为中文文本。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from . import load_configuration
from .imports import expand_document_imports
from .file_tools import validate_document
from .models import field_path_text
```

</details>

<a id="api-_at"></a>
## `_at`

读取存在的字段，跳过展开后已删除的imports位置。

```python
_at(data, path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|dict &#124; list &#124; str &#124; int &#124; float &#124; bool &#124; None|是|无|位置或关键字。已解析的JSON原生值树；只读取，不复制或修改。|
|`path`|tuple[str &#124; int, ...]|是|无|位置或关键字。字段键和数组索引组成的内部路径，根为()；不执行其中的文本。|

### 返回说明

(存在,值)。

### 异常说明

无。

源码：[`src/chronaxis/configuration/origins.py:16`](../../../src/chronaxis/configuration/origins.py#L16)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_record"></a>
## `_record`

复制一项有限来源事实。

```python
_record(document, path, name=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`document`|ConfigurationDocument|是|无|位置或关键字。本次解析后的配置文档，包含原生值、声明文件路径及仅在加载期使用的行列。|
|`path`|tuple[str &#124; int, ...]|是|无|位置或关键字。字段键和数组索引组成的内部路径，根为()；不执行其中的文本。|
|`name`|str &#124; None|否|None|位置或关键字。定义的来源名、信号名、派生名或任务ID；逐字段模式默认None。|

### 返回说明

dict。

### 异常说明

无。

源码：[`src/chronaxis/configuration/origins.py:26`](../../../src/chronaxis/configuration/origins.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-configuration_origins"></a>
## `configuration_origins`

读取实际定义或叶字段的声明位置。

```python
configuration_origins(source, *, fields=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; str|是|无|位置或关键字。当前分析或批量配置文件；读取该配置及明确的一层公共定义，静态信号推导可能读取声明的DBC，不读取数据记录。|
|`fields`|bool|否|False|仅关键字。默认False列定义；True列所有用户实际写入的最终取值字段及原文件行列，不复制字段值，也不虚构默认值来源。|

### 返回说明

来源报告dict。

### 异常说明

配置/读取错误。

分析配置列其定义；批量只列本文件的任务，不读取子计划。省略的默认字段
不在报告内。fields只保位置而不复制值；路径声明单独说明最终指向。

源码：[`src/chronaxis/configuration/origins.py:37`](../../../src/chronaxis/configuration/origins.py#L37)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-render_origins"></a>
## `render_origins`

将有限来源记录显示为中文文本。

```python
render_origins(report)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`report`|dict|是|无|位置或关键字。configuration_origins生成的有限来源报告；包括configuration和items，逐项显示文件与字段位置。|

### 返回说明

str。

### 异常说明

内部报告结构错误。

源码：[`src/chronaxis/configuration/origins.py:81`](../../../src/chronaxis/configuration/origins.py#L81)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
