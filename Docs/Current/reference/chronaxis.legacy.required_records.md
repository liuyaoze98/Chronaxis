# `chronaxis.legacy.required_records`

保存按需分析实际使用的CAN记录、原值和来源位置。计算不需要时间时可以明确不采集时间，但不能把缺少的时间填成0或据此计算观测范围。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`RequiredCANFrame`](#api-RequiredCANFrame)|仅持有所需匹配身份，时间None明确表示未采集；模型不具备原始写出能力。|
|[`RequiredCANFrame.__post_init__`](#api-RequiredCANFrame-__post_init__)|检查身份及可选时间。|
|[`required_frame_to_dict`](#api-required_frame_to_dict)|输出固定身份字段。|
|[`RequiredDecodedFrame`](#api-RequiredDecodedFrame)|持有一次目标原序号和冻结所需值；不根据未采集的时间建立时序坐标。|
|[`RequiredDecodedFrame.__post_init__`](#api-RequiredDecodedFrame-__post_init__)|先检查上界再复制外部Mapping。|
|[`required_to_dict`](#api-required_to_dict)|编码固定按需记录。|
|[`required_from_dict`](#api-required_from_dict)|从独立JSON树恢复按需记录。|
|[`required_from_packet`](#api-required_from_packet)|严格解析单条按需JSON，固定模型检查代替同一树的重复通用遍历。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from .records import MAX_WIRE_BYTES, _integer, _shape, _wire_tree, _decoded_values_size, _decoded_entry_size, _value_to_wire, _value_from_wire, _unique_object, _reject_constant
```

</details>

<a id="api-RequiredCANFrame"></a>
## `RequiredCANFrame`

仅持有所需匹配身份，时间None明确表示未采集；模型不具备原始写出能力。

```python
class RequiredCANFrame
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`timestamp`|float &#124; None|是|无|有限原float秒，或本任务未采集。|
|`arbitration_id`|int|是|无|原29位以内ID，不含通道。|
|`channel`|int &#124; str &#124; None|是|无|原通道身份，保持原类型，不猜测。|
|`is_extended_id`|bool|是|无|原标准/扩展标志。|
|`is_fd`|bool|是|无|原经典CAN/FD标志。|
|`is_remote_frame`|bool|是|无|匹配时排除远程帧所需。|
|`is_error_frame`|bool|是|无|匹配时排除错误帧所需。|

源码：[`src/chronaxis/legacy/required_records.py:23`](../../../src/chronaxis/legacy/required_records.py#L23)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RequiredCANFrame-__post_init__"></a>
### `RequiredCANFrame.__post_init__`

检查身份及可选时间。

```python
RequiredCANFrame.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原类型或边界错误。

本函数直接报告的具体错误：

- `ValueError`：所需报文timestamp需要有限float秒或None。
- `TypeError`：所需报文channel需要int/str/None。
- `ValueError`：所需报文channel文本过长。

源码：[`src/chronaxis/legacy/required_records.py:34`](../../../src/chronaxis/legacy/required_records.py#L34)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-required_frame_to_dict"></a>
## `required_frame_to_dict`

输出固定身份字段。

```python
required_frame_to_dict(frame)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|[RequiredCANFrame](chronaxis.legacy.required_records.md#api-RequiredCANFrame)|是|无|位置或关键字。frame为RequiredCANFrame。|

### 返回说明

dict。

### 异常说明

TypeError。

本函数直接报告的具体错误：

- `TypeError`：需要RequiredCANFrame。

源码：[`src/chronaxis/legacy/required_records.py:48`](../../../src/chronaxis/legacy/required_records.py#L48)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RequiredDecodedFrame"></a>
## `RequiredDecodedFrame`

持有一次目标原序号和冻结所需值；不根据未采集的时间建立时序坐标。

```python
class RequiredDecodedFrame
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|原yield序号，可有无关帧形成的间隙。|
|`frame`|[RequiredCANFrame](chronaxis.legacy.required_records.md#api-RequiredCANFrame)|是|无|必要身份与可选时间。|
|`values`|Mapping[str, int &#124; float &#124; bool]|是|无|缺键保持缺失，诊断非有限值保留。|

源码：[`src/chronaxis/legacy/required_records.py:56`](../../../src/chronaxis/legacy/required_records.py#L56)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-RequiredDecodedFrame-__post_init__"></a>
### `RequiredDecodedFrame.__post_init__`

先检查上界再复制外部Mapping。

```python
RequiredDecodedFrame.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、编码或超限错误。

本函数直接报告的具体错误：

- `TypeError`：按需记录需要RequiredCANFrame与数值Mapping。

源码：[`src/chronaxis/legacy/required_records.py:63`](../../../src/chronaxis/legacy/required_records.py#L63)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-required_to_dict"></a>
## `required_to_dict`

编码固定按需记录。

```python
required_to_dict(record)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`record`|[RequiredDecodedFrame](chronaxis.legacy.required_records.md#api-RequiredDecodedFrame)|是|无|位置或关键字。record为RequiredDecodedFrame。|

### 返回说明

dict。

### 异常说明

类型或值错误。

本函数直接报告的具体错误：

- `TypeError`：需要RequiredDecodedFrame。

源码：[`src/chronaxis/legacy/required_records.py:82`](../../../src/chronaxis/legacy/required_records.py#L82)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-required_from_dict"></a>
## `required_from_dict`

从独立JSON树恢复按需记录。

```python
required_from_dict(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。按需解码协议记录，包含本次需要的消息身份和所选信号值。|

### 返回说明

创建后不可修改的对象。

### 异常说明

形状、类型或限额错误。

本函数直接报告的具体错误：

- `TypeError`：required decoded values需要dict。

源码：[`src/chronaxis/legacy/required_records.py:90`](../../../src/chronaxis/legacy/required_records.py#L90)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-required_from_packet"></a>
## `required_from_packet`

严格解析单条按需JSON，固定模型检查代替同一树的重复通用遍历。

```python
required_from_packet(payload)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。payload为64KiB内bytes。|

### 返回说明

独立创建后不可修改的对象。

### 异常说明

UTF-8、重复键、深度、裸非有限常量或模型错误；不解任意对象标签。

本函数直接报告的具体错误：

- `ValueError`：按需记录需要65536字节内bytes。
- `TypeError`：required decoded values需要dict。

源码：[`src/chronaxis/legacy/required_records.py:101`](../../../src/chronaxis/legacy/required_records.py#L101)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
