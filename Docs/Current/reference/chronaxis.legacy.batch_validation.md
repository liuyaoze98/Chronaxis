# chronaxis.legacy.batch_validation

校验批次中不再保存的原报文，避免为丢弃的数据建立完整解码记录副本。

输入是旧parse_frame刚返回的原msg、完整values和原yield序号；成功返回None。
先沿用原公开帧字段检查。常见原生消息用安全上界证明完整ITEM不超过64KiB；
无法证明时，精确计算原ITEM包字节并检查完整values，保留原类型和非有限诊断。
本模块不读取或解码报文，不改公共records模型，不写文件或保留输入引用。
原帧临时对象和标量编码的费用由调用方在批次许可前预约；不承诺旧库RSS受控。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`_item_base_size`](#api-_item_base_size)|计算合法原帧的ITEM空值包大小，不建立固定字段的多层JSON字典。|
|[`_validate_native_frame`](#api-_validate_native_frame)|校验原生CAN消息的字段快照，不为不会保存的帧构造创建后不可修改的对象。|
|[`validate_discarded`](#api-validate_discarded)|确认未保留原消息仍满足完整记录边界，不因批次选择跳过坏数据。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from math import isfinite
from .records import MAX_WIRE_BYTES, _decoded_values_size, _integer, _scalar_size, _ITEM_FIXED_BYTES, _SMALL_ITEM_BASE_UPPER, _small_item_fits
from .worker import _frame
```

</details>

<a id="api-_item_base_size"></a>
## `_item_base_size`

计算合法原帧的ITEM空值包大小，不建立固定字段的多层JSON字典。

```python
_item_base_size(frame, sequence)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。frame为本次_frame刚校验的LegacyRawFrame|
|`sequence`|int|是|无|位置或关键字。sequence为已校验原生非负int。|

### 返回说明

含空values字典的精确UTF-8字节数。

### 异常说明

原整数转换、文本编码或大小错误。

本函数直接报告的具体错误：

- `ValueError`：wire包超过65536字节。

### 边界说明

标志按true/false计长，未知is_rx按null计长；原浮点repr保负零和指数，data每字节为两位hex。

源码：[`src/chronaxis/legacy/batch_validation.py:18`](../../../src/chronaxis/legacy/batch_validation.py#L18)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_validate_native_frame"></a>
## `_validate_native_frame`

校验原生CAN消息的字段快照，不为不会保存的帧构造创建后不可修改的对象。

```python
_validate_native_frame(msg, values, sequence)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`msg`|can.Message|是|无|位置或关键字。同次旧库读取器产生的原始Message实例，调用方已核对其精确类型。|
|`values`|Mapping|是|无|位置或关键字。values和sequence仍未校验。|
|`sequence`|int|是|无|位置或关键字。该帧在原始读取顺序中的序号，尚未在此函数中完成范围校验。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

与原_frame及未选记录检查一致的字段、值、编码或大小错误。

本函数直接报告的具体错误：

- `ValueError`：原报文data超过64字节，不能先复制再拒绝。
- `ValueError`：原报文timestamp需要有限float秒。
- `ValueError`：原报文data需要不超过64字节的bytes。
- `TypeError`：原报文channel需要int/str/None。
- `ValueError`：原报文channel文本过长。
- `TypeError`：解码记录需要LegacyRawFrame与数值Mapping。
- `ValueError`：wire包超过65536字节。

### 流程说明

按原构造实参顺序读取字段和转换data，随后保持原模型的校验先后。
常见完整值字典可用安全上界证明合法；无法证明时仍走原精确检查函数。

源码：[`src/chronaxis/legacy/batch_validation.py:39`](../../../src/chronaxis/legacy/batch_validation.py#L39)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-validate_discarded"></a>
## `validate_discarded`

确认未保留原消息仍满足完整记录边界，不因批次选择跳过坏数据。

```python
validate_discarded(msg, values, sequence, *, native_message_type=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`msg`|native_message_type|是|无|位置或关键字。msg为本次原yield消息|
|`values`|Mapping|是|无|位置或关键字。values为原parse返回的完整Mapping|
|`sequence`|int|是|无|位置或关键字。sequence为原序号。     native_message_type可由worker在旧库加载完成后传入其真实Message类|
|`native_message_type`|type &#124; None|否|None|仅关键字。worker实际导入的can.Message类，用于检查精确类型；未提供时按函数原有检查路径处理。|

### 返回说明

None；既不复制values，也不持有通过检查的数据。

### 异常说明

原帧、序号、Mapping、信号名称/类型、Unicode或单条超限错误原样传播。

本函数直接报告的具体错误：

- `TypeError`：解码记录需要LegacyRawFrame与数值Mapping。

### 处理流程说明

原字段校验→安全上界正证明，或原ITEM精确计长与完整values检查。没有待保存副本，
    所以不执行公共LegacyDecodedFrame为防止复制时Mapping变化而进行的第二遍检查。

源码：[`src/chronaxis/legacy/batch_validation.py:110`](../../../src/chronaxis/legacy/batch_validation.py#L110)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
