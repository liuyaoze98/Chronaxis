# `chronaxis._control_wire`

内部有限控制消息；Connection 只收发 bytes，不使用隐含 pickle。

CCP1 的固定头为版本、通道、命令和 uint64 总字节数，主体分片不超过 64KiB。
普通CAN/fast由已有工作预算限定；独立batch沿用无全批RAM硬上限的边界。
任务与固定结果逐片接收，不按声明总长预分配，也不截断合法身份。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`ControlProtocolError`](#api-ControlProtocolError)|内部协议版本、长度、命令或固定字段错误。|
|[`_pairs`](#api-_pairs)|建立不重复的JSON对象。|
|[`_depth`](#api-_depth)|在解析前核JSON容器深度。|
|[`encode_json`](#api-encode_json)|逐片编码有限JSON结构。|
|[`decode_json`](#api-decode_json)|解码有限JSON为原生值。|
|[`decode_json.constant`](#api-decode_json-constant)|拒绝JSON宽松常量。|
|[`_integer`](#api-_integer)|判断原生整数下界。|
|[`_time`](#api-_time)|判断有限非负计时。|
|[`_check`](#api-_check)|核控制命令基础形状。|
|[`_short`](#api-_short)|按JSON转义后的字节数截短诊断。|
|[`_diagnostics`](#api-_diagnostics)|限制仅供展示的错误信息。|
|[`ControlChannel`](#api-ControlChannel)|单个管道端的有限控制编码；不拥有额外句柄，close关闭实际Connection。|
|[`ControlChannel.__init__`](#api-ControlChannel-__init__)|绑定一个已有控制端点。|
|[`ControlChannel._limit`](#api-ControlChannel-_limit)|取得当前消息可用额度。|
|[`ControlChannel._direction`](#api-ControlChannel-_direction)|核发送者是否有权发此命令。|
|[`ControlChannel.send`](#api-ControlChannel-send)|发送一条固定命令。|
|[`ControlChannel.recv`](#api-ControlChannel-recv)|接收一条固定消息。|
|[`ControlChannel.__enter__`](#api-ControlChannel-__enter__)|保持原管道上下文用法。|
|[`ControlChannel.__exit__`](#api-ControlChannel-__exit__)|按原管道上下文关闭。|
|[`ControlChannel.poll`](#api-ControlChannel-poll)|查询实际管道是否可读。|
|[`ControlChannel.fileno`](#api-ControlChannel-fileno)|返回同一实际管道句柄。|
|[`ControlChannel.closed`](#api-ControlChannel-closed)|报告实际管道关闭状态。|
|[`ControlChannel.close`](#api-ControlChannel-close)|关闭本端实际管道。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from ._control_models import pack_message, restore_message, native, check_message_fields
```

</details>

<a id="api-ControlProtocolError"></a>
## `ControlProtocolError`

内部协议版本、长度、命令或固定字段错误。

```python
class ControlProtocolError(ValueError)
```

继承关系：ValueError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/_control_wire.py:29`](../../../src/chronaxis/_control_wire.py#L29)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_pairs"></a>
## `_pairs`

建立不重复的JSON对象。

```python
_pairs(items)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`items`|list[tuple[str, Any]]|是|无|位置或关键字。json解析器交出的有序键值对；建立dict前拒绝重复键，不允许后值悄悄覆盖前值。|

### 返回说明

dict。

### 异常说明

重复键时ControlProtocolError。

源码：[`src/chronaxis/_control_wire.py:33`](../../../src/chronaxis/_control_wire.py#L33)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_depth"></a>
## `_depth`

在解析前核JSON容器深度。

```python
_depth(data)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|bytes &#124; bytearray|是|无|位置或关键字。已按接收额度限制长度的JSON字节；仅检查字符串之外的容器层数和闭合情况。|

### 返回说明

None，忽略字符串内的括号。

### 异常说明

超过320层或结构未闭合时ControlProtocolError。

源码：[`src/chronaxis/_control_wire.py:48`](../../../src/chronaxis/_control_wire.py#L48)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-encode_json"></a>
## `encode_json`

逐片编码有限JSON结构。

```python
encode_json(value, maximum)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|None &#124; bool &#124; int &#124; float &#124; str &#124; list &#124; dict[str, Any]|是|无|位置或关键字。已检查的原生JSON树；逐片编码，拒绝非有限数，不允许任意Python对象。|
|`maximum`|int &#124; None|是|无|位置或关键字。本次JSON主体字节上限；CAN/fast取现有预算，batch固定大消息可为None，不表示零字节。|

### 返回说明

bytearray。

### 异常说明

JSON类型、非有限数或超过额度。

源码：[`src/chronaxis/_control_wire.py:79`](../../../src/chronaxis/_control_wire.py#L79)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-decode_json"></a>
## `decode_json`

解码有限JSON为原生值。

```python
decode_json(data)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|bytes &#124; bytearray|是|无|位置或关键字。已完整接收且受当前通道限制的JSON主体；解析前核深度，随后拒绝重复键及非有限数。|

### 返回说明

dict/list/原生标量。

### 异常说明

重复键、非有限数、语法或深度错误。

源码：[`src/chronaxis/_control_wire.py:96`](../../../src/chronaxis/_control_wire.py#L96)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-decode_json-constant"></a>
### `decode_json.constant`

拒绝JSON宽松常量。

```python
decode_json.constant(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。json解析器发现的NaN、Infinity或-Infinity标记；此回调始终拒绝。|

#### 返回说明

无，始终抛错。

#### 异常说明

ControlProtocolError。

源码：[`src/chronaxis/_control_wire.py:104`](../../../src/chronaxis/_control_wire.py#L104)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_integer"></a>
## `_integer`

判断原生整数下界。

```python
_integer(value, minimum=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|Any|是|无|位置或关键字。待判断的候选值；只有原生int且不小于minimum时为True，bool不算int。|
|`minimum`|int|否|0|位置或关键字。允许的最小整数，默认0；调用点需要正整数时传1。|

### 返回说明

bool，不把bool当整数。

### 异常说明

无。

源码：[`src/chronaxis/_control_wire.py:120`](../../../src/chronaxis/_control_wire.py#L120)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_time"></a>
## `_time`

判断有限非负计时。

```python
_time(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|Any|是|无|位置或关键字。待判断的秒数；只有有限、非负的原生int或float返回True，bool及其他类型返回False。|

### 返回说明

bool。

### 异常说明

无。

源码：[`src/chronaxis/_control_wire.py:130`](../../../src/chronaxis/_control_wire.py#L130)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_check"></a>
## `_check`

核控制命令基础形状。

```python
_check(family, command, args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`family`|str|是|无|位置或关键字。can、fast或batch之一，决定命令的基础参数形状。|
|`command`|str|是|无|位置或关键字。本族已登记的命令名，需与消息头一致。|
|`args`|tuple[Any, ...] &#124; list[Any]|是|无|位置或关键字。不含命令名的参数序列；数量、计数和基础类型不符时拒绝。|

### 返回说明

None。

### 异常说明

数量或字段基本类型不符时ControlProtocolError。

源码：[`src/chronaxis/_control_wire.py:140`](../../../src/chronaxis/_control_wire.py#L140)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_short"></a>
## `_short`

按JSON转义后的字节数截短诊断。

```python
_short(value, maximum)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。待展示的错误文本；只访问有限前缀，截短时添加明确标记，不用于任务身份或数值。|
|`maximum`|int|是|无|位置或关键字。该诊断字段允许的JSON转义后字节上限；不是原始字符数上限。|

### 返回说明

短文本，发生截断时明确注明。

### 异常说明

输入不是文本时类型错误。

源码：[`src/chronaxis/_control_wire.py:176`](../../../src/chronaxis/_control_wire.py#L176)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_diagnostics"></a>
## `_diagnostics`

限制仅供展示的错误信息。

```python
_diagnostics(family, command, args)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`family`|str|是|无|位置或关键字。控制通道族；batch结果与其他error消息采用相应诊断字段规则。|
|`command`|str|是|无|位置或关键字。已选命令名，决定是否处理错误类型、消息或错误链。|
|`args`|list[Any]|是|无|位置或关键字。已展开的参数列表；仅裁短供展示的诊断，batch结果字典先复制，计算值及身份不截短。|

### 返回说明

参数列表，只修改独立结果字典中的诊断。

### 异常说明

诊断字段类型非法。

源码：[`src/chronaxis/_control_wire.py:194`](../../../src/chronaxis/_control_wire.py#L194)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel"></a>
## `ControlChannel`

单个管道端的有限控制编码；不拥有额外句柄，close关闭实际Connection。

parent表示父端，仅接受向worker派发已定义命令；worker只能回报已定义事实。
max_bytes是CAN/fast已有预算。独立batch任务及固定结果总长没有原有硬上限；
每片仍至多64KiB，只随实际收到内容增长，不能把分片长度当作总RAM上限。

```python
ControlChannel(connection, family, *, parent, max_bytes=None)
```


源码：[`src/chronaxis/_control_wire.py:214`](../../../src/chronaxis/_control_wire.py#L214)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-__init__"></a>
### `ControlChannel.__init__`

绑定一个已有控制端点。

```python
ControlChannel.__init__(connection, family, *, parent, max_bytes=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`connection`|multiprocessing.connection.Connection|是|无|位置或关键字。已有控制管道端点；本包装不新建句柄，关闭时关闭这个实际Connection。|
|`family`|str|是|无|位置或关键字。本连接的固定族：can、fast或batch；两端必须一致。|
|`parent`|bool|是|无|仅关键字。True表示调度父端，False表示工作端；据此限制发送和接收命令方向。|
|`max_bytes`|int &#124; None|否|None|仅关键字。CAN/fast固定大消息可用的正数字节额度；batch大任务/结果允许None，分片64KiB不是总RAM限制。|

#### 返回说明

新编码端点，不新增句柄。

#### 异常说明

通道、方向或额度错误。

源码：[`src/chronaxis/_control_wire.py:221`](../../../src/chronaxis/_control_wire.py#L221)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-_limit"></a>
### `ControlChannel._limit`

取得当前消息可用额度。

```python
ControlChannel._limit(operation, *, sending)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。当前已登记命令；小消息至多CHUNK，大消息根据通道采用现有额度。|
|`sending`|bool|是|无|仅关键字。调用方标明正在发送还是接收；当前额度规则两方向相同，不改变资源预算。|

#### 返回说明

字节上限。

#### 异常说明

batch固定大消息沿用None；CAN/fast未提供预算时ControlProtocolError。

源码：[`src/chronaxis/_control_wire.py:236`](../../../src/chronaxis/_control_wire.py#L236)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-_direction"></a>
### `ControlChannel._direction`

核发送者是否有权发此命令。

```python
ControlChannel._direction(operation, *, sending)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。需校验方向的命令名；父端派发与工作端回报集合互斥。|
|`sending`|bool|是|无|仅关键字。True核本端发送方向，False核对端发送方向；结合parent确定实际发送者。|

#### 返回说明

None。

#### 异常说明

父子方向不符时ControlProtocolError。

源码：[`src/chronaxis/_control_wire.py:253`](../../../src/chronaxis/_control_wire.py#L253)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-send"></a>
### `ControlChannel.send`

发送一条固定命令。

```python
ControlChannel.send(message)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`message`|tuple[Any, ...] &#124; list[Any]|是|无|位置或关键字。非空固定命令序列，首项为命令名，其余为参数；未知命令、方向、字段或超额内容拒绝发送。|

#### 返回说明

None，返回前释放编码副本。

#### 异常说明

字段、额度或实际管道写入错误。

源码：[`src/chronaxis/_control_wire.py:264`](../../../src/chronaxis/_control_wire.py#L264)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-recv"></a>
### `ControlChannel.recv`

接收一条固定消息。

```python
ControlChannel.recv()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

现有消费者使用的tuple。

#### 异常说明

版本、长度、字段、截断或管道错误。

源码：[`src/chronaxis/_control_wire.py:298`](../../../src/chronaxis/_control_wire.py#L298)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-__enter__"></a>
### `ControlChannel.__enter__`

保持原管道上下文用法。

```python
ControlChannel.__enter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

当前编码端点。

#### 异常说明

无。

源码：[`src/chronaxis/_control_wire.py:336`](../../../src/chronaxis/_control_wire.py#L336)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-__exit__"></a>
### `ControlChannel.__exit__`

按原管道上下文关闭。

```python
ControlChannel.__exit__(*args)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`args`|tuple|否|()|可变位置。args为上下文异常三元组。|

#### 返回说明

原Connection.__exit__返回值。

#### 异常说明

真实关闭错误。

源码：[`src/chronaxis/_control_wire.py:345`](../../../src/chronaxis/_control_wire.py#L345)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-poll"></a>
### `ControlChannel.poll`

查询实际管道是否可读。

```python
ControlChannel.poll(*args)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`args`|tuple|否|()|可变位置。args沿用Connection.poll的等待参数。|

#### 返回说明

bool。

#### 异常说明

真实管道错误。

源码：[`src/chronaxis/_control_wire.py:354`](../../../src/chronaxis/_control_wire.py#L354)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-fileno"></a>
### `ControlChannel.fileno`

返回同一实际管道句柄。

```python
ControlChannel.fileno()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

int，供multiprocessing.wait使用。

#### 异常说明

已关闭等底层句柄错误。

源码：[`src/chronaxis/_control_wire.py:363`](../../../src/chronaxis/_control_wire.py#L363)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-closed"></a>
### `ControlChannel.closed`

报告实际管道关闭状态。

```python
ControlChannel.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/_control_wire.py:373`](../../../src/chronaxis/_control_wire.py#L373)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ControlChannel-close"></a>
### `ControlChannel.close`

关闭本端实际管道。

```python
ControlChannel.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

真实关闭错误。

源码：[`src/chronaxis/_control_wire.py:382`](../../../src/chronaxis/_control_wire.py#L382)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
