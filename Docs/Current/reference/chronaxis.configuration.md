# `chronaxis.configuration`

共享配置语法入口；只读指定文件，返回原生值和加载期位置，不读取业务输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConfigurationDocument](chronaxis.configuration.models.md#api-ConfigurationDocument)、[ConfigurationError](chronaxis.configuration.models.md#api-ConfigurationError)、[ConfigurationLocation](chronaxis.configuration.models.md#api-ConfigurationLocation)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`parse_configuration`](#api-parse_configuration)|解析显式格式文本。|
|[`load_configuration`](#api-load_configuration)|按.json/.yaml/.yml加载UTF-8文件。|

## 导出名称

`ConfigurationDocument`, `ConfigurationError`, `ConfigurationLocation`, `field_path_text`, `parse_configuration`, `load_configuration`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from types import MappingProxyType
from .models import ConfigurationDocument, ConfigurationError, ConfigurationLocation, field_path_text
from .json_parser import parse_json
```

</details>

<a id="api-parse_configuration"></a>
## `parse_configuration`

解析显式格式文本。

```python
parse_configuration(text, *, format, source='<configuration>')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。要处理的配置文本或字段路径文本；不会作为Python代码执行。|
|`format`|str|是|无|仅关键字。文本格式；配置只接受json或yaml，不能用格式选择转换旧结构版本。|
|`source`|str 或 [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|否|'<configuration>'|仅关键字。配置的来源文件或显示名称；用于相对路径解释和错误定位，不是业务日志内容。|

### 返回说明

文档。

### 异常说明

语法或参数错误。

不替换环境变量或执行模板。UTF-8文件开头的BOM可选；字段原始字符串保留。

源码：[`src/chronaxis/configuration/__init__.py:12`](../../../src/chronaxis/configuration/__init__.py#L12)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-load_configuration"></a>
## `load_configuration`

按.json/.yaml/.yml加载UTF-8文件。

```python
load_configuration(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) 或 str|是|无|位置或关键字。配置文件路径；读取入口按文件父目录解释相对输入，写入入口只接受全新目标，不扫描目录。|

### 返回说明

文档。

### 异常说明

定位读取/语法错误；取消原样传播。

后缀不识别时不打开文件；读取结束即关闭句柄，再解析文本，不持有调用者输入文件。

源码：[`src/chronaxis/configuration/__init__.py:30`](../../../src/chronaxis/configuration/__init__.py#L30)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
