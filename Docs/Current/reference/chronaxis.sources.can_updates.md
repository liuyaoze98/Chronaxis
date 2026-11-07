# `chronaxis.sources.can_updates`

把三种原始报文入口的必要值交付给同一个逐消息计算模型。

投影只保存有限字段定位和可共享的来源引用。BLF交付的键是DBC信号名，
文本入口交付的键是规范字段；转换后均为原DBC信号名，不保留载荷副本、
原时间字符串或第二套时间。LegacyDecodedUpdate是已有计算模型的名称，
使用它不代表复现旧程序的缓存行为。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)、[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)、[LegacyUntimedUpdate](chronaxis.legacy.updates.md#api-LegacyUntimedUpdate)、[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`require_message_keys`](#api-require_message_keys)|校验有限触发声明。|
|[`CANUpdateProjection`](#api-CANUpdateProjection)|按完整报文身份索引所需字段；同一帧的多个别名只传一次物理值。|
|[`CANUpdateProjection.__init__`](#api-CANUpdateProjection-__init__)|建立有限投影，不读取DBC或输入文件。|
|[`CANUpdateProjection.configure_metadata`](#api-CANUpdateProjection-configure_metadata)|安装同次DBC候选，并将已见身份限制在当前读取中。|
|[`CANUpdateProjection.for_read`](#api-CANUpdateProjection-for_read)|安装同次DBC候选，并将已见身份限制在当前读取中。|
|[`CANUpdateProjection._matching`](#api-CANUpdateProjection-_matching)|按已解析DBC候选匹配实际帧，并拒绝迟到的身份歧义。|
|[`CANUpdateProjection.accepts_frame`](#api-CANUpdateProjection-accepts_frame)|判断是否有值或触发需求。|
|[`CANUpdateProjection.fields_for`](#api-CANUpdateProjection-fields_for)|定位目标数据帧，未知ID/其他通道或帧型不参与本投影。|
|[`CANUpdateProjection.build`](#api-CANUpdateProjection-build)|只拣选计算字段，复用已有有时间/无时间更新及其严格值检查。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from types import MappingProxyType
from ..core.models import SourceRef
from ..core.validation import require_identifier
from ..legacy.records import LegacyCANField
from ..legacy.updates import LegacyDecodedUpdate, LegacyUntimedUpdate
```

</details>

<a id="api-require_message_keys"></a>
## `require_message_keys`

校验有限触发声明。

```python
require_message_keys(keys, *, channel=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`keys`|tuple[tuple[int, int, bool, bool], ...]|是|无|位置或关键字。待核对的通道、报文ID、扩展标志和FD标志四元组集合，拒绝身份不完整或类型错误。|
|`channel`|int|否|None|仅关键字。明确的内部0基CAN通道，非负整数，不根据报文ID猜通道。配置从1开始，在进入此函数前完成转换。|

### 返回说明

原tuple。

### 异常说明

ValueError。

源码：[`src/chronaxis/sources/can_updates.py:17`](../../../src/chronaxis/sources/can_updates.py#L17)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANUpdateProjection"></a>
## `CANUpdateProjection`

按完整报文身份索引所需字段；同一帧的多个别名只传一次物理值。

```python
CANUpdateProjection(source, session_id, fields, *, message_keys=(), clock_fields=())
```


源码：[`src/chronaxis/sources/can_updates.py:31`](../../../src/chronaxis/sources/can_updates.py#L31)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANUpdateProjection-__init__"></a>
### `CANUpdateProjection.__init__`

建立有限投影，不读取DBC或输入文件。

```python
CANUpdateProjection.__init__(source, session_id, fields, *, message_keys=(), clock_fields=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|位置或关键字。投影所属来源名称，用于生成逐消息更新的来源身份。|
|`session_id`|str|是|无|位置或关键字。本次连续分析会话的标识；跨连续文件保持同一会话，独立任务各自隔离。|
|`fields`|Sequence[[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)]|是|无|位置或关键字。当前确实需要的CAN字段定位集合，包含通道、报文和信号身份。|
|`message_keys`|tuple[tuple[int, int, bool, bool], ...]|否|()|仅关键字。所需报文定位，依次为通道、ID、扩展帧标志、FD标志；空集合表示没有额外逐消息需求。|
|`clock_fields`|tuple[[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField), ...]|否|()|仅关键字。仅请求驱动信号的DBC候选声明，默认空tuple；用于确认实际帧身份，不请求信号值，也不增加普通样本或值解码。|

#### 返回说明

None；初始化实例状态。

#### 异常说明

TypeError/ValueError为字段、身份或同帧信号定位冲突。

源码：[`src/chronaxis/sources/can_updates.py:34`](../../../src/chronaxis/sources/can_updates.py#L34)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANUpdateProjection-configure_metadata"></a>
### `CANUpdateProjection.configure_metadata`

安装同次DBC候选，并将已见身份限制在当前读取中。

```python
CANUpdateProjection.configure_metadata(facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|tuple[Mapping, ...]|是|无|位置或关键字。已验证的字段元数据，包含locator及按需提供的dbc_frames。|

#### 返回说明

None；在当前投影保存已验证的有限DBC候选。

#### 异常说明

定位或元数据不合法时传播TypeError/ValueError。

源码：[`src/chronaxis/sources/can_updates.py:67`](../../../src/chronaxis/sources/can_updates.py#L67)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANUpdateProjection-for_read"></a>
### `CANUpdateProjection.for_read`

安装同次DBC候选，并将已见身份限制在当前读取中。

```python
CANUpdateProjection.for_read(facts)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|tuple[Mapping, ...]|是|无|位置或关键字。已验证的字段元数据，包含locator及按需提供的dbc_frames。|

#### 返回说明

新的CANUpdateProjection，与原投影共享声明但隔离本次读取已见身份。

#### 异常说明

定位或元数据不合法时传播TypeError/ValueError。

源码：[`src/chronaxis/sources/can_updates.py:74`](../../../src/chronaxis/sources/can_updates.py#L74)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANUpdateProjection-_matching"></a>
### `CANUpdateProjection._matching`

按已解析DBC候选匹配实际帧，并拒绝迟到的身份歧义。

```python
CANUpdateProjection._matching(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。当前原帧；远程帧和错误帧不产生信号投影。|

#### 返回说明

匹配字段和SourceRef；无匹配返回None。

#### 异常说明

ValueError：同一自动绑定遇到另一种实际类型。

源码：[`src/chronaxis/sources/can_updates.py:85`](../../../src/chronaxis/sources/can_updates.py#L85)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANUpdateProjection-accepts_frame"></a>
### `CANUpdateProjection.accepts_frame`

判断是否有值或触发需求。

```python
CANUpdateProjection.accepts_frame(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|can.Message &#124; LegacyRawFrame|是|无|位置或关键字。当前实际帧或冻结帧快照；通过公开ID、通道、标志及载荷属性检查和定位，不接受DBC定义代替输入帧。|

#### 返回说明

bool。

#### 异常说明

非原帧属性错。

源码：[`src/chronaxis/sources/can_updates.py:128`](../../../src/chronaxis/sources/can_updates.py#L128)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANUpdateProjection-fields_for"></a>
### `CANUpdateProjection.fields_for`

定位目标数据帧，未知ID/其他通道或帧型不参与本投影。

```python
CANUpdateProjection.fields_for(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|can.Message &#124; LegacyRawFrame|是|无|位置或关键字。当前实际帧或冻结帧快照；通过公开ID、通道、标志及载荷属性检查和定位，不接受DBC定义代替输入帧。|

#### 返回说明

字段元组，非目标为空。

#### 异常说明

非原帧对象缺少必需属性时AttributeError；不吞读取错误。

源码：[`src/chronaxis/sources/can_updates.py:132`](../../../src/chronaxis/sources/can_updates.py#L132)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-CANUpdateProjection-build"></a>
### `CANUpdateProjection.build`

只拣选计算字段，复用已有有时间/无时间更新及其严格值检查。

```python
CANUpdateProjection.build(frame, sequence, values, time_ns, *, canonical_keys=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|can.Message &#124; LegacyRawFrame|是|无|位置或关键字。当前实际帧或冻结帧快照；通过公开ID、通道、标志及载荷属性检查和定位，不接受DBC定义代替输入帧。|
|`sequence`|int|是|无|位置或关键字。当前记录的非负顺序号；同一时刻记录仍有独立序号，不能当作时间戳。|
|`values`|Mapping[str, int &#124; float &#124; bool &#124; str &#124; None]|是|无|位置或关键字。当前所需字段到解码值的映射；缺失保留无效，不复制无关字段。|
|`time_ns`|int &#124; None|是|无|位置或关键字。当前记录的实际纳秒时刻；仅明确不需要采集时间的输入诊断可为None。|
|`canonical_keys`|bool|否|False|仅关键字。values的键是否已转换成当前接口规定的字段键；True复用受控内部键，不重新转一遍。|

#### 返回说明

LegacyDecodedUpdate/LegacyUntimedUpdate；非目标数据帧返回None。

#### 异常说明

类型/数值/身份错误原样传播，不缓存前条值补齐缺失。

源码：[`src/chronaxis/sources/can_updates.py:141`](../../../src/chronaxis/sources/can_updates.py#L141)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
