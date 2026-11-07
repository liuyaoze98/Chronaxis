# `chronaxis.legacy.batch_worker`

在隔离子进程按有限批次调用原CAN函数，默认仍解码全部报文。

INIT仍仅加载原DBC和公开字段元数据；每次pull_batch明确许可原帧条数与字节上限。
默认每条执行原next/parse一次。显式decode_frame_ids限制允许解码的ID，只有其中
实际请求了字段的ID才调用parse；纯常量触发帧不调用parse。全部原帧仍
顺序读取并保留原时间、字段校验；所选帧仍一次调用原parse，参数不变。按需模式在
原parse返回后立即只取INIT所需字段，缺失键保持缺失；v3 READY确认这一投影策略。
原帧保留集合与解码集合独立，导出原始帧可保留全部帧而不解码无需求ID。
auto模式在原生消息ID不匹配时先跳过；仅source需要读其时间。selected/none目标
只保存必要身份与所需值；非原生消息沿完整原帧检查并计入新包的回退数量。
字节不足容纳下一条最大记录时先结束当前批，不提前读取再丢弃。真正StopIteration
可与最后批数据一起报告，子实际退出及资源回收仍由父确认。没有后台预读或pickle。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)、[RequiredCANFrame](chronaxis.legacy.required_records.md#api-RequiredCANFrame)、[RequiredDecodedFrame](chronaxis.legacy.required_records.md#api-RequiredDecodedFrame)

## 对象导航

|对象|用途|
|---|---|
|[`_parse_selected`](#api-_parse_selected)|普通ID复用原解码入口，同ID多定义时直接调用选中的同库解码实现。|
|[`_requested_fields`](#api-_requested_fields)|按固定报文ID整理所需信号名，不读取输入或遍历解码结果。|
|[`_project_values`](#api-_project_values)|只读取本报文所需的原值，让后续完整模型只检查这些值。|
|[`_encode_fresh_packet`](#api-_encode_fresh_packet)|编码本worker刚完成完整检查的记录，省去同一JSON树的再次遍历。|
|[`_limits`](#api-_limits)|验证本次批许可及解码后投影，非法许可不能推进旧读取器。|
|[`batch_worker_main`](#api-batch_worker_main)|处理一次独立批次会话，沿用原INIT、元数据和有限远端错误格式。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from collections import Counter
from importlib import metadata
from math import isfinite
from . import worker
from .records import PROFILE_ID, MAX_WIRE_BYTES, LegacyDecodedFrame, decoded_to_dict, _decoded_values_size
from .batch_wire import HEADER, DEMAND_HEADER, LENGTH, MIN_BATCH_BYTES, MAX_BATCH_BYTES, MAX_BATCH_ROWS, FILE_HEADER, FILE_MAGIC, encode_batch
from .batch_validation import validate_discarded, _item_base_size
from .required_records import RequiredCANFrame, RequiredDecodedFrame, required_to_dict
```

</details>

<a id="api-_parse_selected"></a>
## `_parse_selected`

普通ID复用原解码入口，同ID多定义时直接调用选中的同库解码实现。

```python
_parse_selected(processor, db, frame, message, duplicate_ids)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`processor`|ModuleType|是|无|位置或关键字。已加载的旧解码模块，提供parse_frame(frame, db)；普通唯一ID继续调用该入口。|
|`db`|cantools.database.can.Database|是|无|位置或关键字。与当前读取会话共用的DBC数据库，传给旧解码入口，不重新加载文件。|
|`frame`|can.Message|是|无|位置或关键字。本次实际报文，提供ID、帧型和载荷；函数不读取下一条报文。|
|`message`|cantools.database.can.Message &#124; None|是|无|位置或关键字。按实际帧选择的DBC定义；同ID存在多个定义时调用它的decode，None沿旧入口处理。|
|`duplicate_ids`|set[int]|是|无|位置或关键字。初始化时统计的重复DBC报文ID集合，用于判断是否必须避开旧入口仅按ID查表的歧义。|

### 返回说明

原物理值dict；DBC解码失败为空dict。

### 异常说明

非DBC结构错误由外层传播。

源码：[`src/chronaxis/legacy/batch_worker.py:36`](../../../src/chronaxis/legacy/batch_worker.py#L36)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_requested_fields"></a>
## `_requested_fields`

按固定报文ID整理所需信号名，不读取输入或遍历解码结果。

```python
_requested_fields(fields, decode_ids)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`fields`|tuple[LegacyCANField, ...]|是|无|位置或关键字。INIT已经检查的完整信号定位，每项确定报文及所需信号名称。|
|`decode_ids`|frozenset[int]|是|无|位置或关键字。本次需要解码的报文ID集合，不随每批数据改变。|

### 返回说明

ID到去重信号名字典的有限映射，名字次序保持请求顺序。

### 异常说明

ValueError表示字段所在报文不在解码范围；原分配/取消错误直接传播。
父策略费用为每个字段另付1024B，覆盖此表及构建临时槽；名称借自原请求。

源码：[`src/chronaxis/legacy/batch_worker.py:52`](../../../src/chronaxis/legacy/batch_worker.py#L52)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_project_values"></a>
## `_project_values`

只读取本报文所需的原值，让后续完整模型只检查这些值。

```python
_project_values(values, names)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|Mapping|是|无|位置或关键字。values为原parse返回值|
|`names`|Mapping[str, object] &#124; tuple|是|无|位置或关键字。当前报文需要保留的信号名集合；没有所需名称时使用空元组，不输出其他信号值。|

### 返回说明

新dict，保留实际存在的所需键；KeyError代表缺失，不补None或零。

### 异常说明

有字段需求时非Mapping报TypeError；所需键访问和取消错误原样传播。
无字段的常量触发报文直接返回空dict，不遍历或校验没有用途的原values。

源码：[`src/chronaxis/legacy/batch_worker.py:73`](../../../src/chronaxis/legacy/batch_worker.py#L73)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_encode_fresh_packet"></a>
## `_encode_fresh_packet`

编码本worker刚完成完整检查的记录，省去同一JSON树的再次遍历。

```python
_encode_fresh_packet(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)|是|无|位置或关键字。packet只能是紧邻LegacyDecodedFrame成功构造后由原decoded_to_dict生成的     私有dict|

### 返回说明

与公开encode_packet相同的UTF-8 bytes，不带换行。

### 异常说明

原JSON/UTF-8编码错误、实际超过65536字节的ValueError或原取消异常。
完整模型已检查全部帧字段、含ITEM外壳的长度及收到的Mapping两遍，再复制冻结数值；
原转换只生成固定字段与非有限数值标签。沿用原批许可费用，不保留跨记录状态。

源码：[`src/chronaxis/legacy/batch_worker.py:100`](../../../src/chronaxis/legacy/batch_worker.py#L100)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_limits"></a>
## `_limits`

验证本次批许可及解码后投影，非法许可不能推进旧读取器。

```python
_limits(packet, frames_returned)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|dict[str, object]|是|无|位置或关键字。已经解码并检查字段的进程通信包，含op操作名及该操作的数据；本函数按当前协议步骤继续检查或发送它。|
|`frames_returned`|int|是|无|位置或关键字。此前已经返回的原始帧数，用于计算下一批的起始序号和剩余许可。|

### 返回说明

(原帧上限,字节上限,保留ID集合或None)。

### 异常说明

TypeError/ValueError。

本函数直接报告的具体错误：

- `ValueError`：批次许可必须按原帧序号连续。
- `ValueError`：批次许可条数或字节上限非法。
- `ValueError`：解码后保留ID必须是无重复29位整数列表或None。

源码：[`src/chronaxis/legacy/batch_worker.py:123`](../../../src/chronaxis/legacy/batch_worker.py#L123)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-batch_worker_main"></a>
## `batch_worker_main`

处理一次独立批次会话，沿用原INIT、元数据和有限远端错误格式。

```python
batch_worker_main(connection, *, decode_frame_ids=None, input_check='full', time_scope='source', input_paths=None, decode_policy='legacy', cycle_fields=(), metadata_fields=())
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.Connection|是|无|位置或关键字。父子进程之间已经建立的双向通信端点，用于发送请求和接收结果；不是文件路径或网络地址。|
|`decode_frame_ids`|tuple &#124; None|否|None|仅关键字。decode_frame_ids=None沿用全解码，     原生tuple明确本次固定解码ID，允许空集合|
|`input_check`|str|否|'full'|仅关键字。`"auto"`按实际使用的报文和字段检查；`"full"`检查全部原始帧及时间。发送端与接收端必须使用同一次读取确认的设置。|
|`time_scope`|str|否|'source'|仅关键字。`"none"`不收集时间范围；`"selected"`只收集选中记录的时间；`"source"`收集全部来源时间。发送端与接收端必须使用同一次读取确认的设置。full检查要求time_scope为source。|
|`input_paths`|tuple[str, ...] &#124; None|否|None|仅关键字。有序且同格式的连续输入文件；按给定顺序读取，文件边界不中断计算状态。|
|`decode_policy`|str|否|'legacy'|仅关键字。strict要求DBC长度一致，partial允许短载荷可解部分，legacy沿用旧格式路径；不接受未知取值。|
|`cycle_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。需要读取DBC周期的字段定位集合；初始化时读取元数据，不逐帧读取DBC。|
|`metadata_fields`|tuple[LegacyCANField, ...]|否|()|仅关键字。仅请求驱动信号的DBC候选声明，默认空tuple；用于确认实际帧身份，不请求信号值，也不增加普通样本或值解码。|

### 返回说明

正常STOP或真实EOF时None。

### 异常说明

失败发送有限事实并以SystemExit(1)退出；清理副错不替代原错误。

本函数直接报告的具体错误：

- `ValueError`：输入检查与时间范围必须匹配固定按需解码策略。
- `ValueError`：按需解码ID必须是无重复29位整数tuple。
- `ValueError`：未知批次控制操作。
- `ValueError`：全来源按需批次字节许可不足以容纳一条最大记录。
- `ValueError`：原报文timestamp需要有限float秒。

### 副作用说明

子进程内一次load_file，每个声明文件一次iter_frames；每原帧顺序next，默认全部parse，
    显式按需只对固定集合内有字段需求的帧调用parse，并立即投影所需字段。未解码帧不产生或检查
    解码值，仍检查原帧；原始帧保留范围不扩大解码范围。
    只关闭自己连接和原生成器；不声称原reader已有可靠公开close实现。

源码：[`src/chronaxis/legacy/batch_worker.py:143`](../../../src/chronaxis/legacy/batch_worker.py#L143)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
