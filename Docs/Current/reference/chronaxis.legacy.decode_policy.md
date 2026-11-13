# `chronaxis.legacy.decode_policy`

原始报文的长度检查与显式纯BLF串行解码政策。

只对所需数据帧核所选长度规则。串行兼容函数保留唯一ID和多定义ID的既有异常
范围；普通并行和文本入口不自动使用这一兼容规则。返回空值时不继承前值。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`validate_decode_policy`](#api-validate_decode_policy)|核验长度政策。|
|[`check_decode_length`](#api-check_decode_length)|解码前检查所需帧长度，不复制载荷或检查无关报文。|
|[`decode_serial_frame`](#api-decode_serial_frame)|保留纯BLF串行的既有解码政策，不重复检查报文长度或缩放物理值。|

<a id="api-validate_decode_policy"></a>
## `validate_decode_policy`

核验长度政策。

```python
validate_decode_policy(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str|是|无|位置或关键字。待检查的解码政策，只接受strict、partial、legacy。|

### 返回说明

原字符串。

### 异常说明

ValueError。

源码：[`src/chronaxis/legacy/decode_policy.py:7`](../../../src/chronaxis/legacy/decode_policy.py#L7)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-check_decode_length"></a>
## `check_decode_length`

解码前检查所需帧长度，不复制载荷或检查无关报文。

```python
check_decode_length(frame, expected, policy)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|can.Message &#124; LegacyRawFrame|是|无|位置或关键字。当前实际帧或冻结帧快照；通过公开ID、通道、标志及载荷属性检查和定位，不接受DBC定义代替输入帧。|
|`expected`|int|是|无|位置或关键字。DBC定义的载荷字节长度，用于与实际帧长度核对，不是DLC编码值。|
|`policy`|str|是|无|位置或关键字。解码长度政策：strict严格长度，partial允许短载荷，legacy保留原解码路径。|

### 返回说明

None；partial仅允许载荷短于DBC，不能掩盖DLC与实际字节不一致。

### 异常说明

ValueError表示结构或所选长度政策不符；属性访问错误原样传播。

源码：[`src/chronaxis/legacy/decode_policy.py:15`](../../../src/chronaxis/legacy/decode_policy.py#L15)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-decode_serial_frame"></a>
## `decode_serial_frame`

保留纯BLF串行的既有解码政策，不重复检查报文长度或缩放物理值。

```python
decode_serial_frame(database, frame, message, duplicate_ids)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`database`|cantools.database.can.Database|是|无|位置或关键字。同次加载的DBC数据库；唯一ID使用decode_message，保留该串行路径普通Exception转缺值行为。|
|`frame`|LegacyRawFrame &#124; can.Message|是|无|位置或关键字。当前原始帧，提供ID和data；长度已由调用侧按所选政策检查。|
|`message`|cantools.database.can.Message &#124; None|是|无|位置或关键字。按实际帧型已选定的定义；同ID有多个定义时直接使用它解码，None沿数据库入口处理。|
|`duplicate_ids`|frozenset[int] &#124; set[int]|是|无|位置或关键字。DBC内同一数值ID具有多个定义的集合；这些ID只将DecodeError转缺值，其他异常传播。|

### 返回说明

解码值字典或失败时的空字典。

### 异常说明

唯一ID捕获普通Exception；多定义仅捕获DecodeError，其他错误原样传播。
    这一区别只用于明确的串行兼容入口，普通并行和文本入口不自动套用。

源码：[`src/chronaxis/legacy/decode_policy.py:30`](../../../src/chronaxis/legacy/decode_policy.py#L30)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
