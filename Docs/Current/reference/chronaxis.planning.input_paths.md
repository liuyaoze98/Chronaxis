# `chronaxis.planning.input_paths`

将文件、目录或通配符展开为有序输入，不读取报文内容。

明确文件列表保持用户顺序；每个目录或通配符内部采用自然排序。
只枚举显式请求的目录，不递归追踪子目录；递归必须通过**通配符提出。
展开最多4096项，空匹配及无效路径报配置错误，不悄悄跳过缺失目录。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`natural_path_key`](#api-natural_path_key)|产生稳定自然序键，使file2排在file10前。|
|[`expand_source_files`](#api-expand_source_files)|按声明展开来源路径；目录只取该来源支持的格式。|
|[`expand_input_paths`](#api-expand_input_paths)|只取展开文件路径，供无需文件偏移的调用方使用。|
|[`source_path_fields`](#api-source_path_fields)|枚举文件声明中的路径文字，供转换/导入工具固定路径基准。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from glob import iglob
from pathlib import Path
from .checks import PlanValidationError, absolute_path, array_at, coordinate_at, object_at, text_at
```

</details>

<a id="api-natural_path_key"></a>
## `natural_path_key`

产生稳定自然序键，使file2排在file10前。

```python
natural_path_key(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。输入路径，数字部分按数值排列，平局保留确定顺序；不访问文件。|

### 返回说明

数字/文字分段键及原路径平局键。

### 异常说明

无主动异常；不访问文件系统。

源码：[`src/chronaxis/planning/input_paths.py:21`](../../../src/chronaxis/planning/input_paths.py#L21)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-expand_source_files"></a>
## `expand_source_files`

按声明展开来源路径；目录只取该来源支持的格式。

```python
expand_source_files(raw, base, where)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。含path或paths且二者互斥的来源声明，支持目录、通配符及文件offset。|
|`base`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。输入相对路径的声明目录。|
|`where`|str|是|无|位置或关键字。来源在配置中的字段位置。|

### 返回说明

(绝对Path元组, 可选逐文件偏移字符串元组)。

### 异常说明

PlanValidationError表示缺项、空匹配或超限；
    OSError由目录读取产生并转换为带配置位置的错误。

### 副作用说明

仅目录/通配符声明枚举文件名；明确文件不stat、不读数据内容。

源码：[`src/chronaxis/planning/input_paths.py:34`](../../../src/chronaxis/planning/input_paths.py#L34)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-expand_input_paths"></a>
## `expand_input_paths`

只取展开文件路径，供无需文件偏移的调用方使用。

```python
expand_input_paths(raw, base, where)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。需展开输入文件集合的来源声明。|
|`base`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。路径解释基准目录。|
|`where`|str|是|无|位置或关键字。配置字段位置，用于缺项/超限错误。|

### 返回说明

Path元组。

### 异常说明

与expand_source_files一致；目录扫描只执行一次。

源码：[`src/chronaxis/planning/input_paths.py:94`](../../../src/chronaxis/planning/input_paths.py#L94)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-source_path_fields"></a>
## `source_path_fields`

枚举文件声明中的路径文字，供转换/导入工具固定路径基准。

```python
source_path_fields(source, where='$.sources')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|dict|是|无|位置或关键字。仅枚举已声明的path/paths字段，不扫描目录或改自由metadata。|
|`where`|str|否|'$.sources'|位置或关键字。来源的配置路径，用于非法结构错误。|

### 返回说明

(容器,键)迭代器。

### 异常说明

PlanValidationError为错误结构。不扫描目录，不改变offset或其他元数据。

源码：[`src/chronaxis/planning/input_paths.py:103`](../../../src/chronaxis/planning/input_paths.py#L103)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
