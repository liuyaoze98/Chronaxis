# `chronaxis.configuration.yaml_parser`

通过独立纯Python安全解析器读取YAML1.2受限子集，不构造任意标签对象。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ConfigurationError](chronaxis.configuration.models.md#api-ConfigurationError)、[ConfigurationLocation](chronaxis.configuration.models.md#api-ConfigurationLocation)

## 对象导航

|对象|用途|
|---|---|
|[`parse_yaml`](#api-parse_yaml)|用事件流构造一次原生值树。|
|[`parse_yaml.Yaml12`](#api-parse_yaml-Yaml12)|版本在交给依赖校验前受限，避免依赖对1.3等版本抛出AssertionError。|
|[`parse_yaml.Yaml12.version`](#api-parse_yaml-Yaml12-version)|仅接受默认或1.2。|
|[`parse_yaml.location`](#api-parse_yaml-location)|复制事件位置，不让结果引用整份输入文本。|
|[`parse_yaml.reject`](#api-parse_yaml-reject)|抛定位错误。|
|[`parse_yaml.check`](#api-parse_yaml-check)|在构造前拒绝别名、锚点和显式标签。|
|[`parse_yaml.scalar`](#api-parse_yaml-scalar)|仅转换JSON原生标量；日期时间保文本。|
|[`parse_yaml.value`](#api-parse_yaml-value)|递归消费一次事件流并保位置。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from .models import ConfigurationError, ConfigurationLocation
from .json_parser import MAX_DEPTH
```

</details>

<a id="api-parse_yaml"></a>
## `parse_yaml`

用事件流构造一次原生值树。

```python
parse_yaml(text, source)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。要处理的配置文本或字段路径文本；不会作为Python代码执行。|
|`source`|str 或 Path|是|无|位置或关键字。配置的来源文件或显示名称；用于相对路径解释和错误定位，不是业务日志内容。|

### 返回说明

数据和位置表。

### 异常说明

受限语法错误。

源码：[`src/chronaxis/configuration/yaml_parser.py:8`](../../../src/chronaxis/configuration/yaml_parser.py#L8)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_yaml-Yaml12"></a>
### `parse_yaml.Yaml12`

版本在交给依赖校验前受限，避免依赖对1.3等版本抛出AssertionError。

```python
class parse_yaml.Yaml12(YAML)
```

继承关系：YAML。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/configuration/yaml_parser.py:18`](../../../src/chronaxis/configuration/yaml_parser.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_yaml-Yaml12-version"></a>
### `parse_yaml.Yaml12.version`

仅接受默认或1.2。

```python
parse_yaml.Yaml12.version(selected)
```

装饰器：`YAML.version.setter`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`selected`|tuple[int,int]|是|无|位置或关键字。显式YAML版本，仅允许(1,2)；其他版本转成可定位的配置错误，不让依赖抛无说明断言。|

#### 返回说明

None。

#### 异常说明

明确配置版本错误。

源码：[`src/chronaxis/configuration/yaml_parser.py:22`](../../../src/chronaxis/configuration/yaml_parser.py#L22)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_yaml-location"></a>
### `parse_yaml.location`

复制事件位置，不让结果引用整份输入文本。

```python
parse_yaml.location(event)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|ruamel.yaml事件对象|是|无|位置或关键字。安全YAML解析器产生的一个词法事件，包含类型和原位置；不实例化用户自定义对象。|

#### 返回说明

标量位置。

#### 异常说明

无。

源码：[`src/chronaxis/configuration/yaml_parser.py:35`](../../../src/chronaxis/configuration/yaml_parser.py#L35)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_yaml-reject"></a>
### `parse_yaml.reject`

抛定位错误。

```python
parse_yaml.reject(event, path, code, message)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|ruamel.yaml事件对象|是|无|位置或关键字。安全YAML解析器产生的一个词法事件，包含类型和原位置；不实例化用户自定义对象。|
|`path`|tuple[str 或 int, ...]|是|无|位置或关键字。从配置根开始的字段键/数组下标序列；只表示当前值的位置，不是操作系统文件路径。|
|`code`|str|是|无|位置或关键字。稳定的错误分类代码，例如duplicate_key；供程序判断问题类型，不依赖中文消息。|
|`message`|str|是|无|位置或关键字。说明为什么拒绝当前字段的文字；保留原条件，不把未知项自动改成猜测值。|

#### 返回说明

无。

#### 异常说明

ConfigurationError。

源码：[`src/chronaxis/configuration/yaml_parser.py:39`](../../../src/chronaxis/configuration/yaml_parser.py#L39)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_yaml-check"></a>
### `parse_yaml.check`

在构造前拒绝别名、锚点和显式标签。

```python
parse_yaml.check(event, path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|ruamel.yaml事件对象|是|无|位置或关键字。安全YAML解析器产生的一个词法事件，包含类型和原位置；不实例化用户自定义对象。|
|`path`|tuple[str 或 int, ...]|是|无|位置或关键字。从配置根开始的字段键/数组下标序列；只表示当前值的位置，不是操作系统文件路径。|

#### 返回说明

None。

#### 异常说明

定位配置错误。

源码：[`src/chronaxis/configuration/yaml_parser.py:43`](../../../src/chronaxis/configuration/yaml_parser.py#L43)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_yaml-scalar"></a>
### `parse_yaml.scalar`

仅转换JSON原生标量；日期时间保文本。

```python
parse_yaml.scalar(event, path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|ruamel.yaml事件对象|是|无|位置或关键字。安全YAML解析器产生的一个词法事件，包含类型和原位置；不实例化用户自定义对象。|
|`path`|tuple[str 或 int, ...]|是|无|位置或关键字。从配置根开始的字段键/数组下标序列；只表示当前值的位置，不是操作系统文件路径。|

#### 返回说明

原生值。

#### 异常说明

不支持类型或非有限数。

源码：[`src/chronaxis/configuration/yaml_parser.py:49`](../../../src/chronaxis/configuration/yaml_parser.py#L49)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-parse_yaml-value"></a>
### `parse_yaml.value`

递归消费一次事件流并保位置。

```python
parse_yaml.value(event, path=(), depth=0)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|ruamel.yaml事件对象|是|无|位置或关键字。安全YAML解析器产生的一个词法事件，包含类型和原位置；不实例化用户自定义对象。|
|`path`|tuple[str 或 int, ...]|否|()|位置或关键字。从配置根开始的字段键/数组下标序列；只表示当前值的位置，不是操作系统文件路径。|
|`depth`|int|否|0|位置或关键字。当前配置容器嵌套层数；超过共享解析上限64时报错，防止无界递归。|

#### 返回说明

原生值。

#### 异常说明

受限语法或嵌套超限。

源码：[`src/chronaxis/configuration/yaml_parser.py:77`](../../../src/chronaxis/configuration/yaml_parser.py#L77)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
