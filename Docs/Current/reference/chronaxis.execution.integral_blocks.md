# `chronaxis.execution.integral_blocks`

并行积分的冻结任务与有界二进制块；只恢复列出的数值模型。

面积以网络序float64传输，不求和、不转换单位。首尾同一时刻组保留定宽原值、
质量和序号；精确时间使用Decimal元组，避免十进制上下文影响文件顺序检查。
任务只包含声明、表达式文本及必要积分字段，不传可调用对象或任意Python对象。

两种包：P5I1是concatenate面积包（mode为terms）；P5G1是time_order组点包
（mode为points，PERF-P5-ORDER-01 A2合同）。P5G1把文件事实放在事件之前，
主进程收包时用decode_points_prefix只读到事实为止，归并读回时才用
decode_points完整解码一次事件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[DeferredPointError](chronaxis.execution.file_group_points.md#api-DeferredPointError)、[DerivedDefinition](chronaxis.core.expression.md#api-DerivedDefinition)、[FileIntegralFrontier](chronaxis.execution.file_integral_terms.md#api-FileIntegralFrontier)、[FileIntegralHead](chronaxis.execution.file_integral_terms.md#api-FileIntegralHead)、[FileIntegralTail](chronaxis.execution.file_integral_terms.md#api-FileIntegralTail)、[IntegralTermsChunk](chronaxis.execution.file_integral_terms.md#api-IntegralTermsChunk)、[Interval](chronaxis.core.models.md#api-Interval)、[SameFrameBinding](chronaxis.execution.same_frame_integrals.md#api-SameFrameBinding)、[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

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
|[`task_mode`](#api-task_mode)|读取已核任务的工作模式。|
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
|[`PointPacket`](#api-PointPacket)|一个已完整解码的组点块；字段含义同IntegralPacket，事件为组点或延迟错误。|
|[`point_cost`](#api-point_cost)|按固定字段估算一个组点事件的保守编码与展开字节数，不遍历值内容。|
|[`point_facts_cost`](#api-point_facts_cost)|估算组点包事实的传输和展开字节数；两种包事实相同，直接沿用facts_cost。|
|[`_write_facts`](#api-_write_facts)|写文件事实：面积包在事件之后，组点包在事件之前。|
|[`_read_facts`](#api-_read_facts)|恢复文件事实。|
|[`_check_point_time`](#api-_check_point_time)|核组点时间。|
|[`_check_point_group`](#api-_check_point_group)|编码前核组点使用组内位置的约定。|
|[`encode_points`](#api-encode_points)|编码一个组点块，事实在事件之前，数值位型不变。|
|[`decode_points_prefix`](#api-decode_points_prefix)|收包时只核包头并读到文件事实为止，不解码事件。|
|[`decode_points`](#api-decode_points)|完整恢复一个组点块，并核完整消费与有界模型。|

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

源码：[`src/chronaxis/execution/integral_blocks.py:43`](../../../src/chronaxis/execution/integral_blocks.py#L43)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:48`](../../../src/chronaxis/execution/integral_blocks.py#L48)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:57`](../../../src/chronaxis/execution/integral_blocks.py#L57)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:62`](../../../src/chronaxis/execution/integral_blocks.py#L62)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-pack_task"></a>
## `pack_task`

展开已验证数值任务，不读取文件。

```python
pack_task(definitions, expressions, specs, binding, session_id, *, derived=(), domain=None, batch_intervals=64, step_ns=None, mode='terms')
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
|`step_ns`|int &#124; None|否|None|仅关键字。写入工作进程任务的共用间隔；None为实际间隔，否则为int64范围内正整数纳秒，check_task再次校验。|
|`mode`|str|否|'terms'|仅关键字。mode为'terms'（文件面积，默认）或'points'（同一时刻组点，只归一化和分组，不求值）。|

### 返回说明

dict，只含固定JSON原生值，不包含可调用对象。

### 异常说明

非支持绑定、声明不一致、块上限或模式非法时ValueError；原模型展开错误继续传播。

源码：[`src/chronaxis/execution/integral_blocks.py:70`](../../../src/chronaxis/execution/integral_blocks.py#L70)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:107`](../../../src/chronaxis/execution/integral_blocks.py#L107)（行号对应 Chronaxis 0.1.0 源码）。

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

dict[str, object]，供FileIntegralTerms或FileGroupPoints
    构造时展开；不含mode，模式另由task_mode读取。

### 异常说明

固定字段或声明身份不一致时ValueError；原类型、表达式和声明构造错误继续传播。
此处不加载DBC和报文文件。

源码：[`src/chronaxis/execution/integral_blocks.py:139`](../../../src/chronaxis/execution/integral_blocks.py#L139)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-task_mode"></a>
## `task_mode`

读取已核任务的工作模式。

```python
task_mode(task)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`task`|dict|是|无|位置或关键字。pack_task产生的原生任务dict。|

### 返回说明

str，'terms'或'points'。

### 异常说明

任务外形或模式非法时ValueError，与check_task相同；不重建声明。

源码：[`src/chronaxis/execution/integral_blocks.py:176`](../../../src/chronaxis/execution/integral_blocks.py#L176)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:187`](../../../src/chronaxis/execution/integral_blocks.py#L187)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-IntegralBlockError"></a>
## `IntegralBlockError`

面积块格式、长度或展开量不满足固定协议。

```python
class IntegralBlockError(ValueError)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/integral_blocks.py:196`](../../../src/chronaxis/execution/integral_blocks.py#L196)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:200`](../../../src/chronaxis/execution/integral_blocks.py#L200)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:218`](../../../src/chronaxis/execution/integral_blocks.py#L218)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:227`](../../../src/chronaxis/execution/integral_blocks.py#L227)（行号对应 Chronaxis 0.1.0 源码）。

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

tuple[int, int]，依次为保守编码和模型展开字节数（帧型字段计3字节编码及64字节展开）。

### 异常说明

缺字段时KeyError；原时间类型或UTF-8编码错误继续传播。
仅在形成事件或封包时调用，不逐帧扫描字段名。

源码：[`src/chronaxis/execution/integral_blocks.py:238`](../../../src/chronaxis/execution/integral_blocks.py#L238)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:257`](../../../src/chronaxis/execution/integral_blocks.py#L257)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_Writer"></a>
## `_Writer`

在512KiB包长内构造固定字段；body只持有当前包的bytearray正文。

```python
_Writer()
```


源码：[`src/chronaxis/execution/integral_blocks.py:271`](../../../src/chronaxis/execution/integral_blocks.py#L271)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:273`](../../../src/chronaxis/execution/integral_blocks.py#L273)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:276`](../../../src/chronaxis/execution/integral_blocks.py#L276)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:280`](../../../src/chronaxis/execution/integral_blocks.py#L280)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:283`](../../../src/chronaxis/execution/integral_blocks.py#L283)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:286`](../../../src/chronaxis/execution/integral_blocks.py#L286)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:293`](../../../src/chronaxis/execution/integral_blocks.py#L293)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_Reader"></a>
## `_Reader`

先检查数量再分配模型；data为借用包，position为字节游标，expansion为累计展开字节数。

```python
_Reader(packet, magic=b'P5I1')
```


源码：[`src/chronaxis/execution/integral_blocks.py:302`](../../../src/chronaxis/execution/integral_blocks.py#L302)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_Reader-__init__"></a>
### `_Reader.__init__`

核包头。

```python
_Reader.__init__(packet, magic=b'P5I1')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|bytes|是|无|位置或关键字。包含固定8字节包头的完整积分包，长度为8至WIRE_LIMIT字节。|
|`magic`|bytes|否|b'P5I1'|位置或关键字。magic为期望的4字节协议标志，默认面积包P5I1。|

#### 返回说明

None，构造解码器。

#### 异常说明

格式、标志或长度错误时IntegralBlockError。

源码：[`src/chronaxis/execution/integral_blocks.py:304`](../../../src/chronaxis/execution/integral_blocks.py#L304)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:313`](../../../src/chronaxis/execution/integral_blocks.py#L313)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:317`](../../../src/chronaxis/execution/integral_blocks.py#L317)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:321`](../../../src/chronaxis/execution/integral_blocks.py#L321)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:324`](../../../src/chronaxis/execution/integral_blocks.py#L324)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:329`](../../../src/chronaxis/execution/integral_blocks.py#L329)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:334`](../../../src/chronaxis/execution/integral_blocks.py#L334)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:342`](../../../src/chronaxis/execution/integral_blocks.py#L342)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:353`](../../../src/chronaxis/execution/integral_blocks.py#L353)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:364`](../../../src/chronaxis/execution/integral_blocks.py#L364)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:377`](../../../src/chronaxis/execution/integral_blocks.py#L377)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:386`](../../../src/chronaxis/execution/integral_blocks.py#L386)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:396`](../../../src/chronaxis/execution/integral_blocks.py#L396)（行号对应 Chronaxis 0.1.0 源码）。

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

源码：[`src/chronaxis/execution/integral_blocks.py:428`](../../../src/chronaxis/execution/integral_blocks.py#L428)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-PointPacket"></a>
## `PointPacket`

一个已完整解码的组点块；字段含义同IntegralPacket，事件为组点或延迟错误。

```python
class PointPacket
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`file_index`|int|是|无|原来源声明中的零起文件序号，不按worker完成先后重排。|
|`number`|int|是|无|当前文件从0递增的块序号。|
|`events`|tuple|是|无|SameTimeGroupSummary或DeferredPointError，按文件内时间顺序。|
|`eof`|bool|是|无|原帧读尽且读取器/组点owner已关闭；资源释放另等finished控制确认。|
|`facts`|dict|是|无|本文件截至本包的累计事实，比面积包多frame_identity。|

源码：[`src/chronaxis/execution/integral_blocks.py:465`](../../../src/chronaxis/execution/integral_blocks.py#L465)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-point_cost"></a>
## `point_cost`

按固定字段估算一个组点事件的保守编码与展开字节数，不遍历值内容。

```python
point_cost(event)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`event`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary) &#124; [DeferredPointError](chronaxis.execution.file_group_points.md#api-DeferredPointError)|是|无|位置或关键字。待编码的一个组点或延迟错误事件。|

### 返回说明

tuple[int, int]，依次为保守编码字节数及模型展开字节数，不含整包事实。

### 异常说明

未知事件时IntegralBlockError；延迟错误原文不能编码为UTF-8时UnicodeEncodeError。
编码上界：时间等整数最多18字节，单个数值最多39字节；展开上界与decode_points的charge一致。

源码：[`src/chronaxis/execution/integral_blocks.py:474`](../../../src/chronaxis/execution/integral_blocks.py#L474)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-point_facts_cost"></a>
## `point_facts_cost`

估算组点包事实的传输和展开字节数；两种包事实相同，直接沿用facts_cost。

```python
point_facts_cost(facts, cache)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`facts`|dict|是|无|位置或关键字。含frame_identity的文件事实。|
|`cache`|dict[int, tuple[int, int]]|是|无|位置或关键字。本批兼容字段费用缓存，按兼容字段tuple的对象身份复用。|

### 返回说明

tuple[int, int]，与facts_cost相同。

### 异常说明

缺字段时KeyError；原时间类型或UTF-8编码错误继续传播。

源码：[`src/chronaxis/execution/integral_blocks.py:495`](../../../src/chronaxis/execution/integral_blocks.py#L495)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_write_facts"></a>
## `_write_facts`

写文件事实：面积包在事件之后，组点包在事件之前。

```python
_write_facts(writer, facts)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`writer`|[_Writer](chronaxis.execution.integral_blocks.md#api-_Writer)|是|无|位置或关键字。当前包的编码器。|
|`facts`|dict|是|无|位置或关键字。字段与_FACTS相同的文件事实，含frame_identity。|

### 返回说明

None。

### 异常说明

字段集合不符时ValueError；帧型结构非法或超长时IntegralBlockError。

源码：[`src/chronaxis/execution/integral_blocks.py:505`](../../../src/chronaxis/execution/integral_blocks.py#L505)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_read_facts"></a>
## `_read_facts`

恢复文件事实。

```python
_read_facts(reader)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|[_Reader](chronaxis.execution.integral_blocks.md#api-_Reader)|是|无|位置或关键字。游标已到文件事实位置的解码器（面积包在事件之后，组点包在EOF之后）。|

### 返回说明

dict，字段同_POINT_FACTS。

### 异常说明

计数非法、截断或展开超限时IntegralBlockError；非法UTF-8继续传播。

源码：[`src/chronaxis/execution/integral_blocks.py:523`](../../../src/chronaxis/execution/integral_blocks.py#L523)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_check_point_time"></a>
## `_check_point_time`

核组点时间。

```python
_check_point_time(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; None|是|无|位置或关键字。已解码或待编码的组点时间。|

### 返回说明

None。

### 异常说明

不是int64整数时IntegralBlockError。

源码：[`src/chronaxis/execution/integral_blocks.py:540`](../../../src/chronaxis/execution/integral_blocks.py#L540)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-_check_point_group"></a>
## `_check_point_group`

编码前核组点使用组内位置的约定。

```python
_check_point_group(group)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`group`|[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary)|是|无|位置或关键字。待编码的组点，按组内位置约定填写。|

### 返回说明

None。

### 异常说明

时间、帧数、组内位置或冲突位置不合约定时IntegralBlockError。
约定：first_sequence为0，last_sequence为帧数减1，冲突位置是组内第几帧（1至帧数减1）；
不传来源原序号，主进程按文件位置另加偏移（A2-2）。

源码：[`src/chronaxis/execution/integral_blocks.py:545`](../../../src/chronaxis/execution/integral_blocks.py#L545)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-encode_points"></a>
## `encode_points`

编码一个组点块，事实在事件之前，数值位型不变。

```python
encode_points(file_index, number, events, eof, facts)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`file_index`|int|是|无|位置或关键字。原来源声明中的零起文件序号。|
|`number`|int|是|无|位置或关键字。本文件从0递增的块号。|
|`events`|tuple[[SameTimeGroupSummary](chronaxis.execution.file_integral_terms.md#api-SameTimeGroupSummary) &#124; [DeferredPointError](chronaxis.execution.file_group_points.md#api-DeferredPointError), ...]|是|无|位置或关键字。按文件内时间顺序的组点与延迟错误，最多MAX_POINTS个。|
|`eof`|bool|是|无|位置或关键字。本包是否为本文件的数据终点。|
|`facts`|dict|是|无|位置或关键字。本文件截至本包的累计事实，含frame_identity。|

### 返回说明

bytes，含包头最多512KiB，标志P5G1。

### 异常说明

事件过多、未知事件、组点约定不符、错误类型不在DEFERRED_KINDS、原文超过256KiB或包超限时
    IntegralBlockError；事实字段不符时ValueError；编码原错误继续传播。

源码：[`src/chronaxis/execution/integral_blocks.py:567`](../../../src/chronaxis/execution/integral_blocks.py#L567)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-decode_points_prefix"></a>
## `decode_points_prefix`

收包时只核包头并读到文件事实为止，不解码事件。

```python
decode_points_prefix(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|bytes|是|无|位置或关键字。收到的完整P5G1包；只读到文件事实为止。|

### 返回说明

tuple，依次为文件序号int、块号int、eof bool和facts dict。

### 异常说明

标志、长度、编号或事实非法时IntegralBlockError；非法UTF-8继续传播。
事件部分的合法性留到decode_points在归并读回时检查，本函数不代替它。

源码：[`src/chronaxis/execution/integral_blocks.py:606`](../../../src/chronaxis/execution/integral_blocks.py#L606)（行号对应 Chronaxis 0.1.0 源码）。

<a id="api-decode_points"></a>
## `decode_points`

完整恢复一个组点块，并核完整消费与有界模型。

```python
decode_points(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|bytes|是|无|位置或关键字。从暂存读回的完整P5G1包。|

### 返回说明

PointPacket，事件按原顺序；组点的组内位置按A2-2约定恢复。

### 异常说明

截断、非法计数/事件/位置、未知错误类型或展开超过4MiB时IntegralBlockError；
    非法UTF-8及数值模型构造错误继续传播。只重建列出的模型，不加载任意类。

源码：[`src/chronaxis/execution/integral_blocks.py:619`](../../../src/chronaxis/execution/integral_blocks.py#L619)（行号对应 Chronaxis 0.1.0 源码）。
