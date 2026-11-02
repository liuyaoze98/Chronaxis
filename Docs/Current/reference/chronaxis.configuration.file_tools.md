# chronaxis.configuration.file_tools

当前配置的格式转换和新文件发布；不推断业务参数，不执行分析。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`configuration_type`](#api-configuration_type)|识别三个独立当前入口。|
|[`validate_document`](#api-validate_document)|调用现有模型；return_plan=True时同时返回计划，避免配置工具重复加载DBC。|
|[`path_fields`](#api-path_fields)|枚举声明的文件路径位置。|
|[`same_native_value`](#api-same_native_value)|核类型/顺序/数值不漂移，包含负零和大整数。|
|[`serialize_configuration`](#api-serialize_configuration)|输出可被受限解析器再读取的文本。|
|[`output_format`](#api-output_format)|由扩展名选择格式。|
|[`write_new_configuration`](#api-write_new_configuration)|独占写新文件。|
|[`convert_configuration`](#api-convert_configuration)|仅改变当前配置的JSON/YAML表示。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from io import StringIO
from pathlib import Path
from . import load_configuration, parse_configuration
from .diagnostics import locate_error
```

</details>

<a id="api-configuration_type"></a>
## `configuration_type`

识别三个独立当前入口。

```python
configuration_type(data)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|JSON原生配置对象|是|无|位置或关键字。当前入口的原生配置内容；只支持文本键及有限数值，结构由现有计划模型校验。|

### 返回说明

analysis/batch/mapping。

### 异常说明

ValueError。

版本不能猜测或迁移；旧INI由独立legacy import入口处理。

源码：[`src/chronaxis/configuration/file_tools.py:11`](../../../src/chronaxis/configuration/file_tools.py#L11)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-validate_document"></a>
## `validate_document`

调用现有模型；return_plan=True时同时返回计划，避免配置工具重复加载DBC。

批量不加载子任务，映射只核映射与其分析部分；INI模式与段名需在实际导入时核对。

```python
validate_document(document, base, *, return_plan=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`document`|ConfigurationDocument|是|无|位置或关键字。共享解析器返回的原生配置及字段位置；不包含业务输入记录。|
|`base`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。解释配置相对文件路径的词法绝对目录；不打开其中的日志或DBC。|
|`return_plan`|bool|否|False|仅关键字。默认False只返回配置种类；True同时返回已编译计划，供配置工具复用结果，避免重复加载DBC。|

源码：[`src/chronaxis/configuration/file_tools.py:26`](../../../src/chronaxis/configuration/file_tools.py#L26)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-path_fields"></a>
## `path_fields`

枚举声明的文件路径位置。

```python
path_fields(data, config_type)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|JSON原生配置对象|是|无|位置或关键字。当前入口的原生配置内容；只支持文本键及有限数值，结构由现有计划模型校验。|
|`config_type`|str|是|无|位置或关键字。配置入口类别：analysis为单任务、batch为批量清单、mapping为INI显式映射。|

### 返回说明

(容器,键)迭代器。

### 异常说明

内部结构错误。

只认来源文件/DBC、批量子计划和公共定义；metadata与表达式中的path文字保持原样。

源码：[`src/chronaxis/configuration/file_tools.py:54`](../../../src/chronaxis/configuration/file_tools.py#L54)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-same_native_value"></a>
## `same_native_value`

核类型/顺序/数值不漂移，包含负零和大整数。

```python
same_native_value(left, right)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`left`|JSON原生值|是|无|位置或关键字。转换前的比较基准，类型、容器顺序、数值与浮点负零都要保持。|
|`right`|JSON原生值|是|无|位置或关键字。转换后重新解析的候选值；与left逐层比较，不能把1.0和整数1当作相同类型。|

### 返回说明

bool。

### 异常说明

无。

源码：[`src/chronaxis/configuration/file_tools.py:76`](../../../src/chronaxis/configuration/file_tools.py#L76)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-serialize_configuration"></a>
## `serialize_configuration`

输出可被受限解析器再读取的文本。

```python
serialize_configuration(data, format)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|JSON原生配置对象|是|无|位置或关键字。当前入口的原生配置内容；只支持文本键及有限数值，结构由现有计划模型校验。|
|`format`|str|是|无|位置或关键字。文本格式；配置只接受json或yaml，不能用格式选择转换旧结构版本。|

### 返回说明

str。

### 异常说明

ValueError。

输出后独立重解析并核类型和值，避免YAML隐式类型或浮点表示改写含义。注释不参与互转。

源码：[`src/chronaxis/configuration/file_tools.py:87`](../../../src/chronaxis/configuration/file_tools.py#L87)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-output_format"></a>
## `output_format`

由扩展名选择格式。

```python
output_format(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) 或 str|是|无|位置或关键字。配置文件路径；读取入口按文件父目录解释相对输入，写入入口只接受全新目标，不扫描目录。|

### 返回说明

json/yaml。

### 异常说明

ValueError。

源码：[`src/chronaxis/configuration/file_tools.py:105`](../../../src/chronaxis/configuration/file_tools.py#L105)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-write_new_configuration"></a>
## `write_new_configuration`

独占写新文件。

```python
write_new_configuration(path, text)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) 或 str|是|无|位置或关键字。配置文件路径；读取入口按文件父目录解释相对输入，写入入口只接受全新目标，不扫描目录。|
|`text`|str|是|无|位置或关键字。要处理的配置文本或字段路径文本；不会作为Python代码执行。|

### 返回说明

Path。

### 异常说明

IO/取消。

已存在文件、硬链接和符号链接都由独占打开拒绝；部分写失败仅清理本次创建的文件。

源码：[`src/chronaxis/configuration/file_tools.py:112`](../../../src/chronaxis/configuration/file_tools.py#L112)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-convert_configuration"></a>
## `convert_configuration`

仅改变当前配置的JSON/YAML表示。

```python
convert_configuration(source, output)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) 或 str|是|无|位置或关键字。要读取的当前配置文件；以其声明目录固定输入定位，原文件保持不变。|
|`output`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) 或 str|是|无|位置或关键字。尚不存在的目标文件或目录；初始化写完整新目录，转换与展开写新文件，已有目标拒绝。|

### 返回说明

输出Path。

### 异常说明

配置/IO错误。

相对路径存在时仅接受同目录输出；跨目录需使用resolve显式重定位，不静默修改原值。

源码：[`src/chronaxis/configuration/file_tools.py:130`](../../../src/chronaxis/configuration/file_tools.py#L130)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

## 内部匿名回调


<a id="lambda-97"></a>
### 第97行匿名函数

```python
lambda value: True
```

|参数|含义|返回/异常|
|---|---|---|
|`value`|参数按上方签名传入；具体调用语义尚待补充。|返回值由上方表达式决定；具体用途和异常尚待核对，不据模板推断。|
