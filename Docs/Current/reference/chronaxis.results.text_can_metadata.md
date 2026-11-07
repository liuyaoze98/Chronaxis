# `chronaxis.results.text_can_metadata`

记录本次ASC或原始报文CSV读取使用的解析设置、DBC和实际起止时间。这些信息放入文本CAN的运行清单，便于复核输入；它不代表原BLF读取路径的检查结果。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANFrameFormatNotice](chronaxis.results.can_metadata.md#api-CANFrameFormatNotice)、[CANUnitCheck](chronaxis.results.can_metadata.md#api-CANUnitCheck)

## 对象导航

|对象|用途|
|---|---|
|[`TextCANSourceMetadata`](#api-TextCANSourceMetadata)|保存本次文本CAN的路径、解析格式、偏移、DBC哈希、版本、实际读取和解码数量；文件输入列表不提供原文件内容哈希。|
|[`TextCANSourceMetadata.__post_init__`](#api-TextCANSourceMetadata-__post_init__)|核实结构及计数一致性，不读文件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
from .can_metadata import CANUnitCheck, CANFrameFormatNotice
```

</details>

<a id="api-TextCANSourceMetadata"></a>
## `TextCANSourceMetadata`

保存本次文本CAN的路径、解析格式、偏移、DBC哈希、版本、实际读取和解码数量；文件输入列表不提供原文件内容哈希。

```python
class TextCANSourceMetadata
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|来源别名。|
|`session_id`|str|是|无|当前独立会话的字符串ID，例如trial_a；不能混用另一试验的数据。|
|`source_type`|str|是|无|实际来源种类can_asc或raw_can_csv。|
|`read_identity`|str|是|无|本次实际读取的标识。|
|`inputs`|tuple[tuple[str, str, int], ...]|是|无|(输入路径, 解析器版本/格式, 本文件offset_ns)元组的元组；不是文件哈希或字节数。|
|`dbc_path`|str|是|无|实际加载DBC的路径。|
|`dbc_sha256`|str|是|无|实际加载DBC内容的SHA256。|
|`cantools_version`|str|是|无|本次使用的cantools版本字符串。|
|`record_count`|int|是|无|实际读出的原始报文数量，不是信号样本数。|
|`decode_calls`|int|是|无|实际进行的DBC解码调用次数，不以输入总行数代替。|
|`first_ns`|int &#124; None|是|无|实际首个报文的分析时间ns；空输入时None。|
|`last_ns`|int &#124; None|是|无|实际最后报文的分析时间ns；空输入时None。|
|`unit_checks`|tuple[[CANUnitCheck](chronaxis.results.can_metadata.md#api-CANUnitCheck), ...]|是|无|对选中信号实际执行的DBC单位检查记录。|
|`frame_format_notices`|tuple[[CANFrameFormatNotice](chronaxis.results.can_metadata.md#api-CANFrameFormatNotice), ...]|否|()|DBC帧格式声明与实际帧的兼容检查说明。|
|`profile`|str|否|'can-text-v1'|文本读取/解码路径版本标记can-text-v1，用于复现。|
|`decode_scope`|str|否|'requested'|`"requested"`解码本次需要的报文和字段；`"all"`保留全解码与完整诊断。该字段记录或指定的是解码范围。|
|`time_scope`|str|否|'source'|`"none"`：本次未收集时间范围；`"selected"`：范围只基于选中的报文；`"source"`：范围基于整个来源。selected的首末时间不代表整个文件的首末时间。|

源码：[`src/chronaxis/results/text_can_metadata.py:14`](../../../src/chronaxis/results/text_can_metadata.py#L14)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-TextCANSourceMetadata-__post_init__"></a>
### `TextCANSourceMetadata.__post_init__`

核实结构及计数一致性，不读文件。

```python
TextCANSourceMetadata.__post_init__()
```

参数：无显式参数。


#### 参数说明

创建后不可修改的字段。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/值错误。

本函数直接报告的具体错误：

- `ValueError`：文本CAN清单策略错误。
- `ValueError`：文本CAN清单需要实际DBC SHA256。
- `ValueError`：文本CAN清单需要有限有序输入。
- `ValueError`：文本CAN实际帧数与解码次数错误。
- `TypeError`：文本CAN单位/帧型清单需要创建后不可修改的对象tuple。
- `ValueError`：输入清单需要(path,parser,offset_ns)。
- `ValueError`：空文本CAN不能声明观测时间。
- `ValueError`：文本CAN观测时间倒退。

源码：[`src/chronaxis/results/text_can_metadata.py:35`](../../../src/chronaxis/results/text_can_metadata.py#L35)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
