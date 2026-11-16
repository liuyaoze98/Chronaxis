# `chronaxis.execution.integral_blocks`

并行积分的冻结任务与有界二进制块；只恢复列出的数值模型。

面积以网络序float64传输，不求和、不转换单位。首尾同一时刻组保留定宽原值、
质量和序号；精确时间使用Decimal元组，避免十进制上下文影响文件顺序检查。
任务只包含声明、表达式文本及必要积分字段，不传可调用对象或任意Python对象。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition)、[FileIntegralFrontier](chronaxis.execution.file_integral_terms.md#api-FileIntegralFrontier)、[FileIntegralHead](chronaxis.execution.file_integral_terms.md#api-FileIntegralHead)、[FileIntegralTail](chronaxis.execution.file_integral_terms.md#api-FileIntegralTail)、[IntegralTermsChunk](chronaxis.execution.file_integral_terms.md#api-IntegralTermsChunk)、[Interval](chronaxis.core.models.md#api-Interval)、[SameFrameBinding](chronaxis.execution.same_frame_integrals.md#api-SameFrameBinding)、[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

## 对象导航

|对象|用途|
|---|---|
|[`_timebase`](#api-_timebase)|展开固定时基。|
|[`_restore_timebase`](#api-_restore_timebase)|恢复固定时基。|
|[`_interval`](#api-_interval)|展开可空请求范围。|
|[`_restore_interval`](#api-_restore_interval)|恢复可空范围。|
|[`pack_task`](#api-pack_task)|展开已验证数值任务，不读取文件。|
|[`check_task`](#api-check_task)|核冻结任务外形及数量，拒绝额外指令。|
|[`restore_task`](#api-restore_task)|仅通过明确构造器重建数值任务，并核原声明身份。|
|[`IntegralPacket`](#api-IntegralPacket)|一个已核验数据块；eof标明数据终点，完整资源释放另等finished控制确认。|
|[`IntegralBlockError`](#api-IntegralBlockError)|面积块格式、长度或展开量不满足固定协议。|
|[`event_cost`](#api-event_cost)|按固定字段计算事件的保守传输/展开上界，不遍历每个面积值。|
|[`_group_cost`](#api-_group_cost)|按最大整数编码估算首尾边界。|
|[`_compatibility_cost`](#api-_compatibility_cost)|按UTF-8长度估算兼容提示图。|
|[`facts_cost`](#api-facts_cost)|估算固定事实的传输和展开，复用每批未变化的兼容字段图费用。|
|[`boundary_supported`](#api-boundary_supported)|判断声明的单个首尾边界及全部兼容提示能否进入既有有界包。|
|[`_Writer`](#api-_Writer)|在512KiB包长内构造固定字段；body只持有当前包的bytearray正文。|
|[`_Writer.__init__`](#api-_Writer-__init__)|初始化有限字节区。|
|[`_Writer.add`](#api-_Writer-add)|追加片段前核上限。|
|[`_Writer.byte`](#api-_Writer-byte)|写uint8。|
|[`_Writer.count`](#api-_Writer-count)|写uint32数量。|
|[`_Writer.integer`](#api-_Writer-integer)|无损写有界整数。|
|[`_Writer.decimal`](#api-_Writer-decimal)|写精确时间元组。|
|[`_Reader`](#api-_Reader)|先检查数量再分配模型；data为借用包，position为字节游标，expansion为累计展开字节数。|
|[`_Reader.__init__`](#api-_Reader-__init__)|核包头。|
|[`_Reader.take`](#api-_Reader-take)|读取有限片段。|
|[`_Reader.charge`](#api-_Reader-charge)|核模型展开费用。|
|[`_Reader.byte`](#api-_Reader-byte)|读取uint8。|
|[`_Reader.boolean`](#api-_Reader-boolean)|读取精确bool。|
|[`_Reader.count`](#api-_Reader-count)|读取受限数量。|
|[`_Reader.integer`](#api-_Reader-integer)|恢复整数或None。|
|[`_Reader.decimal`](#api-_Reader-decimal)|恢复精确时间。|
|[`_write_scalar`](#api-_write_scalar)|写规范数值。|
|[`_read_scalar`](#api-_read_scalar)|恢复规范数值。|
|[`_write_group`](#api-_write_group)|写同一时刻边界摘要。|
|[`_read_group`](#api-_read_group)|恢复同一时刻边界摘要。|
|[`encode_packet`](#api-encode_packet)|编码一个面积事件块，不改变浮点位型或事件顺序。|
|[`decode_packet`](#api-decode_packet)|恢复一个固定事件块，并核完整消费与有界模型。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from decimal import Decimal
from .._control_models import extract, keys, native, pack_signal, restore_signal
```

</details>

<a id="api-_timebase"></a>
## `_timebase`

展开固定时基。

```python
_timebase(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|位置或关键字。要展开的已验证时基，保留名称、时间类型和原点。|

### 返回说明

dict。

### 异常说明

非法模型时AttributeError。

源码：[`src/chronaxis/execution/integral_blocks.py:29`](../../../src/chronaxis/execution/integral_blocks.py#L29)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_restore_timebase"></a>
## `_restore_timebase`

恢复固定时基。

```python
_restore_timebase(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。只含timebase_id、time_type和origin的固定JSON对象。|

### 返回说明

TimebaseSpec。

### 异常说明

字段或枚举错误时ValueError，原构造错误继续传播。

源码：[`src/chronaxis/execution/integral_blocks.py:34`](../../../src/chronaxis/execution/integral_blocks.py#L34)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_interval"></a>
## `_interval`

展开可空请求范围。

```python
_interval(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|是|无|位置或关键字。实际纳秒范围；None保留没有显式请求范围的含义。|

### 返回说明

list[int]或None，依次为起止纳秒。

### 异常说明

非法模型时AttributeError。

源码：[`src/chronaxis/execution/integral_blocks.py:43`](../../../src/chronaxis/execution/integral_blocks.py#L43)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_restore_interval"></a>
## `_restore_interval`

恢复可空范围。

```python
_restore_interval(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list[int] &#124; None|是|无|位置或关键字。依次为起止纳秒的两元素列表；None保持无显式范围，其他长度拒绝。|

### 返回说明

Interval或None。

### 异常说明

结构错误时ValueError，原时间类型或范围错误继续传播。

源码：[`src/chronaxis/execution/integral_blocks.py:48`](../../../src/chronaxis/execution/integral_blocks.py#L48)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-pack_task"></a>
## `pack_task`

展开已验证数值任务，不读取文件。

```python
pack_task(definitions, expressions, specs, binding, session_id, *, derived=(), domain=None, batch_intervals=64)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。本次积分实际依赖的信号定义，按冻结顺序排列；已由同次DBC事实补齐有效期。|
|`expressions`|tuple[StaticExpression, ...]|是|无|位置或关键字。已验证的简单数值表达式，与积分计算项顺序一致。|
|`specs`|tuple[[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition), ...]|是|无|位置或关键字。与表达式逐项对应的会话积分请求，保留请求单位及完整性规则。|
|`binding`|[SameFrameBinding](chronaxis.execution.same_frame_integrals.md#api-SameFrameBinding)|是|无|位置或关键字。首帧前由同次DBC元数据证明的唯一共同报文定位。|
|`session_id`|str|是|无|位置或关键字。本次连续分析的会话名称，文件切换时保持不变。|
|`derived`|tuple[[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition), ...]|否|()|仅关键字。原计划的派生声明，默认空tuple；用于核对表达式身份，不新增输出。|
|`domain`|[Interval](chronaxis.core.models.md#api-Interval) &#124; None|否|None|仅关键字。实际纳秒坐标中的请求范围；None表示按已有观测范围处理，不创建第二套时钟。|
|`batch_intervals`|int|否|64|仅关键字。单个传输面积块的区间上限，默认64，允许1至64；不是原帧读取数或采样周期。|

### 返回说明

dict，只含固定JSON原生值，不包含可调用对象。

### 异常说明

非支持绑定、声明不一致或块上限非法时ValueError；原模型展开错误继续传播。

源码：[`src/chronaxis/execution/integral_blocks.py:56`](../../../src/chronaxis/execution/integral_blocks.py#L56)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-check_task"></a>
## `check_task`

核冻结任务外形及数量，拒绝额外指令。

```python
check_task(task)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`task`|dict[str, object]|是|无|位置或关键字。pack_task格式的固定任务树；核白名单、列表数量和会话积分操作，不接收额外指令。|

### 返回说明

None。

### 异常说明

ValueError。

源码：[`src/chronaxis/execution/integral_blocks.py:90`](../../../src/chronaxis/execution/integral_blocks.py#L90)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-restore_task"></a>
## `restore_task`

仅通过明确构造器重建数值任务，并核原声明身份。

```python
restore_task(task)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`task`|dict[str, object]|是|无|位置或关键字。已接收的固定数值任务树；仍核对字段和声明身份，只调用列出的模型构造器。|

### 返回说明

dict[str, object]，供FileIntegralTerms构造时展开。

### 异常说明

固定字段或声明身份不一致时ValueError；原类型、表达式和声明构造错误继续传播。
此处不加载DBC和报文文件。

源码：[`src/chronaxis/execution/integral_blocks.py:115`](../../../src/chronaxis/execution/integral_blocks.py#L115)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-IntegralPacket"></a>
## `IntegralPacket`

一个已核验数据块；eof标明数据终点，完整资源释放另等finished控制确认。

```python
class IntegralPacket
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`file_index`|int|是|无|原来源声明中的零起文件序号，不按worker完成先后重排。|
|`number`|int|是|无|当前文件从0递增的块序号。|
|`events`|tuple[[FileIntegralHead](chronaxis.execution.file_integral_terms.md#api-FileIntegralHead) &#124; [IntegralTermsChunk](chronaxis.execution.file_integral_terms.md#api-IntegralTermsChunk) &#124; [FileIntegralTail](chronaxis.execution.file_integral_terms.md#api-FileIntegralTail) &#124; [FileIntegralFrontier](chronaxis.execution.file_integral_terms.md#api-FileIntegralFrontier), ...]|是|无|固定事件的原序集合；没有逐帧载荷或文件部分和。|
|`eof`|bool|是|无|数据终点标志；完整资源释放必须继续等待finished控制确认。|
|`facts`|dict|是|无|同次原帧计数、实际首末范围、精确顺序时间及必要帧型提示。|

源码：[`src/chronaxis/execution/integral_blocks.py:152`](../../../src/chronaxis/execution/integral_blocks.py#L152)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-IntegralBlockError"></a>
## `IntegralBlockError`

面积块格式、长度或展开量不满足固定协议。

```python
class IntegralBlockError(ValueError)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/integral_blocks.py:161`](../../../src/chronaxis/execution/integral_blocks.py#L161)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-event_cost"></a>
## `event_cost`

按固定字段计算事件的保守传输/展开上界，不遍历每个面积值。

```python
event_cost(event)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|[FileIntegralHead](chronaxis.execution.file_integral_terms.md#api-FileIntegralHead) &#124; [IntegralTermsChunk](chronaxis.execution.file_integral_terms.md#api-IntegralTermsChunk) &#124; [FileIntegralTail](chronaxis.execution.file_integral_terms.md#api-FileIntegralTail) &#124; [FileIntegralFrontier](chronaxis.execution.file_integral_terms.md#api-FileIntegralFrontier)|是|无|位置或关键字。已形成的首组、内部面积、末组或错误前缀已关闭边界事件；不含文件部分和。|

### 返回说明

tuple[int, int]，依次为保守编码字节数及模型展开字节数，不含整包事实。

### 异常说明

不支持事件时IntegralBlockError；只用于有界分块，不代替解码校验。

源码：[`src/chronaxis/execution/integral_blocks.py:165`](../../../src/chronaxis/execution/integral_blocks.py#L165)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_group_cost"></a>
## `_group_cost`

按最大整数编码估算首尾边界。

```python
_group_cost(count)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`count`|int|是|无|位置或关键字。已验证的非负信号字段数；按每字段最大整数和标量编码估算首尾摘要。|

### 返回说明

tuple[int, int]，依次为保守编码和模型展开字节数。

### 异常说明

合法内部计数不抛业务异常。

源码：[`src/chronaxis/execution/integral_blocks.py:183`](../../../src/chronaxis/execution/integral_blocks.py#L183)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_compatibility_cost"></a>
## `_compatibility_cost`

按UTF-8长度估算兼容提示图。

```python
_compatibility_cost(names)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`names`|Iterable[str]|是|无|位置或关键字。规范CAN字段键序列，按每项实际UTF-8长度估算兼容提示编码与展开。|

### 返回说明

tuple[int, int]，依次为保守编码和模型展开字节数。

### 异常说明

字符不能编码时UnicodeEncodeError；非法内部类型错误继续传播。

源码：[`src/chronaxis/execution/integral_blocks.py:192`](../../../src/chronaxis/execution/integral_blocks.py#L192)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-facts_cost"></a>
## `facts_cost`

估算固定事实的传输和展开，复用每批未变化的兼容字段图费用。

```python
facts_cost(facts, cache)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|dict[str, object]|是|无|位置或关键字。同次读取事实：原帧/解码累计数、实际首末纳秒、Decimal顺序时间及compatibility_fields tuple。|
|`cache`|dict[int, tuple[int, int]]|是|无|位置或关键字。当前批次的费用缓存，以compatibility_fields tuple的对象身份为键，值为编码/展开字节数；不跨无限批保留。|

### 返回说明

tuple[int, int]，依次为保守编码和模型展开字节数。

### 异常说明

缺字段时KeyError；原时间类型或UTF-8编码错误继续传播。
仅在形成事件或封包时调用，不逐帧扫描字段名。

源码：[`src/chronaxis/execution/integral_blocks.py:203`](../../../src/chronaxis/execution/integral_blocks.py#L203)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-boundary_supported"></a>
## `boundary_supported`

判断声明的单个首尾边界及全部兼容提示能否进入既有有界包。

```python
boundary_supported(definitions)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|Sequence[SignalDefinition]|是|无|位置或关键字。已验证的必要信号定义；只据声明数量和字段键检查单个首尾摘要能否装入既有包，不读取DBC或原帧。|

### 返回说明

bool；False表示单个边界过宽，调用方在首帧前选择原执行路线。

### 异常说明

非法声明时AttributeError或TypeError，字段编码错误继续传播；不读取输入。
时间和包头另留64KiB/1MiB，
    运行时仍按实际精确时间与事实长度封包，不截短或改成浮点时间。

源码：[`src/chronaxis/execution/integral_blocks.py:222`](../../../src/chronaxis/execution/integral_blocks.py#L222)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Writer"></a>
## `_Writer`

在512KiB包长内构造固定字段；body只持有当前包的bytearray正文。

```python
_Writer()
```


源码：[`src/chronaxis/execution/integral_blocks.py:236`](../../../src/chronaxis/execution/integral_blocks.py#L236)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Writer-__init__"></a>
### `_Writer.__init__`

初始化有限字节区。

```python
_Writer.__init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，构造编码器。

#### 异常说明

MemoryError。

源码：[`src/chronaxis/execution/integral_blocks.py:238`](../../../src/chronaxis/execution/integral_blocks.py#L238)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Writer-add"></a>
### `_Writer.add`

追加片段前核上限。

```python
_Writer.add(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|bytes|是|无|位置或关键字。待追加到当前正文的编码片段；追加后含8字节包头仍不得超过WIRE_LIMIT。|

#### 返回说明

None。

#### 异常说明

IntegralBlockError。

源码：[`src/chronaxis/execution/integral_blocks.py:241`](../../../src/chronaxis/execution/integral_blocks.py#L241)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Writer-byte"></a>
### `_Writer.byte`

写uint8。

```python
_Writer.byte(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。要写入的无符号8位值，0至255；调用方已按字段含义约束。|

#### 返回说明

None。

#### 异常说明

范围或包长错误。

源码：[`src/chronaxis/execution/integral_blocks.py:245`](../../../src/chronaxis/execution/integral_blocks.py#L245)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Writer-count"></a>
### `_Writer.count`

写uint32数量。

```python
_Writer.count(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。要写入的无符号32位数量，不是负索引。|

#### 返回说明

None。

#### 异常说明

范围或包长错误。

源码：[`src/chronaxis/execution/integral_blocks.py:248`](../../../src/chronaxis/execution/integral_blocks.py#L248)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Writer-integer"></a>
### `_Writer.integer`

无损写有界整数。

```python
_Writer.integer(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; None|是|无|位置或关键字。无损编码的原生整数或缺值；幅值最多128位，None使用独立标记。|

#### 返回说明

None。

#### 异常说明

类型或长度错误。

源码：[`src/chronaxis/execution/integral_blocks.py:251`](../../../src/chronaxis/execution/integral_blocks.py#L251)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Writer-decimal"></a>
### `_Writer.decimal`

写精确时间元组。

```python
_Writer.decimal(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|Decimal &#124; None|是|无|位置或关键字。有限的精确顺序时间；编码符号、十进制数字与指数，不转为float。|

#### 返回说明

None。

#### 异常说明

类型/包长错误。

源码：[`src/chronaxis/execution/integral_blocks.py:258`](../../../src/chronaxis/execution/integral_blocks.py#L258)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Reader"></a>
## `_Reader`

先检查数量再分配模型；data为借用包，position为字节游标，expansion为累计展开字节数。

```python
_Reader(packet)
```


源码：[`src/chronaxis/execution/integral_blocks.py:267`](../../../src/chronaxis/execution/integral_blocks.py#L267)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Reader-__init__"></a>
### `_Reader.__init__`

核包头。

```python
_Reader.__init__(packet)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|bytes|是|无|位置或关键字。包含固定8字节包头的完整积分包，长度为8至WIRE_LIMIT字节。|

#### 返回说明

None，构造解码器。

#### 异常说明

格式或长度错误时IntegralBlockError。

源码：[`src/chronaxis/execution/integral_blocks.py:269`](../../../src/chronaxis/execution/integral_blocks.py#L269)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Reader-take"></a>
### `_Reader.take`

读取有限片段。

```python
_Reader.take(size)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`size`|int|是|无|位置或关键字。本次从游标读取的非负字节数；超过剩余长度时报IntegralBlockError。|

#### 返回说明

bytes。

#### 异常说明

截断错误。

源码：[`src/chronaxis/execution/integral_blocks.py:275`](../../../src/chronaxis/execution/integral_blocks.py#L275)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Reader-charge"></a>
### `_Reader.charge`

核模型展开费用。

```python
_Reader.charge(size)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`size`|int|是|无|位置或关键字。即将展开模型的非负字节估算，累计不得超过MODEL_LIMIT。|

#### 返回说明

None。

#### 异常说明

超过MODEL_LIMIT时IntegralBlockError。

源码：[`src/chronaxis/execution/integral_blocks.py:279`](../../../src/chronaxis/execution/integral_blocks.py#L279)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Reader-byte"></a>
### `_Reader.byte`

读取uint8。

```python
_Reader.byte()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

截断。

源码：[`src/chronaxis/execution/integral_blocks.py:283`](../../../src/chronaxis/execution/integral_blocks.py#L283)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Reader-boolean"></a>
### `_Reader.boolean`

读取精确bool。

```python
_Reader.boolean()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

非0/1标志。

源码：[`src/chronaxis/execution/integral_blocks.py:286`](../../../src/chronaxis/execution/integral_blocks.py#L286)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Reader-count"></a>
### `_Reader.count`

读取受限数量。

```python
_Reader.count(maximum=4096)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`maximum`|int|否|4096|位置或关键字。该字段允许的数量上限，默认4096；读出数量还不得超过当前包的剩余字节数。|

#### 返回说明

int。

#### 异常说明

超限或截断。

源码：[`src/chronaxis/execution/integral_blocks.py:291`](../../../src/chronaxis/execution/integral_blocks.py#L291)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Reader-integer"></a>
### `_Reader.integer`

恢复整数或None。

```python
_Reader.integer()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

int|None。

#### 异常说明

标记/长度错误。

源码：[`src/chronaxis/execution/integral_blocks.py:296`](../../../src/chronaxis/execution/integral_blocks.py#L296)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_Reader-decimal"></a>
### `_Reader.decimal`

恢复精确时间。

```python
_Reader.decimal()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

Decimal|None。

#### 异常说明

数字或指数错误。

源码：[`src/chronaxis/execution/integral_blocks.py:304`](../../../src/chronaxis/execution/integral_blocks.py#L304)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_write_scalar"></a>
## `_write_scalar`

写规范数值。

```python
_write_scalar(writer, value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`writer`|[_Writer](chronaxis.execution.integral_blocks.md#api-_Writer)|是|无|位置或关键字。当前积分包的有限编码器。|
|`value`|[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)|是|无|位置或关键字。INT64、UINT64或FLOAT64规范标量；不允许labels、枚举原码或partial扩展状态。|

### 返回说明

None。

### 异常说明

非支持值类型。

源码：[`src/chronaxis/execution/integral_blocks.py:315`](../../../src/chronaxis/execution/integral_blocks.py#L315)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_read_scalar"></a>
## `_read_scalar`

恢复规范数值。

```python
_read_scalar(reader)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|[_Reader](chronaxis.execution.integral_blocks.md#api-_Reader)|是|无|位置或关键字。当前积分包的有界解码器，恢复类型、数值、有效性和质量。|

### 返回说明

ScalarValue。

### 异常说明

类型/质量/结构错误。

源码：[`src/chronaxis/execution/integral_blocks.py:326`](../../../src/chronaxis/execution/integral_blocks.py#L326)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_write_group"></a>
## `_write_group`

写同一时刻边界摘要。

```python
_write_group(writer, group)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`writer`|[_Writer](chronaxis.execution.integral_blocks.md#api-_Writer)|是|无|位置或关键字。当前积分包编码器。|
|`group`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)|是|无|位置或关键字。首末同一时刻摘要，字段数与首值、末值、冲突位置tuple对应。|

### 返回说明

None。

### 异常说明

包长或字段错误。

源码：[`src/chronaxis/execution/integral_blocks.py:339`](../../../src/chronaxis/execution/integral_blocks.py#L339)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_read_group"></a>
## `_read_group`

恢复同一时刻边界摘要。

```python
_read_group(reader)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|[_Reader](chronaxis.execution.integral_blocks.md#api-_Reader)|是|无|位置或关键字。当前积分包解码器；先核字段数量并记展开费用，再恢复同一时刻摘要。|

### 返回说明

SameTimeGroupSummary。

### 异常说明

固定模型错误。

源码：[`src/chronaxis/execution/integral_blocks.py:348`](../../../src/chronaxis/execution/integral_blocks.py#L348)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-encode_packet"></a>
## `encode_packet`

编码一个面积事件块，不改变浮点位型或事件顺序。

```python
encode_packet(file_index, number, events, eof, facts)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`file_index`|int|是|无|位置或关键字。来源声明中的零起文件序号，按配置顺序消费，不按工作进程完成次序重排。|
|`number`|int|是|无|位置或关键字。该文件从0递增的数据块序号，父进程逐包核对。|
|`events`|tuple[[FileIntegralHead](chronaxis.execution.file_integral_terms.md#api-FileIntegralHead) &#124; [IntegralTermsChunk](chronaxis.execution.file_integral_terms.md#api-IntegralTermsChunk) &#124; [FileIntegralTail](chronaxis.execution.file_integral_terms.md#api-FileIntegralTail) &#124; [FileIntegralFrontier](chronaxis.execution.file_integral_terms.md#api-FileIntegralFrontier), ...]|是|无|位置或关键字。本包按顺序交付的有限事件，不改变原面积float64位型。|
|`eof`|bool|是|无|位置或关键字。标记最后数据包；读取器和数值owner已关闭，发送后的工作区释放由finished另行确认。|
|`facts`|dict[str, object]|是|无|位置或关键字。同次读取事实：原帧/解码累计数、实际首末纳秒、Decimal顺序时间及compatibility_fields tuple。|

### 返回说明

bytes，含包头最多512KiB；不会把文件面积先累计成部分和。

### 异常说明

未支持事件或超限时IntegralBlockError；字段、编码及struct原错误继续传播。

源码：[`src/chronaxis/execution/integral_blocks.py:358`](../../../src/chronaxis/execution/integral_blocks.py#L358)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-decode_packet"></a>
## `decode_packet`

恢复一个固定事件块，并核完整消费与有界模型。

```python
decode_packet(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|bytes|是|无|位置或关键字。完整积分二进制包；核版本、长度、有限计数、精确时间和尾随内容。|

### 返回说明

IntegralPacket，保留事件顺序和精确时间。

### 异常说明

截断、非法计数/事件或展开超限时IntegralBlockError；非法UTF-8及固定模型构造错误继续传播。
只重建列出的模型，不加载任意类。

源码：[`src/chronaxis/execution/integral_blocks.py:395`](../../../src/chronaxis/execution/integral_blocks.py#L395)（行号对应 Chronaxis 0.1.0.dev5 源码）。
