# chronaxis.legacy.binding

用报文 ID、所需信号和实际帧类型选择 DBC 定义。

本模块只使用调用方已加载的数据库，不打开 DBC 或日志。候选表仅覆盖当前
请求字段；每次运行保存有限的已见身份，避免省略帧型时混合两种同 ID 报文。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`field_matches`](#api-field_matches)|判断可选帧型约束是否接受当前实际帧。|
|[`dbc_candidates`](#api-dbc_candidates)|从已有DBC中保留同时含所需信号的报文候选。|
|[`select_message`](#api-select_message)|按照实际帧选择唯一定义，优先同型，再使用已批准的FD声明兼容。|
|[`FrameBindingResolver`](#api-FrameBindingResolver)|持有本次所需定义及已见身份；不保存报文载荷或无关信号。|
|[`FrameBindingResolver.__init__`](#api-FrameBindingResolver-__init__)|为本次所需信号建立有限DBC候选，不保存日志副本。|
|[`FrameBindingResolver.fields_for`](#api-FrameBindingResolver-fields_for)|依据实际帧取得本次绑定，并拒绝后来出现的另一种匹配身份。|
|[`FrameBindingResolver.message_for`](#api-FrameBindingResolver-message_for)|依据实际帧取得本次绑定，并拒绝后来出现的另一种匹配身份。|
|[`FrameBindingResolver.missing_flags`](#api-FrameBindingResolver-missing_flags)|仅补原始CSV缺失的类型信息，已有列保持原值。|

<a id="api-field_matches"></a>
## `field_matches`

判断可选帧型约束是否接受当前实际帧。

```python
field_matches(field, frame)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`field`|LegacyCANField|是|无|位置或关键字。本次信号定位，None帧型表示不限定。|
|`frame`|LegacyRawFrame|是|无|位置或关键字。实际原帧，含真实通道、ID和两个类型标志。|

### 返回说明

bool；这里只判断身份，不解码。

### 异常说明

属性访问错误表示调用方未传约定模型。

源码：[`src/chronaxis/legacy/binding.py:8`](../../../src/chronaxis/legacy/binding.py#L8)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-dbc_candidates"></a>
## `dbc_candidates`

从已有DBC中保留同时含所需信号的报文候选。

```python
dbc_candidates(db, frame_id, signal_names=(), is_extended=None, is_fd=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`db`|cantools.database.Database|是|无|位置或关键字。调用方本次已加载的DBC；不在此重复打开文件。|
|`frame_id`|int|是|无|位置或关键字。已归一化的CAN报文ID。|
|`signal_names`|tuple[str, ...]|否|()|位置或关键字。必须同时存在且唯一的原始信号名；空元组仅按报文身份选择。|
|`is_extended`|bool &#124; None|否|None|位置或关键字。None表示未限定，运行时结合DBC及实际帧识别；False限定标准帧且ID不超过0x7FF，True限定扩展帧。Python允许None表达省略，JSON/YAML填写时只能是布尔值。|
|`is_fd`|bool &#124; None|否|None|位置或关键字。None表示未限定，按日志实际帧匹配；False限定经典CAN，True限定CAN FD。DBC为FD而实际为经典CAN可按已批准规则兼容，不修改真实帧。JSON/YAML填写时只能是布尔值。|

### 返回说明

cantools Message元组，保留不同实际类型的候选。

### 异常说明

ValueError：ID不存在、所需信号不唯一/缺失、指定类型无匹配，或同ID同类型仍有重复定义。

源码：[`src/chronaxis/legacy/binding.py:17`](../../../src/chronaxis/legacy/binding.py#L17)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-select_message"></a>
## `select_message`

按照实际帧选择唯一定义，优先同型，再使用已批准的FD声明兼容。

```python
select_message(candidates, frame)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`candidates`|tuple[cantools.database.can.Message, ...]|是|无|位置或关键字。已经筛选的DBC候选。|
|`frame`|LegacyRawFrame|是|无|位置或关键字。带实际类型的原帧，不修改其标志。|

### 返回说明

唯一Message；没有匹配时为None。

### 异常说明

ValueError：实际类型也不能排除多个定义。

源码：[`src/chronaxis/legacy/binding.py:47`](../../../src/chronaxis/legacy/binding.py#L47)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameBindingResolver"></a>
## `FrameBindingResolver`

持有本次所需定义及已见身份；不保存报文载荷或无关信号。

```python
FrameBindingResolver(db, fields)
```


源码：[`src/chronaxis/legacy/binding.py:65`](../../../src/chronaxis/legacy/binding.py#L65)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameBindingResolver-__init__"></a>
### `FrameBindingResolver.__init__`

为本次所需信号建立有限DBC候选，不保存日志副本。

```python
FrameBindingResolver.__init__(db, fields)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`db`|cantools.database.Database|是|无|位置或关键字。本次已加载DBC。|
|`fields`|tuple[LegacyCANField, ...]|是|无|位置或关键字。本次使用的信号定位；重复定位合并。|

#### 返回说明

None。

#### 异常说明

ValueError：字段、ID或DBC定义不明确。

源码：[`src/chronaxis/legacy/binding.py:69`](../../../src/chronaxis/legacy/binding.py#L69)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameBindingResolver-fields_for"></a>
### `FrameBindingResolver.fields_for`

依据实际帧取得本次绑定，并拒绝后来出现的另一种匹配身份。

```python
FrameBindingResolver.fields_for(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。本次读取的实际原帧。|

#### 返回说明

匹配字段元组；非数据帧或无匹配时为空元组。

#### 异常说明

ValueError：同一省略型绑定出现多种实际类型，或一个帧的信号指向不同DBC定义。

源码：[`src/chronaxis/legacy/binding.py:83`](../../../src/chronaxis/legacy/binding.py#L83)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameBindingResolver-message_for"></a>
### `FrameBindingResolver.message_for`

依据实际帧取得本次绑定，并拒绝后来出现的另一种匹配身份。

```python
FrameBindingResolver.message_for(frame, fields)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|LegacyRawFrame|是|无|位置或关键字。本次读取的实际原帧。|
|`fields`|tuple[LegacyCANField, ...]|是|无|位置或关键字。当前原帧实际匹配的字段，通常来自fields_for。|

#### 返回说明

匹配字段所属的唯一DBC Message；无匹配返回None。

#### 异常说明

ValueError：同一省略型绑定出现多种实际类型，或一个帧的信号指向不同DBC定义。

源码：[`src/chronaxis/legacy/binding.py:112`](../../../src/chronaxis/legacy/binding.py#L112)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-FrameBindingResolver-missing_flags"></a>
### `FrameBindingResolver.missing_flags`

仅补原始CSV缺失的类型信息，已有列保持原值。

```python
FrameBindingResolver.missing_flags(channel, frame_id, extended, fd)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`channel`|int|是|无|位置或关键字。已转换为内部0基编号的通道；用户配置通道1在此为0，不再次加减。|
|`frame_id`|int|是|无|位置或关键字。已按CSV格式规则解析的报文ID。|
|`extended`|bool &#124; None|是|无|位置或关键字。原始列中的标准/扩展标志；None表示缺列，需查本次绑定和DBC。|
|`fd`|bool &#124; None|是|无|位置或关键字。原始列中的CAN/FD标志；None表示缺列。DBC为FD仍可能对应两种实际格式。|

#### 返回说明

(is_extended_id, is_fd)两个已确定bool。

#### 异常说明

ValueError：无法唯一补足，提示需要的列映射或绑定选项。

源码：[`src/chronaxis/legacy/binding.py:128`](../../../src/chronaxis/legacy/binding.py#L128)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
