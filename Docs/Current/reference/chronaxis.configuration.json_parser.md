# chronaxis.configuration.json_parser

标准库负责JSON语法和数值；轻量第二遍只定位字段，不再构造第二份配置树。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConfigurationError](chronaxis.configuration.models.md#api-ConfigurationError)、[ConfigurationLocation](chronaxis.configuration.models.md#api-ConfigurationLocation)

## 对象导航

|对象|用途|
|---|---|
|[`_DuplicateKey`](#api-_DuplicateKey)|只用于让标准库停止覆盖重复键；随后位置扫描给出具体字段。|
|[`_unique_pairs`](#api-_unique_pairs)|建立唯一键对象。|
|[`_Locations`](#api-_Locations)|只记录JSON路径和偏移，不保留第二份值树；语法真值仍由json.loads决定。|
|[`_Locations.__init__`](#api-_Locations-__init__)|建立本次扫描状态。|
|[`_Locations.location`](#api-_Locations-location)|把字符偏移转换为1基行列。|
|[`_Locations.scan`](#api-_Locations-scan)|遍历合法JSON或已知含重复键的JSON。|
|[`_finite_values`](#api-_finite_values)|拒绝JSON宽松接受的NaN/Infinity及指数溢出。|
|[`parse_json`](#api-parse_json)|按标准JSON加载并附准确位置。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from bisect import bisect_right
from math import isfinite
from .models import ConfigurationError, ConfigurationLocation
```

</details>

<a id="api-_DuplicateKey"></a>
## `_DuplicateKey`

只用于让标准库停止覆盖重复键；随后位置扫描给出具体字段。

```python
class _DuplicateKey(ValueError)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/configuration/json_parser.py:13`](../../../src/chronaxis/configuration/json_parser.py#L13)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_unique_pairs"></a>
## `_unique_pairs`

建立唯一键对象。

```python
_unique_pairs(pairs)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pairs`|list[tuple[str, JSON原生值]]|是|无|位置或关键字。JSON解码器按原顺序给出的键值对；重复键在构建对象前拒绝，不保留最后一项。|

### 返回说明

dict。

### 异常说明

重复键。

源码：[`src/chronaxis/configuration/json_parser.py:17`](../../../src/chronaxis/configuration/json_parser.py#L17)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_Locations"></a>
## `_Locations`

只记录JSON路径和偏移，不保留第二份值树；语法真值仍由json.loads决定。

```python
_Locations(text, source)
```


源码：[`src/chronaxis/configuration/json_parser.py:27`](../../../src/chronaxis/configuration/json_parser.py#L27)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_Locations-__init__"></a>
### `_Locations.__init__`

建立本次扫描状态。

```python
_Locations.__init__(text, source)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。要处理的配置文本或字段路径文本；不会作为Python代码执行。|
|`source`|str 或 Path|是|无|位置或关键字。配置的来源文件或显示名称；用于相对路径解释和错误定位，不是业务日志内容。|

#### 返回说明

owner。

#### 异常说明

分配失败。

源码：[`src/chronaxis/configuration/json_parser.py:30`](../../../src/chronaxis/configuration/json_parser.py#L30)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_Locations-location"></a>
### `_Locations.location`

把字符偏移转换为1基行列。

```python
_Locations.location(offset)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`offset`|int|是|无|位置或关键字。从原文本开头起算的字符偏移；用于计算1起算的行列，不能当作UTF-8字节偏移。|

#### 返回说明

位置。

#### 异常说明

无。

源码：[`src/chronaxis/configuration/json_parser.py:37`](../../../src/chronaxis/configuration/json_parser.py#L37)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_Locations-scan"></a>
### `_Locations.scan`

遍历合法JSON或已知含重复键的JSON。

```python
_Locations.scan(offset=0, path=(), depth=0)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`offset`|int|否|0|位置或关键字。从原文本开头起算的字符偏移；用于计算1起算的行列，不能当作UTF-8字节偏移。|
|`path`|tuple[str 或 int, ...]|否|()|位置或关键字。从配置根开始的字段键/数组下标序列；只表示当前值的位置，不是操作系统文件路径。|
|`depth`|int|否|0|位置或关键字。当前配置容器嵌套层数；超过共享解析上限64时报错，防止无界递归。|

#### 返回说明

结束偏移。

#### 异常说明

重复键/过深/语法错误。

源码：[`src/chronaxis/configuration/json_parser.py:43`](../../../src/chronaxis/configuration/json_parser.py#L43)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_finite_values"></a>
## `_finite_values`

拒绝JSON宽松接受的NaN/Infinity及指数溢出。

```python
_finite_values(value, source, locations, path=())
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JSON原生值|是|无|位置或关键字。当前待检查或显示的单个值；诊断不会展开打印整个大容器。|
|`source`|str 或 Path|是|无|位置或关键字。配置的来源文件或显示名称；用于相对路径解释和错误定位，不是业务日志内容。|
|`locations`|Mapping[tuple, [ConfigurationLocation](chronaxis.configuration.models.md#api-ConfigurationLocation)]|是|无|位置或关键字。以字段路径元组为键的只读位置表；只在配置加载期间保留，不随结果逐样本保存。|
|`path`|tuple[str 或 int, ...]|否|()|位置或关键字。从配置根开始的字段键/数组下标序列；只表示当前值的位置，不是操作系统文件路径。|

### 返回说明

None。

### 异常说明

定位到实际值。

源码：[`src/chronaxis/configuration/json_parser.py:82`](../../../src/chronaxis/configuration/json_parser.py#L82)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-parse_json"></a>
## `parse_json`

按标准JSON加载并附准确位置。

```python
parse_json(text, source)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。要处理的配置文本或字段路径文本；不会作为Python代码执行。|
|`source`|str 或 Path|是|无|位置或关键字。配置的来源文件或显示名称；用于相对路径解释和错误定位，不是业务日志内容。|

### 返回说明

数据和位置表。

### 异常说明

ConfigurationError。

源码：[`src/chronaxis/configuration/json_parser.py:92`](../../../src/chronaxis/configuration/json_parser.py#L92)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
