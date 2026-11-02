# chronaxis.legacy.batch_wire

定义父进程和CAN读取子进程之间使用的批次格式。一个字节包包含多少条记录、每条记录怎样编码和校验，都由这里规定。它不执行读取或DBC解码，也不反序列化任意Python对象。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)、[RequiredDecodedFrame](chronaxis.legacy.required_records.md#api-RequiredDecodedFrame)

## 对象导航

|对象|用途|
|---|---|
|[`LegacyDecodedBatch`](#api-LegacyDecodedBatch)|持有已核批次的全量时间和稀疏完整记录，借用至read下一次推进或关闭。|
|[`LegacyDecodedBatch.frame_count`](#api-LegacyDecodedBatch-frame_count)|读取原帧数而非时间数量。|
|[`encode_batch`](#api-encode_batch)|拼接已经逐条严格编码的记录，检查物理容量后才创建最终包。|
|[`decode_batch`](#api-decode_batch)|核物理边界、原序号、时间和投影完整性，解包后才交付不可变批次。|
|[`record_payload_offset`](#api-record_payload_offset)|定位已验证包中记录长度前缀区域。|
|[`_encode_required_batch`](#api-_encode_required_batch)|建立独立原帧计数的稀疏包，时间仅在目标JSON内。|
|[`_decode_required_batch`](#api-_decode_required_batch)|严格核对稀疏包原跨度、scope、目标顺序及每条必要身份和值。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from .records import MAX_WIRE_BYTES, LegacyDecodedFrame, _decoded_from_packet
from .required_records import RequiredDecodedFrame, required_from_packet
```

</details>

<a id="api-LegacyDecodedBatch"></a>
## `LegacyDecodedBatch`

持有已核批次的全量时间和稀疏完整记录，借用至read下一次推进或关闭。

source的timestamps对应每个原yield，selected仅对应保留records，none为空；
frame_count始终为原始跨度。records保严格递增原序号且可能为空。对象只能在解包完成后由内部建立，
外部自行构造不构成输入已验证证明；保留借用对象的调用方另承担其内存费用。

```python
class LegacyDecodedBatch
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_sequence`|int|是|无|本批第一个原yield序号，不是保留记录的密集序号。|
|`timestamps`|tuple[float, ...]|是|无|所有原yield的精确二进制浮点秒。|
|`records`|tuple[[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame) &#124; [RequiredDecodedFrame](chronaxis.legacy.required_records.md#api-RequiredDecodedFrame), ...]|是|无|source保完整原帧，其他保必要身份。|
|`raw_count`|int &#124; None|否|None|新包独立原帧数；旧包None兼容原timestamps长度。|
|`time_scope`|str|否|'source'|`"none"`：本次未收集时间范围；`"selected"`：范围只基于选中的报文；`"source"`：范围基于整个来源。selected的首末时间不代表整个文件的首末时间。|
|`full_check_count`|int|否|0|新auto包中非原生输入执行完整原帧检查的数量。|
|`protocol_version`|int|否|1|区分source全时间的新包与旧包，证明含义不可混用。|
|`input_index`|int|否|0|当前批所在原序文件；单文件为0，不逐条复制路径。|

源码：[`src/chronaxis/legacy/batch_wire.py:31`](../../../src/chronaxis/legacy/batch_wire.py#L31)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-LegacyDecodedBatch-frame_count"></a>
### `LegacyDecodedBatch.frame_count`

读取原帧数而非时间数量。

```python
LegacyDecodedBatch.frame_count
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

无。

源码：[`src/chronaxis/legacy/batch_wire.py:50`](../../../src/chronaxis/legacy/batch_wire.py#L50)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-encode_batch"></a>
## `encode_batch`

拼接已经逐条严格编码的记录，检查物理容量后才创建最终包。

```python
encode_batch(start_sequence, timestamps, records, eof, byte_limit, *, raw_count=None, time_scope='source', input_check='full', full_check_count=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_sequence`|int|是|无|位置或关键字。start_sequence为原起点|
|`timestamps`|list|是|无|位置或关键字。timestamps为有限float列表|
|`records`|list|是|无|位置或关键字。records为已编码bytes列表|
|`eof`|bool|是|无|位置或关键字。eof为真实原StopIteration标记|
|`byte_limit`|int|是|无|位置或关键字。byte_limit为本次已获准字节上限|
|`raw_count`|int &#124; None|否|None|仅关键字。原始帧跨度，包含未保留的帧；None使用兼容旧包的时间戳数量。|
|`time_scope`|str|否|'source'|仅关键字。`"none"`不收集时间范围；`"selected"`只收集选中记录的时间；`"source"`收集全部来源时间。发送端与接收端必须使用同一次读取确认的设置。full检查要求time_scope为source。|
|`input_check`|str|否|'full'|仅关键字。`"auto"`按实际使用的报文和字段检查；`"full"`检查全部原始帧及时间。发送端与接收端必须使用同一次读取确认的设置。|
|`full_check_count`|int|否|0|仅关键字。本批非原生帧经过完整检查的数量，用于记录auto检查路径的实际检查次数。|

### 返回说明

bytes数据包。

### 异常说明

类型、容量或边界错误；不调用旧读取器或补帧。

本函数直接报告的具体错误：

- `ValueError`：输入检查范围需要auto/full。
- `ValueError`：完整检查必须保留全来源时间。
- `ValueError`：全来源时间批次原帧计数必须与时间数量一致。
- `ValueError`：批次起点或EOF类型非法。
- `ValueError`：批次容量、计数或序号越界。
- `ValueError`：空批次只能报告真实EOF。
- `ValueError`：原报文timestamp需要有限float秒。
- `ValueError`：批次单条记录必须是原限额内bytes。
- `ValueError`：批次编码超过已授权字节上限。

### 边界说明

这是内部编码器，记录语义由原模型/编码器及接收端再次严格检查。

源码：[`src/chronaxis/legacy/batch_wire.py:55`](../../../src/chronaxis/legacy/batch_wire.py#L55)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-decode_batch"></a>
## `decode_batch`

核物理边界、原序号、时间和投影完整性，解包后才交付不可变批次。

```python
decode_batch(payload, *, expected_start, row_limit, byte_limit, frame_ids, time_scope='source', input_check='full')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。payload为recv_bytes取得的受限bytes|
|`expected_start`|int|是|无|仅关键字。本次请求要求的首个原帧序号，必须与返回批次的起点相同。|
|`row_limit`|int|是|无|仅关键字。本次请求可返回的最大行数，用于拒绝超过读取许可的批次。|
|`byte_limit`|int|是|无|仅关键字。expected_start/row_limit/byte_limit     为本次唯一许可|
|`frame_ids`|tuple[int, ...] &#124; None|是|无|仅关键字。需要保留的报文ID集合；None表示全量记录，空元组表示不保留任何ID。|
|`time_scope`|str|否|'source'|仅关键字。`"none"`不收集时间范围；`"selected"`只收集选中记录的时间；`"source"`收集全部来源时间。发送端与接收端必须使用同一次读取确认的设置。full检查要求time_scope为source。|
|`input_check`|str|否|'full'|仅关键字。`"auto"`按实际使用的报文和字段检查；`"full"`检查全部原始帧及时间。发送端与接收端必须使用同一次读取确认的设置。|

### 返回说明

(LegacyDecodedBatch, eof)；EOF仍须由read确认子退出和关闭才生效。

### 异常说明

原JSON/模型检查错误或ValueError为坏包、乱序、长度/时间不符。

本函数直接报告的具体错误：

- `ValueError`：输入检查范围需要auto/full。
- `ValueError`：完整检查必须保留全来源时间。
- `ValueError`：批次字节长度非法。
- `ValueError`：批次头与本次许可不符。
- `ValueError`：批次时间数组被截断。
- `ValueError`：原报文timestamp需要有限float秒。
- `ValueError`：批次存在尾随字节或全量记录缺项。
- `ValueError`：批次记录长度被截断。
- `ValueError`：批次记录超限或被截断。
- `ValueError`：批次记录原序号乱序、重复或越界。
- `ValueError`：批次原时间与记录时间不一致。
- `ValueError`：批次返回未声明保留的报文ID。

### 边界说明

父先付费；本函数不依靠头内数量分配无限数组，也不忽略尾随字节。

源码：[`src/chronaxis/legacy/batch_wire.py:97`](../../../src/chronaxis/legacy/batch_wire.py#L97)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-record_payload_offset"></a>
## `record_payload_offset`

定位已验证包中记录长度前缀区域。

```python
record_payload_offset(batch)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`batch`|[LegacyDecodedBatch](chronaxis.legacy.batch_wire.md#api-LegacyDecodedBatch)|是|无|位置或关键字。已解包的帧批次，提供时间区长度和记录数量，用于定位原协议包中的记录区。|

### 返回说明

字节偏移。

### 异常说明

ValueError为未知scope。

本函数直接报告的具体错误：

- `ValueError`：未知批次时间范围。

源码：[`src/chronaxis/legacy/batch_wire.py:162`](../../../src/chronaxis/legacy/batch_wire.py#L162)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_encode_required_batch"></a>
## `_encode_required_batch`

建立独立原帧计数的稀疏包，时间仅在目标JSON内。

```python
_encode_required_batch(start_sequence, timestamps, records, eof, byte_limit, *, raw_count, time_scope, full_check_count)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_sequence`|int|是|无|位置或关键字。本批首个原始帧的序号，从0开始。|
|`timestamps`|tuple[float, ...]|是|无|位置或关键字。selected模式保存每条保留记录的秒时间戳；none模式必须为空元组。|
|`records`|tuple[bytes, ...]|是|无|位置或关键字。按原序号排列且已编码的按需消息记录；拼接时同时写入各记录长度。|
|`eof`|bool|是|无|位置或关键字。本次批次是否携带真实EOF候选的布尔值，尚须与协议完成事实核对。|
|`byte_limit`|int|是|无|位置或关键字。本次已经许可的最大协议字节数；不能扩充超过预算的包。|
|`raw_count`|int|是|无|仅关键字。本批覆盖的原始帧数量，包含未解码或未保留的帧。|
|`time_scope`|str|是|无|仅关键字。`"none"`不收集时间范围；`"selected"`只收集选中记录的时间；`"source"`收集全部来源时间。发送端与接收端必须使用同一次读取确认的设置。full检查要求time_scope为source。|
|`full_check_count`|int|是|无|仅关键字。本批实际完成全量检查的原帧数，0到原帧跨度计数之间。|

### 返回说明

bytes。

### 异常说明

类型或容量错误。

本函数直接报告的具体错误：

- `ValueError`：批次时间范围需要source/selected/none。
- `ValueError`：按需批次起点、原计数或EOF非法。
- `ValueError`：按需批次容量或时间数量非法。
- `ValueError`：所需报文timestamp需要有限float秒。
- `ValueError`：批次单条记录必须是原限额内bytes。
- `ValueError`：批次编码超过已授权字节上限。

源码：[`src/chronaxis/legacy/batch_wire.py:171`](../../../src/chronaxis/legacy/batch_wire.py#L171)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-_decode_required_batch"></a>
## `_decode_required_batch`

严格核对稀疏包原跨度、scope、目标顺序及每条必要身份和值。

```python
_decode_required_batch(payload, *, expected_start, row_limit, byte_limit, frame_ids, time_scope)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。当前规范批次包bytes，须满足头部、长度和实际许可。|
|`expected_start`|int|是|无|仅关键字。本次请求要求的首个原帧序号，必须与返回批次的起点相同。|
|`row_limit`|int|是|无|仅关键字。本次请求可返回的最大行数，用于拒绝超过读取许可的批次。|
|`byte_limit`|int|是|无|仅关键字。本次已经许可的最大协议字节数；不能扩充超过预算的包。|
|`frame_ids`|tuple[int, ...] &#124; None|是|无|仅关键字。需要保留的报文ID集合；None表示全量记录，空元组表示不保留任何ID。|
|`time_scope`|str|是|无|仅关键字。`"none"`不收集时间范围；`"selected"`只收集选中记录的时间；`"source"`收集全部来源时间。发送端与接收端必须使用同一次读取确认的设置。full检查要求time_scope为source。|

### 返回说明

(批次,真实EOF候选)。

### 异常说明

未许可范围、坏包、JSON/模型或取消错误；不会用假时间凑原帧数量。

本函数直接报告的具体错误：

- `ValueError`：按需批次时间范围或字节长度非法。
- `ValueError`：按需批次头与本次许可不符。
- `ValueError`：批次存在尾随字节或全量记录缺项。
- `ValueError`：批次时间数组被截断。
- `ValueError`：原报文timestamp需要有限float秒。
- `ValueError`：批次记录长度被截断。
- `ValueError`：批次记录超限或被截断。
- `ValueError`：批次记录原序号乱序、重复或越界。
- `ValueError`：批次返回未声明保留的报文ID。
- `ValueError`：未采时间批次不能携带伪造或额外时间。
- `ValueError`：所选时间批次缺少目标时间。
- `ValueError`：批次原时间与记录时间不一致。

源码：[`src/chronaxis/legacy/batch_wire.py:208`](../../../src/chronaxis/legacy/batch_wire.py#L208)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
