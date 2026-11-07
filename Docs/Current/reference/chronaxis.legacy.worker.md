# `chronaxis.legacy.worker`

在独立spawn进程按一条PULL许可推进一次冻结Sclicer公开函数链。

静态只导入标准库和records；INIT校验后才核三份原样vendor哈希、导入真实依赖，
原load_file一次并创建原iter_frames，不提前next。READY的单位来自同次db公开
messages/signals；每PULL只next一次、对同msg/db原parse_frame一次，返当前ITEM
后等待下一命令。STATUS/ACK不授予读取许可，STOP不取后继，正常EOF后退出。

本进程只发送最大65536字节的严格JSON bytes，不使用Connection.send/recv的pickle。
记录保原msg全部公开写出字段和全部原返回数值，不窥视generator frame、补decode、
增加筛选或缩放。finally只关本连接和原生成器，不声称旧reader底层FD已确定关闭；
父进程须等待本进程确实退出，OS才回收本进程旧FD。外部解释器/DBC/reader的RSS
不受父共享账目保证。失败发送有限原错误事实并以非零退出，不伪称原异常对象跨进程。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyCANRequest](chronaxis.legacy.records.md#api-LegacyCANRequest)、[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)、[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_send`](#api-_send)|通过bytes接口发送一个有界JSON包，不调用pickle通道。|
|[`_receive`](#api-_receive)|只接收一个不超过单包上限的bytes消息。|
|[`_exact`](#api-_exact)|限制每种控制包的精确字段，不让多余许可或版本字段静默生效。|
|[`_request`](#api-_request)|解析唯一INIT，只接受单个实际BLF和原DBC路径，不读取其内容摘要。|
|[`_load_vendor`](#api-_load_vendor)|核原样三模块字节后在独立child安装其原名称，保绝对utils导入。|
|[`_field_metadata`](#api-_field_metadata)|只读同次db公开messages/signals核定位唯一，并返回原单位。|
|[`_frame`](#api-_frame)|在一次原parse之后保存同次msg公开写出字段，不重建CAN消息。|
|[`_argument_text`](#api-_argument_text)|只摘要原生异常参数，不执行任意对象str或先展开完整巨型消息。|
|[`_error_packet`](#api-_error_packet)|保存有限原错误事实，不把远端异常对象或任意类传给父进程。|
|[`_report_error`](#api-_report_error)|尽力发送原错误事实，断管不替代child原错或阻止退出。|
|[`worker_main`](#api-worker_main)|作为spawn目标按INIT/PULL协议调用冻结旧公开链，等待许可时不预取。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from importlib import metadata, util
from pathlib import Path
from .records import LegacyCANRequest, LegacyDecodedFrame, LegacyRawFrame, MAX_WIRE_BYTES, PROFILE_ID, decode_packet, decoded_to_dict, encode_packet, field_from_dict, field_to_dict
```

</details>

<a id="api-_send"></a>
## `_send`

通过bytes接口发送一个有界JSON包，不调用pickle通道。

```python
_send(connection, packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.Connection|是|无|位置或关键字。父子进程之间已经建立的双向通信端点，用于发送请求和接收结果；不是文件路径或网络地址。|
|`packet`|dict|是|无|位置或关键字。packet为协议dict。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

原wire类型/限额或管道错误；不重试导致重复ITEM。

源码：[`src/chronaxis/legacy/worker.py:33`](../../../src/chronaxis/legacy/worker.py#L33)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_receive"></a>
## `_receive`

只接收一个不超过单包上限的bytes消息。

```python
_receive(connection)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.Connection|是|无|位置或关键字。父子进程之间已经建立的双向通信端点，用于发送请求和接收结果；不是文件路径或网络地址。|

### 返回说明

已校验dict。

### 异常说明

EOFError/OSError/协议错误传播，不把断管当正常来源EOF。

源码：[`src/chronaxis/legacy/worker.py:42`](../../../src/chronaxis/legacy/worker.py#L42)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_exact"></a>
## `_exact`

限制每种控制包的精确字段，不让多余许可或版本字段静默生效。

```python
_exact(packet, names)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict[str, object]|是|无|位置或关键字。已经解码并检查字段的进程通信包，含op操作名及该操作的数据；本函数按当前协议步骤继续检查或发送它。|
|`names`|set[str] &#124; tuple[str, ...]|是|无|位置或关键字。该协议操作需要的完整键名集合；缺键和额外键均报错。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

ValueError为字段缺失或多余。

本函数直接报告的具体错误：

- `ValueError`：旧CAN控制包字段缺失或多余。

源码：[`src/chronaxis/legacy/worker.py:51`](../../../src/chronaxis/legacy/worker.py#L51)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_request"></a>
## `_request`

解析唯一INIT，只接受单个实际BLF和原DBC路径，不读取其内容摘要。

```python
_request(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict|是|无|位置或关键字。packet为INIT dict。|

### 返回说明

LegacyCANRequest。

### 异常说明

类型/形状/版本/路径错误；不调用旧reader或load_file。

本函数直接报告的具体错误：

- `ValueError`：旧CAN需要init/version1。
- `TypeError`：旧CAN INIT需要文本路径与fields数组。
- `ValueError`：首版旧CAN仅支持单个现有BLF文件。

源码：[`src/chronaxis/legacy/worker.py:61`](../../../src/chronaxis/legacy/worker.py#L61)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_load_vendor"></a>
## `_load_vendor`

核原样三模块字节后在独立child安装其原名称，保绝对utils导入。

```python
_load_vendor()
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

(file_processor模块,can_processor模块,实际哈希dict)。

### 异常说明

哈希、同名模块污染或原模块依赖导入错误；不猴补函数、reader或计数器。

源码：[`src/chronaxis/legacy/worker.py:82`](../../../src/chronaxis/legacy/worker.py#L82)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_field_metadata"></a>
## `_field_metadata`

只读同次db公开messages/signals核定位唯一，并返回原单位。

```python
_field_metadata(db, fields, *, cycle_fields=())
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`db`|cantools.database.can.Database|是|无|位置或关键字。本次DBC加载所得数据库，读取消息和信号定义生成来源字段描述。|
|`fields`|tuple[LegacyCANField, ...]|是|无|位置或关键字。fields为原LegacyCANField tuple。|
|`cycle_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。需要读取DBC周期的字段定位集合；初始化时读取元数据，不逐帧读取DBC。|

### 返回说明

按请求顺序的字段事实；周期请求的字段另含正cycle_ns。
    仅DBC为FD而定位为经典CAN时增加固定兼容提示。
    channel保声明，不冒称DBC已测通道；不把DBC声明写回原帧。

### 异常说明

ValueError为ID/消息/帧型/信号歧义或不符，TypeError为单位不受支持。

本函数直接报告的具体错误：

- `ValueError`：原DBC消息名称或标准/FD帧型与定位不同。
- `TypeError`：原DBC公开unit需要文本或None。

源码：[`src/chronaxis/legacy/worker.py:115`](../../../src/chronaxis/legacy/worker.py#L115)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_frame"></a>
## `_frame`

在一次原parse之后保存同次msg公开写出字段，不重建CAN消息。

```python
_frame(msg)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`msg`|can.Message|是|无|位置或关键字。本次旧读取器刚返回的原始报文，保持时间戳、ID、通道、标志和数据字节。|

### 返回说明

LegacyRawFrame。

### 异常说明

新边界字段校验失败；data仅无损复制为bytes，不改timestamp/DLC/标志。

本函数直接报告的具体错误：

- `ValueError`：原报文data超过64字节，不能先复制再拒绝。

源码：[`src/chronaxis/legacy/worker.py:167`](../../../src/chronaxis/legacy/worker.py#L167)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_argument_text"></a>
## `_argument_text`

只摘要原生异常参数，不执行任意对象str或先展开完整巨型消息。

```python
_argument_text(value, limit)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。异常args中的一个原始值，转换为有长度上限的错误文字；不直接输出整个日志或大对象。|
|`limit`|int|是|无|位置或关键字。该错误文字的最大字符数，超过时截短以限制协议包大小。|

### 返回说明

有限str，短原str保持内容。

### 异常说明

无主动异常；未知对象仅标明类型，不调用其自定义字符串方法。

源码：[`src/chronaxis/legacy/worker.py:182`](../../../src/chronaxis/legacy/worker.py#L182)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_error_packet"></a>
## `_error_packet`

保存有限原错误事实，不把远端异常对象或任意类传给父进程。

```python
_error_packet(exc, phase, request_id)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|
|`phase`|str|是|无|位置或关键字。phase为有限阶段文本|
|`request_id`|int &#124; None|是|无|位置或关键字。本次协议请求的编号，供父进程关联响应；尚未取得请求编号的初始化错误使用None。|

### 返回说明

有限ERROR dict；message是至多4个args摘要，traceback仅至多8个栈地点，
    均不是完整str(exc)或完整traceback，截断有明确note，短单str参数保持原文本。

### 异常说明

标准库字段访问/编码错误传播；调用方仍须确定退出，不伪报正常EOF。

源码：[`src/chronaxis/legacy/worker.py:197`](../../../src/chronaxis/legacy/worker.py#L197)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_report_error"></a>
## `_report_error`

尽力发送原错误事实，断管不替代child原错或阻止退出。

```python
_report_error(connection, exc, phase, request_id)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.Connection|是|无|位置或关键字。父子进程之间已经建立的双向通信端点，用于发送请求和接收结果；不是文件路径或网络地址。|
|`exc`|BaseException|是|无|位置或关键字。实际捕获的异常，提取有限错误信息后通过协议报告给父进程。|
|`phase`|str|是|无|位置或关键字。异常发生的处理步骤，例如初始化、读取或解码，用于定位失败阶段。|
|`request_id`|int &#124; None|是|无|位置或关键字。本次协议请求的编号，供父进程关联响应；尚未取得请求编号的初始化错误使用None。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

不传播附加报告错误；原失败仍由worker最终非零退出表达。

源码：[`src/chronaxis/legacy/worker.py:240`](../../../src/chronaxis/legacy/worker.py#L240)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-worker_main"></a>
## `worker_main`

作为spawn目标按INIT/PULL协议调用冻结旧公开链，等待许可时不预取。

```python
worker_main(connection)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.Connection|是|无|位置或关键字。父子进程之间已经建立的双向通信端点，用于发送请求和接收结果；不是文件路径或网络地址。|

### 返回说明

正常STOP或真实EOF时None。

### 异常说明

原错误尽力发ERROR后以SystemExit(1)退出；连接/生成器附加关闭错误也非零。

本函数直接报告的具体错误：

- `ValueError`：未知旧CAN控制操作。
- `ValueError`：PULL许可必须从0严格连续。
- `ValueError`：ACK仅接受确认最近返回ITEM。

### 副作用说明

本child内一次load_file、一次iter_frames、每许可一次next/parse；不额外扫描。

源码：[`src/chronaxis/legacy/worker.py:252`](../../../src/chronaxis/legacy/worker.py#L252)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
