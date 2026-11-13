# `chronaxis.configuration.template_catalog`

读取随包发布的合成场景模板；初始化命令与模板验收使用同一套资源。

目录中保存最小版和完整注释版YAML及小型合成输入。本模块仅提供有限模板清单
和文件内容，不创建用户目录、不执行分析、不把模板阈值当作真实设备参数。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`ConfigurationTemplate`](#api-ConfigurationTemplate)|可选场景及其入口；名称用于CLI选择，说明同时注明合成数据和预期行为。|
|[`_catalog`](#api-_catalog)|读取包内固定清单。|
|[`available_templates`](#api-available_templates)|列出当前所有场景。|
|[`_relative_path`](#api-_relative_path)|限制包内及新目录内的相对路径。|
|[`template_files`](#api-template_files)|取得一个场景的完整文件集。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from importlib.resources import files
from pathlib import PurePosixPath
```

</details>

<a id="api-ConfigurationTemplate"></a>
## `ConfigurationTemplate`

可选场景及其入口；名称用于CLI选择，说明同时注明合成数据和预期行为。

```python
class ConfigurationTemplate
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|模板清单中的固定场景名；用于选择完整资源集，不接受任意文件路径。|
|`title`|str|是|无|场景的中文用途说明，帮助选择适合的问题类型，不参与计算。|
|`config_type`|str|是|无|配置入口类别：analysis为当前单任务分析、batch为当前批量清单。|
|`entrypoint`|str|是|无|模板目录内的主配置相对路径；分析用plan.yaml，批量用batch.yaml。|
|`expected`|str|是|无|合成场景的独立手算预期；只解释模板数据，不作为真实设备参数建议。|

源码：[`src/chronaxis/configuration/template_catalog.py:13`](../../../src/chronaxis/configuration/template_catalog.py#L13)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_catalog"></a>
## `_catalog`

读取包内固定清单。

```python
_catalog()
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

dict。

### 异常说明

缺失或损坏资源不隐藏。

源码：[`src/chronaxis/configuration/template_catalog.py:22`](../../../src/chronaxis/configuration/template_catalog.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-available_templates"></a>
## `available_templates`

列出当前所有场景。

```python
available_templates()
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

ConfigurationTemplate tuple。

### 异常说明

包资源错误。

源码：[`src/chronaxis/configuration/template_catalog.py:28`](../../../src/chronaxis/configuration/template_catalog.py#L28)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_relative_path"></a>
## `_relative_path`

限制包内及新目录内的相对路径。

```python
_relative_path(text)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。模板清单中的POSIX相对路径；拒绝空路径、绝对路径、反斜线、盘符和父目录跳转。|

### 返回说明

PurePosixPath。

### 异常说明

ValueError。

清单由项目维护；仍拒绝绝对路径、返回父目录和Windows反斜线，防止资源误配越界。

源码：[`src/chronaxis/configuration/template_catalog.py:35`](../../../src/chronaxis/configuration/template_catalog.py#L35)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-template_files"></a>
## `template_files`

取得一个场景的完整文件集。

```python
template_files(name, *, style='annotated')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。模板清单中的固定场景名；用于选择完整资源集，不接受任意文件路径。|
|`style`|str|否|'annotated'|仅关键字。minimal只含必要配置，annotated提供完整说明；两者解析后的配置相同，默认annotated。|

### 返回说明

(相对路径,bytes) tuple。

### 异常说明

未知场景/风格为ValueError，包内文件错误直接传播；不读取用户配置或写文件。
两种风格只有注释不同，批量子计划也按同一风格选择。资源不含环境变量或模板执行。

源码：[`src/chronaxis/configuration/template_catalog.py:46`](../../../src/chronaxis/configuration/template_catalog.py#L46)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
