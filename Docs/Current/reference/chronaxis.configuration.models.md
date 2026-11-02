# chronaxis.configuration.models

配置加载期的原生数据、字段位置和语法错误，不参与分析执行或来源读取。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`field_path_text`](#api-field_path_text)|把键/数组下标路径变成无歧义文本。|
|[`ConfigurationLocation`](#api-ConfigurationLocation)|一处源码位置；行列从1开始，列按Unicode字符计，不按UTF-8字节计。|
|[`ConfigurationOrigin`](#api-ConfigurationOrigin)|展开字段的声明位置；只保存文件名、字段路径及行列，不保存第二份配置。|
|[`ConfigurationDocument`](#api-ConfigurationDocument)|只在加载期间持有原生值和必要位置；调用者构造计划后释放本对象。|
|[`ConfigurationDocument.origin_for`](#api-ConfigurationDocument-origin_for)|查最近声明来源并保留缺失字段后缀。|
|[`ConfigurationDocument.location_for`](#api-ConfigurationDocument-location_for)|取具体值位置，缺少字段时回溯最近父对象。|
|[`ConfigurationError`](#api-ConfigurationError)|保存语法错误码、文件和字段位置；消息不打印整份配置或执行任意内容。|
|[`ConfigurationError.__init__`](#api-ConfigurationError-__init__)|建立错误事实。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from collections.abc import Mapping
```

</details>

<a id="api-field_path_text"></a>
## `field_path_text`

把键/数组下标路径变成无歧义文本。

```python
field_path_text(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|tuple[str 或 int, ...]|是|无|位置或关键字。从配置根开始的字段键/数组下标序列；只表示当前值的位置，不是操作系统文件路径。|

### 返回说明

JSON路径。

### 异常说明

非内部路径。

源码：[`src/chronaxis/configuration/models.py:7`](../../../src/chronaxis/configuration/models.py#L7)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ConfigurationLocation"></a>
## `ConfigurationLocation`

一处源码位置；行列从1开始，列按Unicode字符计，不按UTF-8字节计。

```python
class ConfigurationLocation
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`line`|int|是|无|原配置中从1开始的行号；报错时用于直接找到出错声明。|
|`column`|int|是|无|原行中从1开始的Unicode字符列号；不是UTF-8字节列号。|

源码：[`src/chronaxis/configuration/models.py:21`](../../../src/chronaxis/configuration/models.py#L21)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ConfigurationOrigin"></a>
## `ConfigurationOrigin`

展开字段的声明位置；只保存文件名、字段路径及行列，不保存第二份配置。

```python
class ConfigurationOrigin
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|实际声明文件的按声明目录形成的绝对路径（不解析链接真实目标）。|
|`field_path`|tuple|是|无|声明文件内部路径，索引尚未被合并重排。|
|`location`|[ConfigurationLocation](chronaxis.configuration.models.md#api-ConfigurationLocation) &#124; None|是|无|原文一基行列；无法取得时为None。|

源码：[`src/chronaxis/configuration/models.py:28`](../../../src/chronaxis/configuration/models.py#L28)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ConfigurationDocument"></a>
## `ConfigurationDocument`

只在加载期间持有原生值和必要位置；调用者构造计划后释放本对象。

```python
class ConfigurationDocument
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|JSON原生配置对象|是|无|当前入口的原生配置内容；只支持文本键及有限数值，结构由现有计划模型校验。|
|`source`|str 或 Path|是|无|配置的来源文件或显示名称；用于相对路径解释和错误定位，不是业务日志内容。|
|`format`|str|是|无|文本格式；配置只接受json或yaml，不能用格式选择转换旧结构版本。|
|`locations`|Mapping[tuple, [ConfigurationLocation](chronaxis.configuration.models.md#api-ConfigurationLocation)]|是|无|以字段路径元组为键的只读位置表；只在配置加载期间保留，不随结果逐样本保存。|
|`origins`|Mapping|否|{}|仅文件导入展开时填充，计划构造后释放。|

源码：[`src/chronaxis/configuration/models.py:36`](../../../src/chronaxis/configuration/models.py#L36)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ConfigurationDocument-origin_for"></a>
### `ConfigurationDocument.origin_for`

查最近声明来源并保留缺失字段后缀。

```python
ConfigurationDocument.origin_for(field_path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`field_path`|tuple[str &#124; int, ...]|是|无|位置或关键字。字段键和数组索引组成的内部路径，根为()；不执行其中的文本。|

#### 返回说明

来源或None。

#### 异常说明

无。

源码：[`src/chronaxis/configuration/models.py:44`](../../../src/chronaxis/configuration/models.py#L44)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ConfigurationDocument-location_for"></a>
### `ConfigurationDocument.location_for`

取具体值位置，缺少字段时回溯最近父对象。

```python
ConfigurationDocument.location_for(field_path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`field_path`|tuple[str 或 int, ...]|是|无|位置或关键字。从根开始的文本键和整数下标序列；找不到具体缺失键时回溯最近父对象的位置。|

#### 返回说明

位置或None。

#### 异常说明

无。

源码：[`src/chronaxis/configuration/models.py:55`](../../../src/chronaxis/configuration/models.py#L55)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ConfigurationError"></a>
## `ConfigurationError`

保存语法错误码、文件和字段位置；消息不打印整份配置或执行任意内容。

```python
ConfigurationError(source, field_path, location, code, message)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/configuration/models.py:63`](../../../src/chronaxis/configuration/models.py#L63)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ConfigurationError-__init__"></a>
### `ConfigurationError.__init__`

建立错误事实。

```python
ConfigurationError.__init__(source, field_path, location, code, message)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str 或 Path|是|无|位置或关键字。配置的来源文件或显示名称；用于相对路径解释和错误定位，不是业务日志内容。|
|`field_path`|tuple[str 或 int, ...]|是|无|位置或关键字。从根开始的文本键和整数下标序列；找不到具体缺失键时回溯最近父对象的位置。|
|`location`|[ConfigurationLocation](chronaxis.configuration.models.md#api-ConfigurationLocation) 或 None|是|无|位置或关键字。解析器可证明的原行列；None表示没有可靠位置，不能填入猜测行号。|
|`code`|str|是|无|位置或关键字。稳定的错误分类代码，例如duplicate_key；供程序判断问题类型，不依赖中文消息。|
|`message`|str|是|无|位置或关键字。说明为什么拒绝当前字段的文字；保留原条件，不把未知项自动改成猜测值。|

#### 返回说明

None。

#### 异常说明

无。

源码：[`src/chronaxis/configuration/models.py:66`](../../../src/chronaxis/configuration/models.py#L66)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
