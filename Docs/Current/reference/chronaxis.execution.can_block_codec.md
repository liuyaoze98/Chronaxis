# `chronaxis.execution.can_block_codec`

普通 CAN 有界数据块；只恢复固定记录，绝不加载任意 Python 对象。

CND1 头为 4 字节版本和网络序 uint32 主体长度。主体先存字符串表，再按
固定字段依次存块、来源和原帧。字符串只在本块共享；原数值保留位型和整数精度。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DecodedCANRecord](chronaxis.sources.text_can_decode.md#api-DecodedCANRecord)、[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`CANBlockError`](#api-CANBlockError)|固定 CAN 编码结构不完整或不合法。|
|[`_Writer`](#api-_Writer)|单块临时编码空间；所有增长先核原有包长上限。|
|[`_Writer.__init__`](#api-_Writer-__init__)|建立单块临时空间。|
|[`_Writer.add`](#api-_Writer-add)|追加已编码字节并先核包长。|
|[`_Writer.byte`](#api-_Writer-byte)|写一个uint8。|
|[`_Writer.uint`](#api-_Writer-uint)|写网络序uint32。|
|[`_Writer.text`](#api-_Writer-text)|写本块字符串表索引。|
|[`_Writer.scalar`](#api-_Writer-scalar)|无损写有限种类原值。|
|[`_Writer.optional_text`](#api-_Writer-optional_text)|写可空文本。|
|[`_Writer.pairs`](#api-_Writer-pairs)|写字段值对。|
|[`_Writer.decimal`](#api-_Writer-decimal)|写精确比较时间事实。|
|[`_Writer.finish`](#api-_Writer-finish)|拼接单一头、字符串表和主体。|
|[`_Reader`](#api-_Reader)|只按固定顺序取字段；长度检查在切片或容器分配之前执行。|
|[`_Reader.__init__`](#api-_Reader-__init__)|核固定头并读取本块字符串表。|
|[`_Reader.close`](#api-_Reader-close)|清除仅属解码器的视图与字符串表引用。|
|[`_Reader.charge`](#api-_Reader-charge)|累计本块模型展开上界。|
|[`_Reader.remaining`](#api-_Reader-remaining)|取得未消费字节数。|
|[`_Reader.take`](#api-_Reader-take)|取得有界字节视图并移动游标。|
|[`_Reader.byte`](#api-_Reader-byte)|读一个uint8。|
|[`_Reader.uint`](#api-_Reader-uint)|读网络序uint32。|
|[`_Reader.boolean`](#api-_Reader-boolean)|读严格布尔位。|
|[`_Reader.text`](#api-_Reader-text)|取本块已有字符串。|
|[`_Reader.scalar`](#api-_Reader-scalar)|读固定种类数值。|
|[`_Reader.nonnegative`](#api-_Reader-nonnegative)|读原生非负序号。|
|[`_Reader.optional_text`](#api-_Reader-optional_text)|读可空文本。|
|[`_Reader.pairs`](#api-_Reader-pairs)|读有限字段对。|
|[`_Reader.decimal`](#api-_Reader-decimal)|读精确比较时间事实。|
|[`_write_frame`](#api-_write_frame)|写原帧固定公开字段。|
|[`_read_frame`](#api-_read_frame)|恢复已知原帧类型。|
|[`encode_block`](#api-encode_block)|编码一个已校验CAN块。|
|[`decode_block`](#api-decode_block)|恢复一个固定CAN块；失败只保留原诊断，不保留已经解码的整批记录。|
|[`_metadata`](#api-_metadata)|核当前CAN读取器字段事实。|
|[`encode_metadata`](#api-encode_metadata)|编码READY事实，并复用单块字符串表避免宽字段的重复JSON键膨胀。|
|[`decode_metadata`](#api-decode_metadata)|恢复固定READY事实；只按明确字段解释CMT1，不支持旧pickle。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from decimal import Decimal
from pathlib import Path
```

</details>

<a id="api-CANBlockError"></a>
## `CANBlockError`

固定 CAN 编码结构不完整或不合法。

```python
class CANBlockError(ValueError)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/can_block_codec.py:21`](../../../src/chronaxis/execution/can_block_codec.py#L21)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer"></a>
## `_Writer`

单块临时编码空间；所有增长先核原有包长上限。

```python
_Writer()
```


源码：[`src/chronaxis/execution/can_block_codec.py:25`](../../../src/chronaxis/execution/can_block_codec.py#L25)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-__init__"></a>
### `_Writer.__init__`

建立单块临时空间。

```python
_Writer.__init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

新编码器。

#### 异常说明

内存分配错误。

源码：[`src/chronaxis/execution/can_block_codec.py:28`](../../../src/chronaxis/execution/can_block_codec.py#L28)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-add"></a>
### `_Writer.add`

追加已编码字节并先核包长。

```python
_Writer.add(data)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|bytes &#124; bytearray &#124; memoryview|是|无|位置或关键字。已编码的连续字节片段；增长前核整个包不得超过512KiB。|

#### 返回说明

None。

#### 异常说明

超过512KiB时CANBlockError。

源码：[`src/chronaxis/execution/can_block_codec.py:40`](../../../src/chronaxis/execution/can_block_codec.py#L40)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-byte"></a>
### `_Writer.byte`

写一个uint8。

```python
_Writer.byte(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。0到255的无符号字节值，不用于传递任意原始整数。|

#### 返回说明

None。

#### 异常说明

范围或包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:51`](../../../src/chronaxis/execution/can_block_codec.py#L51)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-uint"></a>
### `_Writer.uint`

写网络序uint32。

```python
_Writer.uint(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。0到2**32-1的无符号整数，以网络序固定4字节写入。|

#### 返回说明

None。

#### 异常说明

范围或包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:60`](../../../src/chronaxis/execution/can_block_codec.py#L60)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-text"></a>
### `_Writer.text`

写本块字符串表索引。

```python
_Writer.text(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。本块要共享的文本；首次出现编码为UTF-8/surrogatepass，随后只写字符串表索引。|

#### 返回说明

None，首次出现时登记UTF8/surrogatepass内容。

#### 异常说明

类型或包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:69`](../../../src/chronaxis/execution/can_block_codec.py#L69)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-scalar"></a>
### `_Writer.scalar`

无损写有限种类原值。

```python
_Writer.scalar(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|None &#124; bool &#124; int &#124; float|是|无|位置或关键字。固定原生值；bool独立编码，大整数保留精度，float保留位型及NaN/Inf。|

#### 返回说明

None。

#### 异常说明

未支持类型或包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:89`](../../../src/chronaxis/execution/can_block_codec.py#L89)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-optional_text"></a>
### `_Writer.optional_text`

写可空文本。

```python
_Writer.optional_text(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str &#124; None|是|无|位置或关键字。可空文本；先写是否存在标记，非空时再写字符串表索引。|

#### 返回说明

None。

#### 异常说明

类型或包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:115`](../../../src/chronaxis/execution/can_block_codec.py#L115)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-pairs"></a>
### `_Writer.pairs`

写字段值对。

```python
_Writer.pairs(values)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|Sequence[tuple[str, int &#124; float &#124; bool &#124; None]]|是|无|位置或关键字。已经校验的名称和值对序列；逐项写名称索引和无损原生数值。|

#### 返回说明

None。

#### 异常说明

字段类型或包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:126`](../../../src/chronaxis/execution/can_block_codec.py#L126)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-decimal"></a>
### `_Writer.decimal`

写精确比较时间事实。

```python
_Writer.decimal(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|Decimal &#124; None|是|无|位置或关键字。有限精确时间或None；按符号、数字和指数编码，不先展开成巨型小数文本。|

#### 返回说明

None，不按指数展开文本。

#### 异常说明

类型、非有限值或包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:138`](../../../src/chronaxis/execution/can_block_codec.py#L138)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Writer-finish"></a>
### `_Writer.finish`

拼接单一头、字符串表和主体。

```python
_Writer.finish(magic=b'CND1')
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`magic`|bytes|否|b'CND1'|位置或关键字。magic为内部写定的CND1或CMT1版本。|

#### 返回说明

对应固定格式的完整bytes。

#### 异常说明

超过512KiB时CANBlockError。

源码：[`src/chronaxis/execution/can_block_codec.py:155`](../../../src/chronaxis/execution/can_block_codec.py#L155)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader"></a>
## `_Reader`

只按固定顺序取字段；长度检查在切片或容器分配之前执行。

```python
_Reader(packet, expected=b'CND1', *, on_expand=None)
```


源码：[`src/chronaxis/execution/can_block_codec.py:175`](../../../src/chronaxis/execution/can_block_codec.py#L175)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-__init__"></a>
### `_Reader.__init__`

核固定头并读取本块字符串表。

```python
_Reader.__init__(packet, expected=b'CND1', *, on_expand=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|bytes|是|无|位置或关键字。完整CND1或CMT1包，长度12字节到512KiB；固定头长度必须与实际包一致。|
|`expected`|bytes|否|b'CND1'|位置或关键字。本入口允许的固定版本，默认b'CND1'；元数据读取显式传b'CMT1'，不得从包中任意选择构造器。|
|`on_expand`|Callable[[int], None] &#124; None|否|None|仅关键字。可选的父端预约回调；收到本块累计展开估算，须在新增模型分配前允许或抛错。|

#### 返回说明

新读取器，拥有游标及局部展开计数。

#### 异常说明

版本、长度、编码或展开上限错误。

源码：[`src/chronaxis/execution/can_block_codec.py:178`](../../../src/chronaxis/execution/can_block_codec.py#L178)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-close"></a>
### `_Reader.close`

清除仅属解码器的视图与字符串表引用。

```python
_Reader.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；返回模型继续持有其实际使用的不可变文本。

#### 异常说明

无，重复调用无副作用。

源码：[`src/chronaxis/execution/can_block_codec.py:218`](../../../src/chronaxis/execution/can_block_codec.py#L218)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-charge"></a>
### `_Reader.charge`

累计本块模型展开上界。

```python
_Reader.charge(amount)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`amount`|int|是|无|位置或关键字。本次新增模型的保守字节量；累计到固定展开上限，并将累计值交on_expand预付检查。|

#### 返回说明

None，不改变ResourceBudget账本。

#### 异常说明

超过本固定图边界时CANBlockError；父预约不足或取消原样传播。

源码：[`src/chronaxis/execution/can_block_codec.py:230`](../../../src/chronaxis/execution/can_block_codec.py#L230)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-remaining"></a>
### `_Reader.remaining`

取得未消费字节数。

```python
_Reader.remaining
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

非负int。

#### 异常说明

无。

源码：[`src/chronaxis/execution/can_block_codec.py:245`](../../../src/chronaxis/execution/can_block_codec.py#L245)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-take"></a>
### `_Reader.take`

取得有界字节视图并移动游标。

```python
_Reader.take(size)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`size`|int|是|无|位置或关键字。要消费的非负字节数；先核剩余长度，再返回memoryview并推进游标。|

#### 返回说明

memoryview，不复制包主体。

#### 异常说明

长度越界或截断时CANBlockError。

源码：[`src/chronaxis/execution/can_block_codec.py:254`](../../../src/chronaxis/execution/can_block_codec.py#L254)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-byte"></a>
### `_Reader.byte`

读一个uint8。

```python
_Reader.byte()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

截断时CANBlockError。

源码：[`src/chronaxis/execution/can_block_codec.py:267`](../../../src/chronaxis/execution/can_block_codec.py#L267)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-uint"></a>
### `_Reader.uint`

读网络序uint32。

```python
_Reader.uint()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

截断时CANBlockError。

源码：[`src/chronaxis/execution/can_block_codec.py:281`](../../../src/chronaxis/execution/can_block_codec.py#L281)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-boolean"></a>
### `_Reader.boolean`

读严格布尔位。

```python
_Reader.boolean()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

非0/1或截断时CANBlockError。

源码：[`src/chronaxis/execution/can_block_codec.py:295`](../../../src/chronaxis/execution/can_block_codec.py#L295)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-text"></a>
### `_Reader.text`

取本块已有字符串。

```python
_Reader.text()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

str，不复制共享文本。

#### 异常说明

索引越界或截断时CANBlockError。

源码：[`src/chronaxis/execution/can_block_codec.py:307`](../../../src/chronaxis/execution/can_block_codec.py#L307)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-scalar"></a>
### `_Reader.scalar`

读固定种类数值。

```python
_Reader.scalar()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None/bool/int/float，保留原位型。

#### 异常说明

未知标记、非最短整数、展开或截断错误。

源码：[`src/chronaxis/execution/can_block_codec.py:319`](../../../src/chronaxis/execution/can_block_codec.py#L319)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-nonnegative"></a>
### `_Reader.nonnegative`

读原生非负序号。

```python
_Reader.nonnegative()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

负数、bool、其他类型或截断错误。

源码：[`src/chronaxis/execution/can_block_codec.py:353`](../../../src/chronaxis/execution/can_block_codec.py#L353)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-optional_text"></a>
### `_Reader.optional_text`

读可空文本。

```python
_Reader.optional_text()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

str或None。

#### 异常说明

存在位、索引或截断错误。

源码：[`src/chronaxis/execution/can_block_codec.py:365`](../../../src/chronaxis/execution/can_block_codec.py#L365)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-pairs"></a>
### `_Reader.pairs`

读有限字段对。

```python
_Reader.pairs(*, maximum=4096)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`maximum`|int|否|4096|仅关键字。maximum为条数上限，默认4096。|

#### 返回说明

tuple名称值对。

#### 异常说明

计数、展开、标记或截断错误。

源码：[`src/chronaxis/execution/can_block_codec.py:374`](../../../src/chronaxis/execution/can_block_codec.py#L374)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Reader-decimal"></a>
### `_Reader.decimal`

读精确比较时间事实。

```python
_Reader.decimal()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

有限Decimal或None。

#### 异常说明

符号、数字、指数、展开或截断错误。

源码：[`src/chronaxis/execution/can_block_codec.py:387`](../../../src/chronaxis/execution/can_block_codec.py#L387)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_write_frame"></a>
## `_write_frame`

写原帧固定公开字段。

```python
_write_frame(writer, frame)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`writer`|[_Writer](chronaxis.execution.can_block_codec.md#api-_Writer)|是|无|位置或关键字。当前块的编码器；所有写入使用其同一包长限制和字符串表。|
|`frame`|[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame) &#124; can.Message|是|无|位置或关键字。已由读取路径建立的原帧；按固定字段保留timestamp、ID、帧标志、通道、DLC和载荷。|

### 返回说明

None。

### 异常说明

字段或包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:419`](../../../src/chronaxis/execution/can_block_codec.py#L419)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_read_frame"></a>
## `_read_frame`

恢复已知原帧类型。

```python
_read_frame(reader, timed)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`reader`|[_Reader](chronaxis.execution.can_block_codec.md#api-_Reader)|是|无|位置或关键字。当前块的有界读取器，按固定顺序消费原帧字段。|
|`timed`|bool|是|无|位置或关键字。True恢复LegacyRawFrame并沿用其检查；False恢复已知can.Message，不添加无需求的时间有限性检查。|

### 返回说明

LegacyRawFrame或已知can.Message。

### 异常说明

固定字段或原模型校验错误，无时间模式不增加时间有限性检查。

源码：[`src/chronaxis/execution/can_block_codec.py:440`](../../../src/chronaxis/execution/can_block_codec.py#L440)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-encode_block"></a>
## `encode_block`

编码一个已校验CAN块。

```python
encode_block(number, records, eof, facts)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`number`|int|是|无|位置或关键字。非负数据块序号；由同一文件的发送顺序产生，不是报文ID。|
|`records`|Sequence[[DecodedCANRecord](chronaxis.sources.text_can_decode.md#api-DecodedCANRecord)]|是|无|位置或关键字。本块已经检查的记录，最多64条；原始位置、状态、值和原帧均按固定字段编码。|
|`eof`|bool|是|无|位置或关键字。True表示该文件真实读取结束；不是把当前块用完当作整个来源EOF。|
|`facts`|dict[str, int &#124; Decimal &#124; None]|是|无|位置或关键字。恰含count、first_ns、last_ns、decode_calls、first_order_time、last_order_time六项文件事实；前四项为整数/可空时间，后两项为可空Decimal。|

### 返回说明

CND1 bytes。

### 异常说明

数量、字段或原512KiB包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:470`](../../../src/chronaxis/execution/can_block_codec.py#L470)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-decode_block"></a>
## `decode_block`

恢复一个固定CAN块；失败只保留原诊断，不保留已经解码的整批记录。

```python
decode_block(packet)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|bytes|是|无|位置或关键字。完整CND1包；恢复固定记录列表并核计数、状态、字段键、展开限额、截断和尾随数据。|

### 返回说明

块号、records列表、EOF和facts字典；成功时记录所有权交给调用方。

### 异常说明

结构、模型、展开、截断或尾随字节错误；保留原异常与原因链。

源码：[`src/chronaxis/execution/can_block_codec.py:516`](../../../src/chronaxis/execution/can_block_codec.py#L516)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_metadata"></a>
## `_metadata`

核当前CAN读取器字段事实。

```python
_metadata(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, Any]|是|无|位置或关键字。CAN读取器的固定元数据对象，字段集合须等于_METADATA_KEYS，fields至多4096项；只核当前政策，不加载DBC。|

### 返回说明

原生dict。

### 异常说明

缺项、未知字段或类型不符。

源码：[`src/chronaxis/execution/can_block_codec.py:595`](../../../src/chronaxis/execution/can_block_codec.py#L595)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-encode_metadata"></a>
## `encode_metadata`

编码READY事实，并复用单块字符串表避免宽字段的重复JSON键膨胀。

```python
encode_metadata(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, Any]|是|无|位置或关键字。通过_metadata约束的READY事实；按固定字段写为CMT1包，文本只在该包共享。|

### 返回说明

CMT1 bytes，仍受原512KiB上限。

### 异常说明

字段、类型或包长错误。

源码：[`src/chronaxis/execution/can_block_codec.py:646`](../../../src/chronaxis/execution/can_block_codec.py#L646)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-decode_metadata"></a>
## `decode_metadata`

恢复固定READY事实；只按明确字段解释CMT1，不支持旧pickle。

```python
decode_metadata(packet, *, on_expand=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`packet`|bytes|是|无|位置或关键字。完整CMT1元数据包；按明确字段恢复原生字典，不接受pickle或任意类型名称。|
|`on_expand`|Callable[[int], None] &#124; None|否|None|仅关键字。可选父端额度回调，参数为累计模型展开估算；父端在实际新增分配前预约，失败原样传播。|

### 返回说明

固定元数据dict，随后由既有模型冻结。

### 异常说明

版本、字段、包长、索引、展开或截断错误。

源码：[`src/chronaxis/execution/can_block_codec.py:684`](../../../src/chronaxis/execution/can_block_codec.py#L684)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
