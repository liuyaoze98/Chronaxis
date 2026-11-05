# `chronaxis.configuration.resolution`

按请求生成可独立加载的有效配置；只读配置，不读取业务输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_duration`](#api-_duration)|纳秒用整数文本输出，不经浮点。|
|[`_interval`](#api-_interval)|输出合法间隔对象，不为actual/dbc补伪周期。|
|[`_signal_defaults`](#api-_signal_defaults)|复用当前编译的信号事实，不为导出配置再次读取DBC。|
|[`_analysis_defaults`](#api-_analysis_defaults)|显式化已编译模型的适用默认值。|
|[`resolved_configuration`](#api-resolved_configuration)|展开预设并固定路径。|
|[`resolve_configuration`](#api-resolve_configuration)|显示或导出有效配置。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from . import load_configuration, parse_configuration
from .file_tools import path_fields, validate_document, serialize_configuration, output_format, write_new_configuration
```

</details>

<a id="api-_duration"></a>
## `_duration`

纳秒用整数文本输出，不经浮点。

```python
_duration(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。整数纳秒时长，直接拼接ns单位，避免浮点精度损失。|

### 返回说明

时长str。

### 异常说明

无。

源码：[`src/chronaxis/configuration/resolution.py:10`](../../../src/chronaxis/configuration/resolution.py#L10)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_interval"></a>
## `_interval`

输出合法间隔对象，不为actual/dbc补伪周期。

```python
_interval(choice)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`choice`|IntervalChoice|是|无|位置或关键字。已解析的actual/fixed/dbc计时选择；fixed用整数纳秒写value，dbc不填写虚构周期。|

### 返回说明

dict。

### 异常说明

无。

源码：[`src/chronaxis/configuration/resolution.py:15`](../../../src/chronaxis/configuration/resolution.py#L15)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_signal_defaults"></a>
## `_signal_defaults`

复用当前编译的信号事实，不为导出配置再次读取DBC。

```python
_signal_defaults(raw, plan, *, normalized=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。待输出当前公共配置副本。|
|`plan`|AnalysisPlan|是|无|位置或关键字。已编译计划，提供每条信号的实际默认类型、单位与定位。|
|`normalized`|bool|否|False|仅关键字。normalized表示转换字段已展开为内部平铺形式。|

### 返回说明

None；只补入可重复加载的原类型、单位及映射。

### 异常说明

KeyError为内部配置与计划不匹配；不修改用户原文件。

源码：[`src/chronaxis/configuration/resolution.py:23`](../../../src/chronaxis/configuration/resolution.py#L23)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_analysis_defaults"></a>
## `_analysis_defaults`

显式化已编译模型的适用默认值。

```python
_analysis_defaults(raw, plan)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。由原配置复制得到的可修改对象；显式填默认只改这个副本，不写回用户文件。|
|`plan`|AnalysisPlan|是|无|位置或关键字。已经静态校验的分析计划；用于提取实际声明、规则和默认值，不执行分析。|

### 返回说明

None。

### 异常说明

内部契约错误。

只填写实际有含义且可重新加载的字段；不猜单位/方向/阈值，不写无关规则参数或DBC周期。

源码：[`src/chronaxis/configuration/resolution.py:45`](../../../src/chronaxis/configuration/resolution.py#L45)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-resolved_configuration"></a>
## `resolved_configuration`

展开预设并固定路径。

```python
resolved_configuration(source, *, defaults=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) 或 str|是|无|位置或关键字。要读取的当前配置文件；以其声明目录固定输入定位，原文件保持不变。|
|`defaults`|bool|否|False|仅关键字。True写出适用的实际默认值与继承政策；False保留原显式项，只展开预设并固定路径。|

### 返回说明

原生配置。

### 异常说明

配置/IO错误。

原配置不写回；省略defaults时保原显式值。公开预设构建器只在独立副本执行。

源码：[`src/chronaxis/configuration/resolution.py:135`](../../../src/chronaxis/configuration/resolution.py#L135)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-resolve_configuration"></a>
## `resolve_configuration`

显示或导出有效配置。

```python
resolve_configuration(source, *, output=None, format=None, defaults=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) 或 str|是|无|位置或关键字。要读取的当前配置文件；以其声明目录固定输入定位，原文件保持不变。|
|`output`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) 或 str|否|None|仅关键字。尚不存在的目标文件或目录；初始化写完整新目录，转换与展开写新文件，已有目标拒绝。|
|`format`|str|否|None|仅关键字。文本格式；配置只接受json或yaml，不能用格式选择转换旧结构版本。|
|`defaults`|bool|否|False|仅关键字。True写出适用的实际默认值与继承政策；False保留原显式项，只展开预设并固定路径。|

### 返回说明

文本或Path。

### 异常说明

配置/IO错误。

无输出文件时默认YAML写给调用者；有文件时扩展名定格式，显式格式不一致则拒绝。

源码：[`src/chronaxis/configuration/resolution.py:172`](../../../src/chronaxis/configuration/resolution.py#L172)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
