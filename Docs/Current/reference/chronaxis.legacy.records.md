# chronaxis.legacy.records

冻结单BLF原公开函数链的报文、解码值、定位和有界IPC协议。

输入为同次can.Message的公开写出字段、原parse_frame返回值与用户定位声明；
输出是冻结dataclass及最大65536字节的JSON包。data以hex无损表达，非有限
解码浮点使用明确标签；不执行eval、pickle或任意模型反序列化，不应用DBC缩放。
本文件只依赖标准库，无来源/DBC读取或进程副作用。父进程承担wire/记录副本预算，
worker在INIT后才加载真实库；记录模型不声称原reader已关闭或旧进程RSS受控。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`normalize_frame_id`](#api-normalize_frame_id)|把配置中的十进制、十六进制或二进制ID转成一次可复用的整数。|
|[`_small_item_fits`](#api-_small_item_fits)|证明已核原字段的小ITEM符合原限额；不能证明时返回False，不拒绝输入。|
|[`_integer`](#api-_integer)|检查原生整数边界，bool不能充当序号、通道或ID。|
|[`_text`](#api-_text)|检查有限非空原文本，不将DBC名称改成表达式标识符。|
|[`_shape`](#api-_shape)|校验wire字典精确字段，拒绝额外对象标签或丢失字段。|
|[`LegacyRawFrame`](#api-LegacyRawFrame)|保留同次原msg全部公开写出字段，不重构消息或推断DBC质量。|
|[`LegacyRawFrame.__post_init__`](#api-LegacyRawFrame-__post_init__)|校验公开字段类型，不补帧、缩放或改变原顺序。|
|[`LegacyDecodedFrame`](#api-LegacyDecodedFrame)|保存一次原yield和一次parse的结果，values独立只读且保留非有限诊断值。|
|[`LegacyDecodedFrame.__post_init__`](#api-LegacyDecodedFrame-__post_init__)|冻结原数值映射，不把缺键或非有限浮点替换为零。|
|[`StoredRawFrame`](#api-StoredRawFrame)|为首次读取保存原frame与分析坐标，供后续导出从新暂存回读。|
|[`StoredRawFrame.__post_init__`](#api-StoredRawFrame-__post_init__)|检查原序号和新分析坐标，拒绝越界或替代模型。|
|[`LegacyCANField`](#api-LegacyCANField)|按通道、ID和信号定位；可选帧类型由运行时实际记录消除歧义。|
|[`LegacyCANField.__post_init__`](#api-LegacyCANField-__post_init__)|校验定位形状，实际唯一性由worker同次公开DBC元数据核实。|
|[`LegacyCANField.key`](#api-LegacyCANField-key)|提供稳定原定位键，供新绑定层引用；不改signal名称。|
|[`LegacyCANRequest`](#api-LegacyCANRequest)|声明单BLF、单DBC和有限原定位；构造只校验模型，不访问文件。|
|[`LegacyCANRequest.__post_init__`](#api-LegacyCANRequest-__post_init__)|拒绝替代路径/定位及重复完整定位，保留原tuple顺序。|
|[`LegacyCANRequest.profile`](#api-LegacyCANRequest-profile)|读取唯一受支持profile。|
|[`frame_to_dict`](#api-frame_to_dict)|将原frame编码为固定JSON字段，data_hex不丢失任一字节。|
|[`frame_from_dict`](#api-frame_from_dict)|只从固定字段重建原frame，不加载任意类或调用CAN构造器。|
|[`_value_to_wire`](#api-_value_to_wire)|给非有限原解码float明确标签，有限数字和bool保原类型。|
|[`_value_from_wire`](#api-_value_from_wire)|恢复固定非有限标签，拒绝裸NaN和任意标签对象。|
|[`decoded_to_dict`](#api-decoded_to_dict)|编码一次原yield的完整解码记录，不投影或过滤返回键。|
|[`decoded_from_dict`](#api-decoded_from_dict)|重建单次原返回，空dict与非有限诊断均保持，不猜解码失败原因。|
|[`_decoded_from_checked_dict`](#api-_decoded_from_checked_dict)|在同次严格JSON解包后重建原记录，原值只检查一次后冻结自有字典。|
|[`_try_decoded_small_packet`](#api-_try_decoded_small_packet)|解析并证明常见完整decoded小包合法，不能证明时返回None交回原入口。|
|[`_decoded_from_packet`](#api-_decoded_from_packet)|在同次专用decoded包解析中复用小包证明，保原完整入口的输出及错误顺序。|
|[`field_to_dict`](#api-field_to_dict)|按唯一定位合同输出原字段，不带样本或隐式别名。|
|[`field_from_dict`](#api-field_from_dict)|只构建固定定位模型，不接受多余元数据或对象标签。|
|[`_scalar_size`](#api-_scalar_size)|计算原生JSON标量字节，普通标量直接计数，复杂文本仍交原JSON编码器。|
|[`_decoded_entry_size`](#api-_decoded_entry_size)|在插入新values字典前核单项完整wire成本，保0/False和非有限原值。|
|[`_decoded_values_size`](#api-_decoded_values_size)|不复制Mapping先预检全部解码值，累计成本限制无界或动态items前缀。|
|[`_wire_tree`](#api-_wire_tree)|在JSON复制前累计精确包大小，嵌套子树共享剩余额度而非各自重置上限。|
|[`encode_packet`](#api-encode_packet)|编码最大65536字节的单个JSON对象包，不带换行或pickle。|
|[`_unique_object`](#api-_unique_object)|拒绝重复JSON键，防止后值覆盖已核过的协议字段。|
|[`_reject_constant`](#api-_reject_constant)|拒绝NaN/Infinity非标准JSON常量。|
|[`decode_packet`](#api-decode_packet)|从有界JSON bytes校验包形状，不反序列化任意Python对象。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite, isnan
from pathlib import Path
from re import fullmatch
from types import MappingProxyType
```

</details>

<a id="api-normalize_frame_id"></a>
## `normalize_frame_id`

把配置中的十进制、十六进制或二进制ID转成一次可复用的整数。

```python
normalize_frame_id(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; str|是|无|位置或关键字。原生整数或进制字符串；0x/0X为十六进制，0b/0B为二进制，无前缀为十进制，010表示10。构造后保存0至0x1FFFFFFF的整数；拒绝bool、float、负数、加号、下划线及0o前缀。|

### 返回说明

原生int，范围0至0x1FFFFFFF。

### 异常说明

TypeError：bool、float及其他类型；ValueError：前缀、数字格式或范围非法。

### 副作用说明

无；不用于ASC等原始文件的专有进制解析。

源码：[`src/chronaxis/legacy/records.py:27`](../../../src/chronaxis/legacy/records.py#L27)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_small_item_fits"></a>
## `_small_item_fits`

证明已核原字段的小ITEM符合原限额；不能证明时返回False，不拒绝输入。

```python
_small_item_fits(values, sequence, channel)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|dict|是|无|位置或关键字。values已确认为Mapping|
|`sequence`|int|是|无|位置或关键字。sequence已核原生非负int|
|`channel`|int &#124; str|是|无|位置或关键字。channel已核原帧类型。     同次原帧的有限float时间、29bit ID、DLC/data不超过64及七个bool也须已核。|

### 返回说明

bool。True表示完整原生dict均已检查且整个ITEM的保守上界不超过65536。

### 异常说明

取消、分配失败或原生dict并发变化等运行时错误原样传播，不伪装成正常回退。

### 边界说明

只接受非空原生ASCII键及原生bool、有限float或绝对值不超过64bit的int。
    非有限诊断、Unicode、大整数和近限额记录都交回原精确路径；不复制或缓存值。

源码：[`src/chronaxis/legacy/records.py:68`](../../../src/chronaxis/legacy/records.py#L68)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_integer"></a>
## `_integer`

检查原生整数边界，bool不能充当序号、通道或ID。

```python
_integer(value, name, minimum=0, maximum=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。待检查的Python整数；拒绝bool，并按minimum、maximum检查范围。|
|`name`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|
|`minimum`|int|否|0|位置或关键字。minimum/maximum为含端点范围，None无上界。|
|`maximum`|int &#124; None|否|None|位置或关键字。可接受的最大数值，包含该上限；None表示没有上限。|

### 返回说明

原int。

### 异常说明

TypeError为非int，ValueError为超范围；无转换或I/O。

源码：[`src/chronaxis/legacy/records.py:121`](../../../src/chronaxis/legacy/records.py#L121)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_text"></a>
## `_text`

检查有限非空原文本，不将DBC名称改成表达式标识符。

```python
_text(value, name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。待检查的文本字段，需满足本协议的非空和长度要求。|
|`name`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|

### 返回说明

原str。

### 异常说明

TypeError/ValueError为类型、空文本或超过单包字符上限；不改大小写/空格。

源码：[`src/chronaxis/legacy/records.py:134`](../../../src/chronaxis/legacy/records.py#L134)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_shape"></a>
## `_shape`

校验wire字典精确字段，拒绝额外对象标签或丢失字段。

```python
_shape(value, names, name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。待检查的协议对象，要求原生dict且字段名与names完全一致。|
|`names`|set[str] &#124; tuple[str, ...]|是|无|位置或关键字。该协议对象的完整字段名集合，用来检查缺项和多余字段。|
|`name`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|

### 返回说明

原dict。

### 异常说明

TypeError/ValueError为容器或字段不符。

源码：[`src/chronaxis/legacy/records.py:147`](../../../src/chronaxis/legacy/records.py#L147)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyRawFrame"></a>
## `LegacyRawFrame`

保留同次原msg全部公开写出字段，不重构消息或推断DBC质量。

```python
class LegacyRawFrame
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`timestamp`|float|是|无|原浮点秒；有限性不代表上游精度可恢复。|
|`arbitration_id`|int|是|无|原29位以内报文ID，不把channel拼进ID。|
|`is_extended_id`|bool|是|无|原标准/扩展帧标志。|
|`is_remote_frame`|bool|是|无|原远程帧标志，不按投影滤掉。|
|`is_error_frame`|bool|是|无|原错误帧标志。|
|`channel`|int &#124; str &#124; None|是|无|原公开通道值，不猜缺失通道。|
|`dlc`|int|是|无|原公开DLC，不根据data长度重算。|
|`data`|bytes|是|无|原payload的独立无损bytes副本。|
|`is_fd`|bool|是|无|原CAN FD标志。|
|`is_rx`|bool &#124; None|是|无|原收发方向；CSV未提供时为None，不能据此导出Rx/Tx。|
|`bitrate_switch`|bool|是|无|原FD速率切换标志。|
|`error_state_indicator`|bool|是|无|原FD错误状态指示。|

源码：[`src/chronaxis/legacy/records.py:161`](../../../src/chronaxis/legacy/records.py#L161)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyRawFrame-__post_init__"></a>
### `LegacyRawFrame.__post_init__`

校验公开字段类型，不补帧、缩放或改变原顺序。

```python
LegacyRawFrame.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为非法字段或超过CAN最大payload。

本函数直接报告的具体错误：

- `ValueError`：原报文timestamp需要有限float秒。
- `ValueError`：原报文data需要不超过64字节的bytes。
- `TypeError`：原报文channel需要int/str/None。
- `ValueError`：原报文channel文本过长。

源码：[`src/chronaxis/legacy/records.py:177`](../../../src/chronaxis/legacy/records.py#L177)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyDecodedFrame"></a>
## `LegacyDecodedFrame`

保存一次原yield和一次parse的结果，values独立只读且保留非有限诊断值。

```python
class LegacyDecodedFrame
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|本次来源从0开始的原yield序号，不是物理文件行号。|
|`frame`|[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)|是|无|同次原msg公开快照。|
|`values`|Mapping[str, int &#124; float &#124; bool]|是|无|原返回字典，空dict不推断错误原因。|

源码：[`src/chronaxis/legacy/records.py:201`](../../../src/chronaxis/legacy/records.py#L201)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyDecodedFrame-__post_init__"></a>
### `LegacyDecodedFrame.__post_init__`

冻结原数值映射，不把缺键或非有限浮点替换为零。

```python
LegacyDecodedFrame.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为序号、frame或数值类型错误。

本函数直接报告的具体错误：

- `TypeError`：解码记录需要LegacyRawFrame与数值Mapping。

源码：[`src/chronaxis/legacy/records.py:208`](../../../src/chronaxis/legacy/records.py#L208)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-StoredRawFrame"></a>
## `StoredRawFrame`

为首次读取保存原frame与分析坐标，供后续导出从新暂存回读。

```python
class StoredRawFrame
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|原yield顺序，含同一时刻不同消息。|
|`time_ns`|int|是|无|明确映射后的int64纳秒，不改变原frame.timestamp。|
|`frame`|[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)|是|无|原公开写出字段。|

源码：[`src/chronaxis/legacy/records.py:232`](../../../src/chronaxis/legacy/records.py#L232)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-StoredRawFrame-__post_init__"></a>
### `StoredRawFrame.__post_init__`

检查原序号和新分析坐标，拒绝越界或替代模型。

```python
StoredRawFrame.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为字段或int64范围不符。

本函数直接报告的具体错误：

- `TypeError`：原始暂存需要LegacyRawFrame。

源码：[`src/chronaxis/legacy/records.py:239`](../../../src/chronaxis/legacy/records.py#L239)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANField"></a>
## `LegacyCANField`

按通道、ID和信号定位；可选帧类型由运行时实际记录消除歧义。

```python
class LegacyCANField
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`channel`|int|是|无|内部0基CAN通道，非负整数，须与已解析来源一致；用户配置通道1在此为0，规范定位键仍可为can:0。|
|`signal`|str|是|无|DBC中的原信号名称，区分大小写；不填写报文名称message。|
|`frame_id`|int &#124; str|是|无|原生整数或进制字符串；0x/0X为十六进制，0b/0B为二进制，无前缀为十进制，010表示10。构造后保存0至0x1FFFFFFF的整数；拒绝bool、float、负数、加号、下划线及0o前缀。 Python构造器接受两种输入；对象建立后该属性为int。|
|`is_extended`|bool &#124; None|否|None|None表示未限定，运行时结合DBC及实际帧识别；False限定标准帧且ID不超过0x7FF，True限定扩展帧。Python允许None表达省略，JSON/YAML填写时只能是布尔值。|
|`is_fd`|bool &#124; None|否|None|None表示未限定，按日志实际帧匹配；False限定经典CAN，True限定CAN FD。DBC为FD而实际为经典CAN可按已批准规则兼容，不修改真实帧。JSON/YAML填写时只能是布尔值。|

源码：[`src/chronaxis/legacy/records.py:251`](../../../src/chronaxis/legacy/records.py#L251)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANField-__post_init__"></a>
### `LegacyCANField.__post_init__`

校验定位形状，实际唯一性由worker同次公开DBC元数据核实。

```python
LegacyCANField.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError：类型不是原生整数/字符串或布尔值；ValueError：ID格式、范围、标准帧上限或信号名非法。省略的帧型为None，允许留待运行时识别。

源码：[`src/chronaxis/legacy/records.py:260`](../../../src/chronaxis/legacy/records.py#L260)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANField-key"></a>
### `LegacyCANField.key`

提供稳定原定位键，供新绑定层引用；不改signal名称。

```python
LegacyCANField.key
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

规范紧凑JSON str。

#### 异常说明

原json编码错误；无I/O或DBC查询。

源码：[`src/chronaxis/legacy/records.py:274`](../../../src/chronaxis/legacy/records.py#L274)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANRequest"></a>
## `LegacyCANRequest`

声明单BLF、单DBC和有限原定位；构造只校验模型，不访问文件。

```python
class LegacyCANRequest
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`input_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|原BLF路径，不在模型中resolve或新增扫描。|
|`dbc_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|只供worker一次原load_file。|
|`fields`|tuple[[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField), ...]|是|无|空tuple可原样读取全部帧，不省decode。|

源码：[`src/chronaxis/legacy/records.py:283`](../../../src/chronaxis/legacy/records.py#L283)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANRequest-__post_init__"></a>
### `LegacyCANRequest.__post_init__`

拒绝替代路径/定位及重复完整定位，保留原tuple顺序。

```python
LegacyCANRequest.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为路径类型或重复定位错误。

本函数直接报告的具体错误：

- `TypeError`：原CAN请求路径需要Path。
- `TypeError`：原CAN请求fields需要LegacyCANField tuple。
- `ValueError`：原CAN定位数量超过wire能力。
- `ValueError`：原CAN请求完整定位重复。
- `ValueError`：原CAN路径超过wire能力。

源码：[`src/chronaxis/legacy/records.py:290`](../../../src/chronaxis/legacy/records.py#L290)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyCANRequest-profile"></a>
### `LegacyCANRequest.profile`

读取唯一受支持profile。

```python
LegacyCANRequest.profile
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

固定str。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/records.py:316`](../../../src/chronaxis/legacy/records.py#L316)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-frame_to_dict"></a>
## `frame_to_dict`

将原frame编码为固定JSON字段，data_hex不丢失任一字节。

```python
frame_to_dict(frame)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)|是|无|位置或关键字。frame为LegacyRawFrame。|

### 返回说明

新dict。

### 异常说明

TypeError为非法模型。

本函数直接报告的具体错误：

- `TypeError`：需要LegacyRawFrame。

源码：[`src/chronaxis/legacy/records.py:322`](../../../src/chronaxis/legacy/records.py#L322)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-frame_from_dict"></a>
## `frame_from_dict`

只从固定字段重建原frame，不加载任意类或调用CAN构造器。

```python
frame_from_dict(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。decode_packet得到的原帧字段字典，构造LegacyFrame前逐项检查类型和范围。|

### 返回说明

LegacyRawFrame。

### 异常说明

TypeError/ValueError为形状、hex或原frame字段非法。

本函数直接报告的具体错误：

- `ValueError`：data_hex需要不超过64字节的完整hex。

源码：[`src/chronaxis/legacy/records.py:332`](../../../src/chronaxis/legacy/records.py#L332)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_value_to_wire"></a>
## `_value_to_wire`

给非有限原解码float明确标签，有限数字和bool保原类型。

```python
_value_to_wire(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; bool|是|无|位置或关键字。一个原始解码值；非有限浮点数编码成诊断对象，避免产生非标准JSON数值。|

### 返回说明

JSON标量或diagnostic_float字典。

### 异常说明

TypeError为未支持值；不按数值truthiness丢弃False或0。

本函数直接报告的具体错误：

- `TypeError`：解码wire值仅支持数值或bool。

源码：[`src/chronaxis/legacy/records.py:345`](../../../src/chronaxis/legacy/records.py#L345)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_value_from_wire"></a>
## `_value_from_wire`

恢复固定非有限标签，拒绝裸NaN和任意标签对象。

```python
_value_from_wire(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float &#124; bool &#124; dict|是|无|位置或关键字。JSON数字、布尔值或固定诊断对象；诊断对象恢复原NaN或无穷值以保留质量事实。|

### 返回说明

原生int/float/bool。

### 异常说明

TypeError/ValueError为未知类型、标签或未标记非有限数值。

本函数直接报告的具体错误：

- `TypeError`：解码wire值非法或非有限标签缺失。
- `ValueError`：未知非有限解码标签。

源码：[`src/chronaxis/legacy/records.py:358`](../../../src/chronaxis/legacy/records.py#L358)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-decoded_to_dict"></a>
## `decoded_to_dict`

编码一次原yield的完整解码记录，不投影或过滤返回键。

```python
decoded_to_dict(record)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)|是|无|位置或关键字。record为LegacyDecodedFrame。|

### 返回说明

固定dict。

### 异常说明

TypeError为非法模型；原值编码错误传播。

本函数直接报告的具体错误：

- `TypeError`：需要LegacyDecodedFrame。

源码：[`src/chronaxis/legacy/records.py:374`](../../../src/chronaxis/legacy/records.py#L374)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-decoded_from_dict"></a>
## `decoded_from_dict`

重建单次原返回，空dict与非有限诊断均保持，不猜解码失败原因。

```python
decoded_from_dict(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。完整的已解码帧协议对象，包含原帧和信号值映射。|

### 返回说明

LegacyDecodedFrame。

### 异常说明

TypeError/ValueError为形状或值非法。

本函数直接报告的具体错误：

- `TypeError`：decoded values需要dict。

源码：[`src/chronaxis/legacy/records.py:386`](../../../src/chronaxis/legacy/records.py#L386)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_decoded_from_checked_dict"></a>
## `_decoded_from_checked_dict`

在同次严格JSON解包后重建原记录，原值只检查一次后冻结自有字典。

```python
_decoded_from_checked_dict(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。同次decode_packet刚返回且已检查结构的对象；供消息仓或批次解包复用。|

### 返回说明

LegacyDecodedFrame，原字段、数值类型及非有限诊断按公共入口相同方式恢复。

### 异常说明

原形状、frame、数值、模型限额或分配/取消错误；调用方保持原错误包装。

本函数直接报告的具体错误：

- `TypeError`：decoded values需要dict。
- `TypeError`：解码记录需要LegacyRawFrame与数值Mapping。

### 副作用说明

仅建立本条有界模型；不持有跨调用状态，不读写文件或改变预算。
    清理只断开本模块已结束异常frame的临时引用，保留原异常、诊断与traceback结构。

### 约束说明

首次解包已检查UTF-8、重复键、深度和64KiB；本函数不是独立解析入口，
    不开放trusted参数。公共decoded_from_dict仍独立完整检查，不能改走本路径省略边界。
    本层新建的values只含原生不可变标量，未向外暴露；常见完整值可用保守上界
    证明ITEM不超限，不能证明时沿原精确路径。核完ITEM外壳/全部值
    后可直接冻结，不需要公开构造器为外部可变Mapping设置的第二遍检查和复制。

源码：[`src/chronaxis/legacy/records.py:401`](../../../src/chronaxis/legacy/records.py#L401)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_try_decoded_small_packet"></a>
## `_try_decoded_small_packet`

解析并证明常见完整decoded小包合法，不能证明时返回None交回原入口。

```python
_try_decoded_small_packet(payload)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。payload为本次已预付工作空间内的有界bytes，不借外部JSON树或验证标志。|

### 返回说明

独立冻结的LegacyDecodedFrame；None只表示需走完整原路径，不表示输入非法。

### 异常说明

原JSON/模型错误、MemoryError或取消；外层只对普通错误重走原错误顺序。

### 副作用说明

无I/O、跨行缓存或新预算owner。回退前释放本次临时模型，原错误仅清理
    本模块已结束frame的借入引用；取消及内存错误不重试，不清用户诊断frame。

### 流程说明

保留UTF-8、重复键、裸非有限常量检查及完整frame/sequence校验；只有
    原生ASCII键和有限数值/bool满足完整ITEM保守上界，才省去重复JSON树遍历。
    固定字段结构的深度与标量已由模型核定，ITEM上界也覆盖较小decoded包。
    复杂值、Unicode、近限额等均返回原路径；成功只创建一份frame及自有values。

源码：[`src/chronaxis/legacy/records.py:459`](../../../src/chronaxis/legacy/records.py#L459)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_decoded_from_packet"></a>
## `_decoded_from_packet`

在同次专用decoded包解析中复用小包证明，保原完整入口的输出及错误顺序。

```python
_decoded_from_packet(payload)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。payload为完整decoded JSON bytes，仍受原64KiB及ITEM外壳限制。|

### 返回说明

LegacyDecodedFrame；完整字段、原值类型、量化前时间及非有限诊断不变。

### 异常说明

与decode_packet后接私有构建相同的原错误；MemoryError/取消原样传播。

### 边界说明

普通失败退出except并释放试算对象后，重新由原完整解析/构建决定报错；
    不提前把frame错误置于wire错误前。公共decode_packet及decoded_from_dict不变。

源码：[`src/chronaxis/legacy/records.py:509`](../../../src/chronaxis/legacy/records.py#L509)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-field_to_dict"></a>
## `field_to_dict`

按唯一定位合同输出原字段，不带样本或隐式别名。

```python
field_to_dict(field)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`field`|[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)|是|无|位置或关键字。field为LegacyCANField。|

### 返回说明

固定dict。

### 异常说明

TypeError为非法模型。

本函数直接报告的具体错误：

- `TypeError`：需要LegacyCANField。

源码：[`src/chronaxis/legacy/records.py:531`](../../../src/chronaxis/legacy/records.py#L531)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-field_from_dict"></a>
## `field_from_dict`

只构建固定定位模型，不接受多余元数据或对象标签。

```python
field_from_dict(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。协议中的信号字段描述字典，转换成类型化字段定位。|

### 返回说明

LegacyCANField。

### 异常说明

TypeError/ValueError为形状或字段非法。

源码：[`src/chronaxis/legacy/records.py:541`](../../../src/chronaxis/legacy/records.py#L541)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_scalar_size"></a>
## `_scalar_size`

计算原生JSON标量字节，普通标量直接计数，复杂文本仍交原JSON编码器。

```python
_scalar_size(value, remaining)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str &#124; int &#124; float &#124; bool &#124; None|是|无|位置或关键字。一个JSON标量；计算按协议编码后的字节数，同时检查剩余空间。|
|`remaining`|int|是|无|位置或关键字。当前编码包还可使用的字节数；计算下一项大小时同时检查是否超限。|

### 返回说明

精确UTF-8编码长度。

### 异常说明

TypeError/ValueError/UnicodeError为类型/数值/限额；标量暂态最多单包有限倍数。

本函数直接报告的具体错误：

- `ValueError`：wire包超过65536字节。
- `ValueError`：wire文本超过单包上限。
- `ValueError`：wire整数超过单包能力。
- `TypeError`：wire标量类型不受支持。
- `ValueError`：wire非有限数值必须显式标签。

源码：[`src/chronaxis/legacy/records.py:558`](../../../src/chronaxis/legacy/records.py#L558)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_decoded_entry_size"></a>
## `_decoded_entry_size`

在插入新values字典前核单项完整wire成本，保0/False和非有限原值。

```python
_decoded_entry_size(name, value, remaining)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。原解码信号名，计算它作为JSON键所占的UTF-8字节数。|
|`value`|int &#124; float &#124; bool|是|无|位置或关键字。该信号的原始解码值，按协议标量格式计算字节数。|
|`remaining`|int|是|无|位置或关键字。当前编码包还可使用的字节数；计算下一项大小时同时检查是否超限。|

### 返回说明

键、冒号和值的精确长度。

### 异常说明

原类型、非空名称或wire限额错误。

源码：[`src/chronaxis/legacy/records.py:595`](../../../src/chronaxis/legacy/records.py#L595)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_decoded_values_size"></a>
## `_decoded_values_size`

不复制Mapping先预检全部解码值，累计成本限制无界或动态items前缀。

```python
_decoded_values_size(values, remaining)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|Mapping[str, int &#124; float &#124; bool]|是|无|位置或关键字。信号名到解码值的映射，估算包含键、值和标点的完整编码大小。|
|`remaining`|int|是|无|位置或关键字。当前编码包还可使用的字节数；计算下一项大小时同时检查是否超限。|

### 返回说明

精确值字典长度。

### 异常说明

类型/限额错误，尚未创建values副本。

本函数直接报告的具体错误：

- `ValueError`：解码信号数量超过64KiB wire能力。

源码：[`src/chronaxis/legacy/records.py:606`](../../../src/chronaxis/legacy/records.py#L606)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_wire_tree"></a>
## `_wire_tree`

在JSON复制前累计精确包大小，嵌套子树共享剩余额度而非各自重置上限。

```python
_wire_tree(value, depth=0, remaining=MAX_WIRE_BYTES)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JSON值|是|无|位置或关键字。待编码的字典、列表或原生标量树；递归检查类型、深度和整包字节限制。|
|`depth`|int|否|0|位置或关键字。depth为递归层|
|`remaining`|int|否|MAX_WIRE_BYTES|位置或关键字。当前编码包还可使用的字节数；计算下一项大小时同时检查是否超限。|

### 返回说明

紧凑UTF-8 JSON精确长度。

### 异常说明

TypeError/ValueError为类型/深度/总量；无任意类构建。

本函数直接报告的具体错误：

- `ValueError`：wire嵌套或累计大小超过上限。
- `TypeError`：wire仅接JSON结构，不接任意对象。
- `ValueError`：wire容器超过单包上限。
- `ValueError`：wire包超过65536字节。
- `TypeError`：wire字典键需要str。

源码：[`src/chronaxis/legacy/records.py:621`](../../../src/chronaxis/legacy/records.py#L621)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-encode_packet"></a>
## `encode_packet`

编码最大65536字节的单个JSON对象包，不带换行或pickle。

```python
encode_packet(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。通信包根对象，必须是dict；内部由JSON兼容的字典、列表、标量构成。|

### 返回说明

UTF-8 bytes。

### 异常说明

TypeError/ValueError为类型/非有限/深度/字节上限或JSON编码失败。

本函数直接报告的具体错误：

- `TypeError`：wire包根需要dict。
- `ValueError`：wire包超过65536字节。

源码：[`src/chronaxis/legacy/records.py:658`](../../../src/chronaxis/legacy/records.py#L658)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_unique_object"></a>
## `_unique_object`

拒绝重复JSON键，防止后值覆盖已核过的协议字段。

```python
_unique_object(pairs)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`pairs`|list[tuple[str, object]]|是|无|位置或关键字。JSON解析器按原顺序提供的键值对；先检查是否有重复键，再建立字典，避免同名项被静默覆盖。|

### 返回说明

新dict。

### 异常说明

ValueError为重复字段。

本函数直接报告的具体错误：

- `ValueError`：wire存在重复JSON键。

源码：[`src/chronaxis/legacy/records.py:676`](../../../src/chronaxis/legacy/records.py#L676)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_reject_constant"></a>
## `_reject_constant`

拒绝NaN/Infinity非标准JSON常量。

```python
_reject_constant(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。JSON解析器遇到的NaN、Infinity或-Infinity文本；这些非标准常量会被拒绝。|

### 返回说明

无。

### 异常说明

ValueError总是抛出。

源码：[`src/chronaxis/legacy/records.py:689`](../../../src/chronaxis/legacy/records.py#L689)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-decode_packet"></a>
## `decode_packet`

从有界JSON bytes校验包形状，不反序列化任意Python对象。

```python
decode_packet(payload)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。payload为不超过MAX_WIRE_BYTES的bytes。|

### 返回说明

已校验dict。

### 异常说明

TypeError/ValueError/UnicodeError为类型、大小、格式或结构非法。

本函数直接报告的具体错误：

- `ValueError`：wire包需要1至65536字节的bytes。
- `TypeError`：wire包根需要dict。

源码：[`src/chronaxis/legacy/records.py:697`](../../../src/chronaxis/legacy/records.py#L697)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
