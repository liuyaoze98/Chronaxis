# `chronaxis.sources.raw_can`

保存原始CAN记录及位置；文本用物理行，BLF用记录序号。

文本解析器输出RawCANRecord：整数纳秒供分析，LegacyRawFrame仅复用已有报文
字段模型供后续DBC和写出接口使用。其float秒是兼容表示，不替代精确时间。
本模块不打开文件、不加载DBC、不生成信号，CAN身份不会进入通用时序核心。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`CANTextError`](#api-CANTextError)|表示具体文本文件某物理行不能解释为所选版本的报文。|
|[`CANTextError.__init__`](#api-CANTextError-__init__)|保留可程序读取的位置。|
|[`RawCANRecord`](#api-RawCANRecord)|保存一次真实输入；文本直接转纳秒，BLF沿用读取库的浮点秒转换。|
|[`RawCANRecord.__post_init__`](#api-RawCANRecord-__post_init__)|检查定位和快照。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from pathlib import Path
from ..legacy.records import LegacyRawFrame
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-CANTextError"></a>
## `CANTextError`

表示具体文本文件某物理行不能解释为所选版本的报文。

```python
CANTextError(path, line_number, reason)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/sources/raw_can.py:15`](../../../src/chronaxis/sources/raw_can.py#L15)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANTextError-__init__"></a>
### `CANTextError.__init__`

保留可程序读取的位置。

```python
CANTextError.__init__(path, line_number, reason)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。发生格式错误的原始文本文件路径，写入错误定位信息。|
|`line_number`|int|是|无|位置或关键字。错误所在的物理行号，从1开始，包括文件头和空行所占行数。|
|`reason`|str|是|无|位置或关键字。该行无法解析的具体原因，例如字段不足或帧长度不匹配。|

#### 返回说明

定位异常。

#### 异常说明

无；不包含整行私人载荷或隐式记录日志。

源码：[`src/chronaxis/sources/raw_can.py:18`](../../../src/chronaxis/sources/raw_can.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RawCANRecord"></a>
## `RawCANRecord`

保存一次真实输入；文本直接转纳秒，BLF沿用读取库的浮点秒转换。

```python
class RawCANRecord
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)|是|无|原帧公开字段，通道统一从0开始。|
|`time_ns`|int|是|无|按明确参考原点解释后的精确int64纳秒。|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|实际读取文件，不声明为绝对路径或内容指纹。|
|`line_number`|int &#124; None|是|无|文本物理行；二进制BLF没有行号，使用sequence定位。|
|`sequence`|int|是|无|同次读取从0开始，允许同时间不同载荷。|
|`raw_time`|str &#124; None|是|无|仅原文诊断请求保留；普通计算为None。|
|`parser_version`|str|是|无|固定格式版本，不在半途自动切换。|
|`dlc_code`|int &#124; None|是|无|真正DLC编码，错误帧没有该值。|
|`time_quantized`|bool|否|False|文本比纳秒更细时的实际舍入事实。|
|`source_time_ns`|int &#124; None|否|None|显式平移前的精确时间；手工旧构造省略时与time_ns相同。|

源码：[`src/chronaxis/sources/raw_can.py:30`](../../../src/chronaxis/sources/raw_can.py#L30)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RawCANRecord-__post_init__"></a>
### `RawCANRecord.__post_init__`

检查定位和快照。

```python
RawCANRecord.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、时间或位置错误。

本函数直接报告的具体错误：

- `TypeError`：文本CAN记录需要原帧快照和Path。
- `ValueError`：文本CAN位置需要正物理行和非负序号。
- `ValueError`：文本CAN记录需要时间原文、版本和量化标志。
- `ValueError`：DLC编码需0到15或None。

源码：[`src/chronaxis/sources/raw_can.py:44`](../../../src/chronaxis/sources/raw_can.py#L44)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
