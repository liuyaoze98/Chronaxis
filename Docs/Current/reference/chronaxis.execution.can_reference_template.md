# chronaxis.execution.can_reference_template

复用已校验CAN定位的固定部分，逐条仍验证原序号、原时间和量化标志。

输入是同一运行绑定中的固定来源字段；构造时调用公开CANSourceRef完整验证一次。
输出仍是原生冻结CANSourceRef，所有字段及公开编码不变。这里只省固定声明的重复
规范JSON编码，不读取DBC、不改变reader/decoder，也不缓存报文。模板费用及生成引用
的费用由调用owner在创建前支付；模板随该owner释放，没有全局缓存或独立I/O。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CANSourceRef](chronaxis.sources.can_spec.md#api-CANSourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`CANReferenceTemplate`](#api-CANReferenceTemplate)|持有一份只读固定字段快照；每次at只创建当前报文引用，不复用可变行。|
|[`CANReferenceTemplate.__init__`](#api-CANReferenceTemplate-__init__)|先用公开构造器校验固定字段，再保存独立只读快照。|
|[`CANReferenceTemplate.at`](#api-CANReferenceTemplate-at)|检查当前报文的序号、时间和量化标记，与固定的来源信息组合成CANSourceRef。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from types import MappingProxyType
from dataclasses import dataclass
from ..sources.can_spec import CANSourceRef, _nonnegative_integer
```

</details>

<a id="api-CANReferenceTemplate"></a>
## `CANReferenceTemplate`

持有一份只读固定字段快照；每次at只创建当前报文引用，不复用可变行。

```python
CANReferenceTemplate(session_id, source_name, field, path, profile, channel, signal, frame_id, is_extended, is_fd)
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`_fields`|object|不直接填写|由自定义构造器建立；见 __init__|公开模型完整校验后的只读字段，不借用外部dict。|

源码：[`src/chronaxis/execution/can_reference_template.py:17`](../../../src/chronaxis/execution/can_reference_template.py#L17)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANReferenceTemplate-__init__"></a>
### `CANReferenceTemplate.__init__`

先用公开构造器校验固定字段，再保存独立只读快照。

```python
CANReferenceTemplate.__init__(session_id, source_name, field, path, profile, channel, signal, frame_id, is_extended, is_fd)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`session_id`|str|是|无|位置或关键字。本次会话的名字，用来防止把不同试验的数据混在一起。|
|`source_name`|str|是|无|位置或关键字。计划中已声明的来源名，例如bus；不是信号别名。|
|`field`|str|是|无|位置或关键字。完整原字段定位字符串，包含来源合同中的消息和信号定位信息；不作为分析表达式解析。|
|`path`|str|是|无|位置或关键字。原输入文件路径，写入来源引用以便回查；路径本身不表示时钟或单位已匹配。|
|`profile`|str|是|无|位置或关键字。旧解码实现的名称；M3使用"sclicer-functions-v1"，用于记录实际调用的解码路径。|
|`channel`|int|是|无|位置或关键字。内部0基CAN通道，非负整数，须与已解析来源一致。用户配置从1开始，进入本模型前已减1。|
|`signal`|str|是|无|位置或关键字。DBC中的信号名称，保留原有大小写。|
|`frame_id`|int|是|无|位置或关键字。实际帧ID整数，与通道、标准/扩展、FD标志共同定位消息。|
|`is_extended`|bool|是|无|位置或关键字。实际消息是否扩展帧的布尔值。|
|`is_fd`|bool|是|无|位置或关键字。实际消息是否CAN FD的布尔值。|

#### 返回说明

已校验模板。

#### 异常说明

原公开模型的身份/定位/类型/编码错误。

源码：[`src/chronaxis/execution/can_reference_template.py:22`](../../../src/chronaxis/execution/can_reference_template.py#L22)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-CANReferenceTemplate-at"></a>
### `CANReferenceTemplate.at`

检查当前报文的序号、时间和量化标记，与固定的来源信息组合成CANSourceRef。

```python
CANReferenceTemplate.at(yield_sequence, timestamp_s, time_quantized)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`yield_sequence`|int|是|无|位置或关键字。原读取器产出次序的非负整数，不根据时间重新编号。|
|`timestamp_s`|float|是|无|位置或关键字。旧读取器给出的原生float秒值；保留原值，不冒称恢复其已丢失精度。|
|`time_quantized`|bool|是|无|位置或关键字。时间转换是否发生纳秒量化的布尔标志。|

#### 返回说明

新的冻结CANSourceRef；原始float位值和全部定位保持。

#### 异常说明

与公开构造器动态字段相同的TypeError/ValueError，不隐式转换。

本函数直接报告的具体错误：

- `TypeError`：CANSourceRef timestamp需要原生float秒。
- `ValueError`：CANSourceRef timestamp必须有限。
- `TypeError`：CANSourceRef time_quantized需要bool。

源码：[`src/chronaxis/execution/can_reference_template.py:38`](../../../src/chronaxis/execution/can_reference_template.py#L38)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
