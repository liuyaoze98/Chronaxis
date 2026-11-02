# chronaxis.sources.can_spec

声明固定旧函数链的有序BLF来源，并保存解码样本的完整CAN定位。

LegacyCANSpec接收首个Path、可选连续paths、一个DBC Path、明确通道、TimebaseSpec和原浮点秒
表示，输出冻结声明；构造只查类型、后缀和纳秒偏移，不open/stat/resolve，不加载
旧模块、CAN库或DBC，也不猜时区、单位、方向、实际观测范围和解码质量。
CANSourceRef在通用会话/来源/field上保留原路径、profile、通道、信号、实际帧型、
yield序号、原浮点秒及时间量化标志。field是ID/信号及可选帧类型的规范JSON，
不能把原名称当DSL变量、隐藏改名、再次施加DBC缩放或声称原物理行号。
仅依赖通用模型和基于标准库的CAN读取记录协议；无文件、子进程、reader或预算生命周期。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 继承字段

- `CANSourceRef`同时继承[SourceRef](chronaxis.core.models.md#api-SourceRef)字段：`session_id`, `source_name`, `field`。构造时须一并提供基类的必填字段；类型、默认值及约束按基类表。

## 相关类型

[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

## 对象导航

|对象|用途|
|---|---|
|[`_nonnegative_integer`](#api-_nonnegative_integer)|检查原生非负通道/序号，不接受bool或外部整数子类替代。|
|[`can_field_from_key`](#api-can_field_from_key)|从严格规范JSON恢复完整原定位，复用CAN定位模型，不解析DBC。|
|[`LegacyCANSpec`](#api-LegacyCANSpec)|冻结有序同格式BLF、单通道和单DBC声明，不认证输入文件或实际旧链能力。|
|[`LegacyCANSpec.input_paths`](#api-LegacyCANSpec-input_paths)|取得原序文件。|
|[`LegacyCANSpec.__post_init__`](#api-LegacyCANSpec-__post_init__)|检查静态来源约束，路径和时基对象均原样保留。|
|[`CANSourceRef`](#api-CANSourceRef)|保留一次原yield对应样本的CAN身份，不替代实际绑定或质量检查。|
|[`CANSourceRef.__post_init__`](#api-CANSourceRef-__post_init__)|校验通用身份与完整原定位相等，不访问路径或重新解码。|
|[`CANSourceRef.evaluation_index`](#api-CANSourceRef-evaluation_index)|提供本次原yield位置的只读别名，明确不声称legacy_sum求值流已存在。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from ..core.models import SourceRef, TimebaseSpec
from ..core.validation import require_identifier, require_text
from ..legacy.records import LegacyCANField, MAX_WIRE_BYTES, PROFILE_ID, decode_packet, field_from_dict
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-_nonnegative_integer"></a>
## `_nonnegative_integer`

检查原生非负通道/序号，不接受bool或外部整数子类替代。

```python
_nonnegative_integer(value, name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。待检查的非负Python整数，不接受bool作为序号或计数。|
|`name`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|

### 返回说明

None，不重编号或转换类型。

### 异常说明

TypeError为非原生int，ValueError为负数；无I/O。

源码：[`src/chronaxis/sources/can_spec.py:22`](../../../src/chronaxis/sources/can_spec.py#L22)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-can_field_from_key"></a>
## `can_field_from_key`

从严格规范JSON恢复完整原定位，复用CAN定位模型，不解析DBC。

```python
can_field_from_key(text)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。text为LegacyCANField.key生成的原生str，UTF-8包不超过65536字节。|

### 返回说明

LegacyCANField，保信号名大小写、点号及可选帧类型，不读取DBC。

### 异常说明

TypeError/ValueError/UnicodeError为类型、JSON、重复键、字段、数值或非规范键；
    不接受仅语义相同但空白、键序或转义不同的文本，不eval或反序列化任意对象。

源码：[`src/chronaxis/sources/can_spec.py:34`](../../../src/chronaxis/sources/can_spec.py#L34)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-LegacyCANSpec"></a>
## `LegacyCANSpec`

冻结有序同格式BLF、单通道和单DBC声明，不认证输入文件或实际旧链能力。

```python
class LegacyCANSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|当前计划来源的安全简单名称，不是DBC消息名。|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|首个BLF声明；不扫描目录，连续文件由paths显式提供。|
|`dbc_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|同次worker原load_file的唯一DBC声明，不在此读取。|
|`channel`|int|是|无|明确单通道，非负原生int，不猜缺失通道。|
|`timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|完整时基声明，来源名称相同不自动证明同步。|
|`unit`|str|否|'s'|原函数返回浮点秒，首版只接受s，不按文件名推断。|
|`offset_ns`|int|否|0|明确int64固定纳秒偏移，不更改原timestamp。|
|`legacy_profile`|str|否|PROFILE_ID|唯一冻结sclicer-functions-v1，不自动回退profile。|
|`decode_scope`|str|否|'requested'|`"requested"`解码本次需要的报文和字段；`"all"`保留全解码与完整诊断。该字段记录或指定的是解码范围。|
|`input_check`|str|否|'auto'|`"auto"`按本计划实际要计算的内容检查输入；`"full"`检查全部原帧及时间，即使某帧不参与指标也检查它。|
|`paths`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), ...]|否|()|显式连续BLF；空tuple沿用path单文件，首项必须等于path。|
|`decode_policy`|str|否|'legacy'|新版本默认strict；旧调用保原宽松解码。|

源码：[`src/chronaxis/sources/can_spec.py:54`](../../../src/chronaxis/sources/can_spec.py#L54)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-LegacyCANSpec-input_paths"></a>
### `LegacyCANSpec.input_paths`

取得原序文件。

```python
LegacyCANSpec.input_paths
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

tuple。

#### 异常说明

无；不扫描目录。

源码：[`src/chronaxis/sources/can_spec.py:72`](../../../src/chronaxis/sources/can_spec.py#L72)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-LegacyCANSpec-__post_init__"></a>
### `LegacyCANSpec.__post_init__`

检查静态来源约束，路径和时基对象均原样保留。

```python
LegacyCANSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无，读取本冻结声明字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError为路径/通道/时基/单位/profile/偏移/解码范围类型错误；ValueError为名称、
    后缀、通道、单位、profile或解码/检查范围不符；OverflowError为offset_ns超出int64。

#### 副作用说明

无open/stat/resolve/DBC/依赖加载，不核实存在性或实际BLF内容。

源码：[`src/chronaxis/sources/can_spec.py:76`](../../../src/chronaxis/sources/can_spec.py#L76)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANSourceRef"></a>
## `CANSourceRef`

保留一次原yield对应样本的CAN身份，不替代实际绑定或质量检查。

继承session_id/source_name/field；实际定位须满足field声明的可选类型约束。
yield_sequence从0开始且保原来源顺序，同一时刻消息不会被去重；不是物理行号。
原timestamp和量化标志同时保留，不用新纳秒坐标覆盖原浮点诊断。

```python
class CANSourceRef(SourceRef)
```

继承关系：[SourceRef](chronaxis.core.models.md#api-SourceRef)。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|原单BLF路径文本，是否真实打开由实际read证明。|
|`profile`|str|是|无|实际固定旧函数链标识。|
|`channel`|int|是|无|明确来源通道。|
|`signal`|str|是|无|原DBC信号名，不裁剪、替换点号或改大小写。|
|`frame_id`|int|是|无|原报文ID，与field一致。|
|`is_extended`|bool|是|无|原定位标准/扩展帧标志。|
|`is_fd`|bool|是|无|原定位经典CAN/FD标志。|
|`yield_sequence`|int|是|无|0起原函数yield序号，不是legacy_sum的历史求值序号。|
|`timestamp`|float|是|无|有限原浮点秒，可保负数和-0.0；精度已损失时不能恢复。|
|`time_quantized`|bool|是|无|显式时间转换是否按纳秒量化，不等于浮点精度完好。|

源码：[`src/chronaxis/sources/can_spec.py:120`](../../../src/chronaxis/sources/can_spec.py#L120)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANSourceRef-__post_init__"></a>
### `CANSourceRef.__post_init__`

校验通用身份与完整原定位相等，不访问路径或重新解码。

```python
CANSourceRef.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，全部原声明保持冻结。

#### 异常说明

TypeError/ValueError/UnicodeError为身份、profile、JSON定位、序号、原时间
    或量化标志非法，或field与附加定位冲突；没有失效补零或隐式别名。

源码：[`src/chronaxis/sources/can_spec.py:139`](../../../src/chronaxis/sources/can_spec.py#L139)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANSourceRef-evaluation_index"></a>
### `CANSourceRef.evaluation_index`

提供本次原yield位置的只读别名，明确不声称legacy_sum求值流已存在。

```python
CANSourceRef.evaluation_index
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

与yield_sequence完全相同的int。

#### 异常说明

无；不产生额外求值或计数。

源码：[`src/chronaxis/sources/can_spec.py:174`](../../../src/chronaxis/sources/can_spec.py#L174)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
