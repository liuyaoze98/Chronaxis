# `chronaxis.legacy.vendor.sclicer_functions_v1.utils`

保留的Sclicer专用ASC读取与时间工具，用于历史链和行为核对。M3公共ASC入口使用独立sources.asc，不调用此旧解析器；这里列全旧定义供维护者查阅。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`ASCReaderForCANFD`](#api-ASCReaderForCANFD)|通用CAN FD ASC文件解析器|
|[`ASCReaderForCANFD.__init__`](#api-ASCReaderForCANFD-__init__)|初始化解析器|
|[`ASCReaderForCANFD._initialize_patterns`](#api-ASCReaderForCANFD-_initialize_patterns)|初始化支持的多种正则表达式模式|
|[`ASCReaderForCANFD._detect_format`](#api-ASCReaderForCANFD-_detect_format)|自动检测ASC文件的格式|
|[`ASCReaderForCANFD._record_pattern_info`](#api-ASCReaderForCANFD-_record_pattern_info)|记录匹配模式的信息，用于后续解析|
|[`ASCReaderForCANFD.__iter__`](#api-ASCReaderForCANFD-__iter__)|迭代器接口，生成can.Message对象|
|[`ASCReaderForCANFD._parse_line`](#api-ASCReaderForCANFD-_parse_line)|解析单行CAN FD报文，尝试多种格式|
|[`ASCReaderForCANFD._parse_with_pattern`](#api-ASCReaderForCANFD-_parse_with_pattern)|使用指定的正则表达式模式解析行|
|[`ASCReaderForCANFD._parse_with_generic_split`](#api-ASCReaderForCANFD-_parse_with_generic_split)|基于空格分割的通用解析方法，作为最后的尝试|
|[`ASCReaderForCANFD.add_custom_pattern`](#api-ASCReaderForCANFD-add_custom_pattern)|添加自定义正则表达式模式|
|[`ASCReaderForCANFD._parse_header`](#api-ASCReaderForCANFD-_parse_header)|解析文件头的日期与时间戳模式，使行为与 can.ASCReader 保持一致|
|[`ASCReaderForCANFD._apply_header_timestamp`](#api-ASCReaderForCANFD-_apply_header_timestamp)|根据头部策略调整时间戳：absolute 时叠加基准（若存在），relative 保持原值|

## 导出名称

`ASCReaderForCANFD`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from typing import Generator, List, Dict, Any, Optional, Tuple
from datetime import datetime
```

</details>

<a id="api-ASCReaderForCANFD"></a>
## `ASCReaderForCANFD`

通用CAN FD ASC文件解析器
支持多种格式的CAN FD ASC文件，自动适应不同的数据布局
生成与python-can兼容的Message对象

```python
ASCReaderForCANFD(file_path: str, relative_timestamp: bool=False, format_hint: str='auto')
```


源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:11`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L11)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-__init__"></a>
### `ASCReaderForCANFD.__init__`

初始化解析器

```python
ASCReaderForCANFD.__init__(file_path: str, relative_timestamp: bool=False, format_hint: str='auto')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`file_path`|str|是|无|位置或关键字。ASC文件路径|
|`relative_timestamp`|bool|否|False|位置或关键字。是否使用相对时间戳|
|`format_hint`|str|否|'auto'|位置或关键字。格式提示，可选值：'auto'（自动检测）、'standard'（标准格式）、'custom'（自定义格式）|

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:18`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-_initialize_patterns"></a>
### `ASCReaderForCANFD._initialize_patterns`

初始化支持的多种正则表达式模式

```python
ASCReaderForCANFD._initialize_patterns() -> List[re.Pattern]
```

参数：无显式参数。


返回类型：List[re.Pattern]。

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:46`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L46)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-_detect_format"></a>
### `ASCReaderForCANFD._detect_format`

自动检测ASC文件的格式

```python
ASCReaderForCANFD._detect_format()
```

参数：无显式参数。


源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:72`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L72)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-_record_pattern_info"></a>
### `ASCReaderForCANFD._record_pattern_info`

记录匹配模式的信息，用于后续解析

```python
ASCReaderForCANFD._record_pattern_info(match: re.Match)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`match`|re.Match|是|无|位置或关键字。已匹配ASC行的正则Match对象，用于登记本次可复用字段位置。|

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:96`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L96)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-__iter__"></a>
### `ASCReaderForCANFD.__iter__`

迭代器接口，生成can.Message对象

```python
ASCReaderForCANFD.__iter__() -> Generator[can.Message, None, None]
```

参数：无显式参数。


返回类型：Generator[can.Message, None, None]。

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:103`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L103)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-_parse_line"></a>
### `ASCReaderForCANFD._parse_line`

解析单行CAN FD报文，尝试多种格式

```python
ASCReaderForCANFD._parse_line(line: str) -> Optional[can.Message]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`line`|str|是|无|位置或关键字。单行CAN FD报文数据|

#### 返回说明

can.Message: 解析后的CAN消息对象，解析失败返回None

返回类型：Optional[can.Message]。

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:121`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L121)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-_parse_with_pattern"></a>
### `ASCReaderForCANFD._parse_with_pattern`

使用指定的正则表达式模式解析行

```python
ASCReaderForCANFD._parse_with_pattern(line: str, pattern: re.Pattern) -> Optional[can.Message]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`line`|str|是|无|位置或关键字。当前原ASC文本行，保留原格式交给此解析分支。|
|`pattern`|re.Pattern|是|无|位置或关键字。尝试解析当前ASC行的正则表达式模式。|

返回类型：Optional[can.Message]。

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:149`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L149)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-_parse_with_generic_split"></a>
### `ASCReaderForCANFD._parse_with_generic_split`

基于空格分割的通用解析方法，作为最后的尝试
增强点：
- 支持以"*"开头的行（星号前缀）
- 支持时分秒时间戳 "HH:MM:SS.mmm"
- 支持日期+时间前缀 "YYYY.MM.DD HH:MM:SS.mmm"
- 兼容有/无 CANFD 关键字

```python
ASCReaderForCANFD._parse_with_generic_split(line: str) -> Optional[can.Message]
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`line`|str|是|无|位置或关键字。当前原ASC文本行，保留原格式交给此解析分支。|

返回类型：Optional[can.Message]。

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:239`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L239)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-add_custom_pattern"></a>
### `ASCReaderForCANFD.add_custom_pattern`

添加自定义正则表达式模式

```python
ASCReaderForCANFD.add_custom_pattern(pattern: str) -> bool
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pattern`|str|是|无|位置或关键字。正则表达式字符串|

#### 返回说明

bool: 添加是否成功

返回类型：bool。

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:379`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L379)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-_parse_header"></a>
### `ASCReaderForCANFD._parse_header`

解析文件头的日期与时间戳模式，使行为与 can.ASCReader 保持一致

```python
ASCReaderForCANFD._parse_header() -> None
```

参数：无显式参数。


返回类型：None。

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:398`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L398)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-ASCReaderForCANFD-_apply_header_timestamp"></a>
### `ASCReaderForCANFD._apply_header_timestamp`

根据头部策略调整时间戳：absolute 时叠加基准（若存在），relative 保持原值

```python
ASCReaderForCANFD._apply_header_timestamp(ts: float) -> float
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ts`|float|是|无|位置或关键字。当前解析出的秒时间戳；absolute头策略可加基准，relative保持原值。|

返回类型：float。

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py:438`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/utils.py#L438)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
