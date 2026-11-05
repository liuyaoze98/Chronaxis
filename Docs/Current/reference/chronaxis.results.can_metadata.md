# `chronaxis.results.can_metadata`

保存一次CAN读取的记录：使用的输入和DBC、原始报文暂存信息、声明单位与DBC单位的比较结果。记录来自实际执行；仅仅构造这些对象不会重新读取或验证文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)

## 对象导航

|对象|用途|
|---|---|
|[`_integer`](#api-_integer)|校验非负原生整数，拒绝bool和外部整数替代。|
|[`_sha256`](#api-_sha256)|校验64位hex摘要原文，不把路径、版本或随机身份冒充内容SHA。|
|[`_pairs`](#api-_pairs)|检查版本或vendor摘要的冻结键值对，不能重复键或接受可变字典。|
|[`CANUnitCheck`](#api-CANUnitCheck)|保原声明单位及同次DBC单位；verified只表示非空原文本完全相同。|
|[`CANUnitCheck.__post_init__`](#api-CANUnitCheck-__post_init__)|校验单位比较事实，不去空格、换算或重复施加DBC缩放。|
|[`CANFrameFormatNotice`](#api-CANFrameFormatNotice)|保存DBC声明FD但选中实际经典CAN的有限提示，不证明任意原帧均匹配。|
|[`CANFrameFormatNotice.__post_init__`](#api-CANFrameFormatNotice-__post_init__)|核固定提示及原定位类型，不访问DBC或把声明当实际帧转换。|
|[`CANSourceMetadata`](#api-CANSourceMetadata)|保存一条真实read的有限事实；内部模型校验不认证实际读取或资源释放。|
|[`CANSourceMetadata.__post_init__`](#api-CANSourceMetadata-__post_init__)|核标识、计数/首末、摘要及冻结子记录，不访问原输入或暂存。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.validation import require_identifier, require_text
from ..legacy.records import PROFILE_ID, LegacyCANField
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-_integer"></a>
## `_integer`

校验非负原生整数，拒绝bool和外部整数替代。

```python
_integer(value, name, minimum=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。待检查的非负Python整数；bool不算整数，非法类型或负数报错。|
|`name`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|
|`minimum`|int|否|0|位置或关键字。minimum为含端点下限。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

TypeError为非原生int，ValueError为小于下限。

源码：[`src/chronaxis/results/can_metadata.py:19`](../../../src/chronaxis/results/can_metadata.py#L19)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_sha256"></a>
## `_sha256`

校验64位hex摘要原文，不把路径、版本或随机身份冒充内容SHA。

```python
_sha256(value, name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。待检查的SHA-256摘要，写为64个小写十六进制字符。|
|`name`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|

### 返回说明

None，保大小写原值。

### 异常说明

TypeError/ValueError为类型、长度或非hex字符；不读取文件证明实际内容。

源码：[`src/chronaxis/results/can_metadata.py:31`](../../../src/chronaxis/results/can_metadata.py#L31)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-_pairs"></a>
## `_pairs`

检查版本或vendor摘要的冻结键值对，不能重复键或接受可变字典。

```python
_pairs(value, name, hashes=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|tuple[tuple[str, str], ...]|是|无|位置或关键字。按固定顺序保存的名称与文本值对；每项都必须是两个字符串组成的元组。|
|`name`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|
|`hashes`|bool|否|False|位置或关键字。hashes指值是否需要SHA。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

TypeError/ValueError为结构、空文本、重复键或非法SHA。

源码：[`src/chronaxis/results/can_metadata.py:43`](../../../src/chronaxis/results/can_metadata.py#L43)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANUnitCheck"></a>
## `CANUnitCheck`

保原声明单位及同次DBC单位；verified只表示非空原文本完全相同。

```python
class CANUnitCheck
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`alias`|str|是|无|同一运行signal_bindings中的简单别名，不是DBC信号名称。|
|`input_unit`|str|是|无|原解码输入单位，不是额外线性转换后的输出单位。|
|`dbc_unit`|str &#124; None|是|无|同次公开signal.unit原值，None/空字符串均原样保留。|
|`status`|str|是|无|verified或declared；不表示物理测量已验。|

源码：[`src/chronaxis/results/can_metadata.py:65`](../../../src/chronaxis/results/can_metadata.py#L65)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANUnitCheck-__post_init__"></a>
### `CANUnitCheck.__post_init__`

校验单位比较事实，不去空格、换算或重复施加DBC缩放。

```python
CANUnitCheck.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为字段类型或状态与原单位冲突。

本函数直接报告的具体错误：

- `TypeError`：can_unit.dbc_unit需要str或None。
- `ValueError`：CAN单位状态仅verified/declared。
- `ValueError`：verified需要非空DBC单位与原input_unit完全相同。
- `ValueError`：declared仅用于DBC单位None或空字符串。

源码：[`src/chronaxis/results/can_metadata.py:73`](../../../src/chronaxis/results/can_metadata.py#L73)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANFrameFormatNotice"></a>
## `CANFrameFormatNotice`

保存DBC声明FD但选中实际经典CAN的有限提示，不证明任意原帧均匹配。

alias关联本次实际信号声明，其余字段完整保存原定位和同次DBC帧型。
仅单向差异合法；真实帧仍由读取层原通道/ID/标准/FD校验，不改变原帧。

```python
class CANFrameFormatNotice
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`alias`|str|是|无|同次实际signal_bindings简单别名。|
|`channel`|int|是|无|原定位通道，不冒称DBC能证明物理通道。|
|`signal`|str|是|无|同次DBC核对的原信号名称，保全文。|
|`frame_id`|int|是|无|与原显式定位一致的数值报文ID。|
|`is_extended`|bool|是|无|同次读取确认的实际标准/扩展帧类型，必须是bool，不允许None。|
|`dbc_is_fd`|bool|是|无|同次DBC声明，唯一允许值为原生True。|
|`requested_is_fd`|bool|是|无|兼容处理中选中的经典CAN，固定False；既可能来自显式选择，也可能是自动识别结果。|
|`code`|str|否|'dbc_fd_classic_selector'|稳定机器码，不接受其他自由兼容政策。|

源码：[`src/chronaxis/results/can_metadata.py:92`](../../../src/chronaxis/results/can_metadata.py#L92)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANFrameFormatNotice-__post_init__"></a>
### `CANFrameFormatNotice.__post_init__`

核固定提示及原定位类型，不访问DBC或把声明当实际帧转换。

```python
CANFrameFormatNotice.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为非法类型、方向或固定code。

本函数直接报告的具体错误：

- `TypeError`：DBC帧型提示需要原生bool。
- `ValueError`：仅兼容DBC FD声明与显式经典CAN定位。
- `ValueError`：CAN帧型提示code非法。

源码：[`src/chronaxis/results/can_metadata.py:108`](../../../src/chronaxis/results/can_metadata.py#L108)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANSourceMetadata"></a>
## `CANSourceMetadata`

保存一条真实read的有限事实；内部模型校验不认证实际读取或资源释放。

```python
class CANSourceMetadata
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|同计划安全来源名。|
|`session_id`|str|是|无|同次分析会话，运行清单另核会话归属。|
|`legacy_profile`|str|是|无|固定sclicer-functions-v1。|
|`path`|str|是|无|原单BLF路径文本，不在元数据模型中resolve。|
|`dbc_path`|str|是|无|同次原load_file路径，不是DBC内容哈希。|
|`channel`|int|是|无|明确单通道，非负原生int。|
|`read_identity`|str|是|无|同次实际read身份，不与随机运行ID或物理行号混淆。|
|`worker_pid`|int|是|无|实际子进程正整数PID，不能用bool表示。|
|`frame_count`|int|是|无|原yield总数，不是投影信号样本数。|
|`first_ns`|int &#124; None|是|无|原帧映射后首坐标；空来源为None。|
|`last_ns`|int &#124; None|是|无|原帧映射后末坐标；不伪造请求domain的终点。|
|`raw_store_path`|str &#124; None|是|无|本次封口原始帧暂存路径；计划不需原帧导出时为None。|
|`raw_store_sha256`|str &#124; None|是|无|仅实际保存原帧时给整流SHA，不冒充原BLF或DBC的SHA。|
|`raw_spool_bytes`|int|是|无|本raw_store累计预留字节，不是RSS或已归还磁盘。|
|`dependency_versions`|tuple[tuple[str, str], ...]|是|无|同次READY版本事实，键唯一。|
|`vendor_sha256`|tuple[tuple[str, str], ...]|是|无|同次三原模块证据，键唯一、值为SHA。|
|`unit_checks`|tuple[[CANUnitCheck](chronaxis.results.can_metadata.md#api-CANUnitCheck), ...]|是|无|每别名单位事实，不能重复别名。|
|`frame_format_notices`|tuple[[CANFrameFormatNotice](chronaxis.results.can_metadata.md#api-CANFrameFormatNotice), ...]|否|()|无差异保空，不新增旧序列化键或费用。|
|`decode_scope`|str|否|'all'|`"requested"`解码本次需要的报文和字段；`"all"`保留全解码与完整诊断。该字段记录或指定的是解码范围。|
|`decode_frame_ids`|tuple[int, ...]|否|()|requested实际固定ID集合，覆盖本次所需字段和触发报文。|
|`decoded_values_policy`|str|否|'all_values-v1'|旧全字段默认不加清单键；按需只传实际所需字段。|
|`input_check`|str|否|'full'|`"auto"`按本计划实际要计算的内容检查输入；`"full"`检查全部原帧及时间，即使某帧不参与指标也检查它。|
|`time_scope`|str|否|'source'|`"none"`：本次未收集时间范围；`"selected"`：范围只基于选中的报文；`"source"`：范围基于整个来源。selected的首末时间不代表整个文件的首末时间。|
|`check_policy_version`|str &#124; None|否|None|仅新按需策略给版本。 None表示旧全量路径没有这项按需检查版本。|
|`retained_record_count`|int &#124; None|否|None|实际保留原记录数。 None表示此读取路径没有记录这一计数，不等于0。|
|`full_check_count`|int|否|0|非原生输入完整检查回退数。|
|`selected_first_ns`|int &#124; None|否|None|仅selected提供目标首时间。 None表示没有选中的目标时间或本路径不采集selected时间。|
|`selected_last_ns`|int &#124; None|否|None|目标末时间，不是文件末时间。 None表示没有选中的目标时间或本路径不采集selected时间。|

源码：[`src/chronaxis/results/can_metadata.py:125`](../../../src/chronaxis/results/can_metadata.py#L125)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CANSourceMetadata-__post_init__"></a>
### `CANSourceMetadata.__post_init__`

核标识、计数/首末、摘要及冻结子记录，不访问原输入或暂存。

```python
CANSourceMetadata.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为类型、范围或内部事实冲突，
    OverflowError为非空首末超int64；不把声明校验写成实际EOF/哈希验证成功。

源码：[`src/chronaxis/results/can_metadata.py:157`](../../../src/chronaxis/results/can_metadata.py#L157)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
