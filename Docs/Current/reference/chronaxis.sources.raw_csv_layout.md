# chronaxis.sources.raw_csv_layout

定义原始报文CSV的列名/列号、固定值和值映射；只做列对应，不解码报文。它供已实现的raw_can_csv公共入口使用。见[完整例子](../text-inputs.md)。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`_scalar`](#api-_scalar)|限定可静态配置的值。|
|[`_fields`](#api-_fields)|检查严格配置键。|
|[`_physical_value`](#api-_physical_value)|校验已映射的字段类型，避免文本被隐式转成True。|
|[`_common_value`](#api-_common_value)|只识别含义明确的常用文字；显式value_map的结果不经过此函数。|
|[`ColumnMapping`](#api-ColumnMapping)|固定一种取值来源及可选值映射；复制后不可被调用方字典修改。|
|[`ColumnMapping.__post_init__`](#api-ColumnMapping-__post_init__)|校验来源并冻结映射。|
|[`ColumnMapping.from_dict`](#api-ColumnMapping-from_dict)|从严格JSON形状构造。|
|[`ColumnMapping.to_dict`](#api-ColumnMapping-to_dict)|保存明确声明，保留False/0/空值差异。|
|[`CANCSVLayout`](#api-CANCSVLayout)|声明原始报文表，不与已解码signal_csv混淆；绑定表头以前不访问文件。|
|[`CANCSVLayout.__post_init__`](#api-CANCSVLayout-__post_init__)|冻结布局并校验完整字段声明。|
|[`CANCSVLayout.from_dict`](#api-CANCSVLayout-from_dict)|加载严格布局配置。|
|[`CANCSVLayout.to_dict`](#api-CANCSVLayout-to_dict)|输出完整已采用布局供解释/追溯。|
|[`CANCSVLayout.bind_header`](#api-CANCSVLayout-bind_header)|只解析一次表头列位置。|
|[`BoundCANCSVLayout`](#api-BoundCANCSVLayout)|保存有结构检查的列位置，只访问选择列；不认证实际文件表头或内容。|
|[`BoundCANCSVLayout.__post_init__`](#api-BoundCANCSVLayout-__post_init__)|校验可独立构造的绑定。|
|[`BoundCANCSVLayout.map_row`](#api-BoundCANCSVLayout-map_row)|提取并明确映射一条表记录。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, field
from types import MappingProxyType
from collections.abc import Mapping
```

</details>

<a id="api-_scalar"></a>
## `_scalar`

限定可静态配置的值。

```python
_scalar(value, label, *, limit=MAX_FIXED_TEXT)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str &#124; int &#124; float &#124; bool &#124; None|是|无|位置或关键字。列映射中的常量或查表值，检查其是否为支持的原生标量。|
|`label`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|
|`limit`|str|否|MAX_FIXED_TEXT|仅关键字。limit文本上限。|

### 返回说明

原值。

### 异常说明

类型/长度错误。

源码：[`src/chronaxis/sources/raw_csv_layout.py:24`](../../../src/chronaxis/sources/raw_csv_layout.py#L24)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_fields"></a>
## `_fields`

检查严格配置键。

```python
_fields(value, allowed, required, label)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。待检查的配置对象，按allowed和required检查额外键及缺失键。|
|`allowed`|set[str] &#124; tuple[str, ...]|是|无|位置或关键字。该配置对象支持的全部键名，出现其他键时报错。|
|`required`|set[str] &#124; tuple[str, ...]|是|无|位置或关键字。该对象必须填写的键名集合；缺少其中任一项时报错。|
|`label`|str|是|无|位置或关键字。错误信息中的对象或字段名称，用于定位配置问题。|

### 返回说明

原dict。

### 异常说明

类型/未知缺失键。

源码：[`src/chronaxis/sources/raw_csv_layout.py:37`](../../../src/chronaxis/sources/raw_csv_layout.py#L37)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_physical_value"></a>
## `_physical_value`

校验已映射的字段类型，避免文本被隐式转成True。

```python
_physical_value(name, value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。错误信息中使用的字段名，例如channel或frame_id，用于指出哪一项填写有误。|
|`value`|str &#124; int &#124; float &#124; bool &#124; None|是|无|位置或关键字。已经从CSV列取出或经映射表转换后的字段值，再按规范字段的含义检查。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

标志/帧类型或普通字段类型错误。

本函数直接报告的具体错误：

- `ValueError`：CSV帧种类需要data/remote/error映射。
- `ValueError`：CSV载荷需要明确的十六进制文本。

源码：[`src/chronaxis/sources/raw_csv_layout.py:48`](../../../src/chronaxis/sources/raw_csv_layout.py#L48)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_common_value"></a>
## `_common_value`

只识别含义明确的常用文字；显式value_map的结果不经过此函数。

```python
_common_value(name, value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。common中当前固定报文字段的名称。|
|`value`|object|是|无|位置或关键字。本文件所有记录共用的该字段原生值，按字段类型校验。|

源码：[`src/chronaxis/sources/raw_csv_layout.py:67`](../../../src/chronaxis/sources/raw_csv_layout.py#L67)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ColumnMapping"></a>
## `ColumnMapping`

固定一种取值来源及可选值映射；复制后不可被调用方字典修改。

```python
class ColumnMapping
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`column`|str &#124; int &#124; None|否|None|字符串是列名，如 `"方向"`；整数是1～4096的列号。整数1是第一列，字符串"1"是名为1的列。列名最多256字符。 None表示不从CSV列读取，应改由constant提供值。|
|`fixed`|str &#124; int &#124; bool &#124; None|否|None|整份文件确定不变的值。例如确认全是接收帧时写 `{"fixed":true}`；不是用来掩盖未知标志的默认值。|
|`value_map`|Mapping[str, str &#124; int &#124; bool] &#124; None|否|None|1～256项原文字到目标值的对应，如 `{"Rx":true,"Tx":false}`。原文字未列出时会报错。目标类型须符合上方字段，例如is_rx的目标是布尔值。|
|`strip`|bool|否|True|true去掉单元格两端空白后再映射；false保留两端空白。不会删掉载荷字节之间的空格。|

源码：[`src/chronaxis/sources/raw_csv_layout.py:84`](../../../src/chronaxis/sources/raw_csv_layout.py#L84)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ColumnMapping-__post_init__"></a>
### `ColumnMapping.__post_init__`

校验来源并冻结映射。

```python
ColumnMapping.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

模糊来源、坏类型或超限。

本函数直接报告的具体错误：

- `ValueError`：列映射必须且只能指定column或fixed。
- `TypeError`：strip需要bool。
- `ValueError`：value_map需要1到256项映射。
- `ValueError`：列号从1开始且不超过4096。
- `ValueError`：列名需非空且不超过256字符。
- `ValueError`：value_map键需不超过256字符的文本。
- `ValueError`：strip模式的映射键不能有边缘空白。

源码：[`src/chronaxis/sources/raw_csv_layout.py:92`](../../../src/chronaxis/sources/raw_csv_layout.py#L92)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ColumnMapping-from_dict"></a>
### `ColumnMapping.from_dict`

从严格JSON形状构造。

```python
ColumnMapping.from_dict(value)
```

装饰器：`classmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。一个原始CAN CSV列的取值规则：column与fixed恰填一个，可用value_map转换列值；没有constant、mapping或default键。完整类型、长度和例子见[CSV列映射](../text-inputs.md)。|

#### 返回说明

ColumnMapping。

#### 异常说明

未知键/值错误。

源码：[`src/chronaxis/sources/raw_csv_layout.py:123`](../../../src/chronaxis/sources/raw_csv_layout.py#L123)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ColumnMapping-to_dict"></a>
### `ColumnMapping.to_dict`

保存明确声明，保留False/0/空值差异。

```python
ColumnMapping.to_dict()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

独立dict。

#### 异常说明

无。

源码：[`src/chronaxis/sources/raw_csv_layout.py:131`](../../../src/chronaxis/sources/raw_csv_layout.py#L131)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANCSVLayout"></a>
## `CANCSVLayout`

声明原始报文表，不与已解码signal_csv混淆；绑定表头以前不访问文件。

```python
class CANCSVLayout
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`fields`|Mapping[str, [ColumnMapping](chronaxis.sources.raw_csv_layout.md#api-ColumnMapping)]|是|无|原始物理字段到列或常量的映射。is_extended_id/is_fd可省略，由分析入口的已加载DBC和绑定补足；无法唯一识别会报缺项。独立读取器没有DBC时仍需给出真实类型。其余必填字段及长度要求见原始CSV输入说明。|
|`encoding`|str|否|'utf-8-sig'|支持utf-8、utf-8-sig、ascii、gbk、cp1252、iso8859-1及其标准别名；按文件实际编码填写。|
|`delimiter`|str|否|','|单字符分隔符；制表符写 `"\t"`。不能用换行、双引号或NUL作分隔符。|
|`has_header`|bool|否|True|true表示第一条未跳过的记录是表头；false表示没有表头，column要填整数列号，不能填列名。|
|`skip_rows`|int|否|0|从文件开头跳过多少条CSV记录，0～100000。例如文件头有两行说明文字，就填2；不会自动寻找表头。|
|`layout_version`|str|否|'raw-can-csv-layout-v1'|当前布局格式版本，填写这个值或省略即可。|

源码：[`src/chronaxis/sources/raw_csv_layout.py:142`](../../../src/chronaxis/sources/raw_csv_layout.py#L142)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANCSVLayout-__post_init__"></a>
### `CANCSVLayout.__post_init__`

冻结布局并校验完整字段声明。

```python
CANCSVLayout.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/缺失/未知字段或编码错误。

本函数直接报告的具体错误：

- `ValueError`：不支持的原始报文CSV布局版本。
- `TypeError`：CSV编码必须明确。
- `ValueError`：CSV分隔符需一个非换行/引号/NUL字符。
- `ValueError`：CSV需要bool表头开关和0到100000的跳过记录数。
- `TypeError`：CSV fields需要映射。
- `ValueError`：CSV物理字段缺失或未知，长度至少声明payload_length/dlc_code之一。
- `TypeError`：CSV fields值需要ColumnMapping。
- `ValueError`：无表头CSV不能按列名取值。

源码：[`src/chronaxis/sources/raw_csv_layout.py:152`](../../../src/chronaxis/sources/raw_csv_layout.py#L152)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANCSVLayout-from_dict"></a>
### `CANCSVLayout.from_dict`

加载严格布局配置。

```python
CANCSVLayout.from_dict(value)
```

装饰器：`classmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。布局字典，使用fields声明timestamp、arbitration_id、data及通道/帧标志等列映射；允许的原始字段和必填组合见[原始CAN CSV布局](../text-inputs.md)。|

#### 返回说明

CANCSVLayout。

#### 异常说明

未知键/字段/列映射错误。

本函数直接报告的具体错误：

- `TypeError`：raw_csv_layout.fields需要dict。

源码：[`src/chronaxis/sources/raw_csv_layout.py:198`](../../../src/chronaxis/sources/raw_csv_layout.py#L198)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANCSVLayout-to_dict"></a>
### `CANCSVLayout.to_dict`

输出完整已采用布局供解释/追溯。

```python
CANCSVLayout.to_dict()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

独立JSON字典。

#### 异常说明

无。

源码：[`src/chronaxis/sources/raw_csv_layout.py:208`](../../../src/chronaxis/sources/raw_csv_layout.py#L208)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANCSVLayout-bind_header"></a>
### `CANCSVLayout.bind_header`

只解析一次表头列位置。

```python
CANCSVLayout.bind_header(header=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`header`|list[str] &#124; tuple[str, ...] &#124; None|否|None|位置或关键字。文件第一行的列名。has_header=True时提供这些列名以查找column字符串；无表头时传None，column按从1开始的列号定位。|

#### 返回说明

BoundCANCSVLayout。

#### 异常说明

表头类型/重复/缺列或表头开关矛盾；不读任何记录。

本函数直接报告的具体错误：

- `ValueError`：CSV表头需要1到4096列。
- `ValueError`：CSV表头需要有限文本。
- `ValueError`：CSV表头存在重复列名。
- `ValueError`：无表头配置不能另传表头。
- `ValueError`：CSV映射列号超出表头。

源码：[`src/chronaxis/sources/raw_csv_layout.py:215`](../../../src/chronaxis/sources/raw_csv_layout.py#L215)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BoundCANCSVLayout"></a>
## `BoundCANCSVLayout`

保存有结构检查的列位置，只访问选择列；不认证实际文件表头或内容。

```python
class BoundCANCSVLayout
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`bindings`|tuple|是|无|(规范字段名,冻结映射,0基列位置或None)。|

源码：[`src/chronaxis/sources/raw_csv_layout.py:251`](../../../src/chronaxis/sources/raw_csv_layout.py#L251)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BoundCANCSVLayout-__post_init__"></a>
### `BoundCANCSVLayout.__post_init__`

校验可独立构造的绑定。

```python
BoundCANCSVLayout.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

绑定结构、字段或列号错误。

本函数直接报告的具体错误：

- `ValueError`：CSV绑定数量错误。
- `ValueError`：CSV绑定缺少物理字段。
- `ValueError`：CSV绑定需要字段/映射/位置三元组。
- `ValueError`：CSV绑定字段或映射错误。
- `ValueError`：CSV固定值与列位置矛盾。
- `ValueError`：CSV绑定列位置错误。
- `ValueError`：CSV绑定列号与位置矛盾。

源码：[`src/chronaxis/sources/raw_csv_layout.py:256`](../../../src/chronaxis/sources/raw_csv_layout.py#L256)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BoundCANCSVLayout-map_row"></a>
### `BoundCANCSVLayout.map_row`

提取并明确映射一条表记录。

```python
BoundCANCSVLayout.map_row(row, *, names=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|list[str] &#124; tuple[str, ...]|是|无|位置或关键字。CSV解析器给出的一行单元格，按已确定的列位置取值，再应用strip和value_map；未选择的列不参与报文构造。|
|`names`|Collection[str] &#124; None|否|None|仅关键字。限定本次需要提取的规范字段名称，例如只取arbitration_id先筛选；默认None提取全部已声明字段，未选择列不做内容转换。|

#### 返回说明

只读规范字段字典；时间、数值和载荷由原始CSV读取器解析。

#### 异常说明

缺列、所需单元格非文本、未登记枚举、布尔/帧类型或值类型错误。

本函数直接报告的具体错误：

- `ValueError`：CSV记录需要不超过4096列。

源码：[`src/chronaxis/sources/raw_csv_layout.py:279`](../../../src/chronaxis/sources/raw_csv_layout.py#L279)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
