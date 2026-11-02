# chronaxis.legacy.decode_policy

新原始报文入口的长度政策；只检查实际需要解码的数据帧。

不改旧解码函数，也不再次解码。旧函数返回空值时，下游把所需字段置为无效；
旧接口没有暴露失败原因，本层不猜测原因。legacy保留原来的调用行为。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`validate_decode_policy`](#api-validate_decode_policy)|核验长度政策。|
|[`check_decode_length`](#api-check_decode_length)|解码前检查所需帧长度，不复制载荷或检查无关报文。|

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

源码：[`src/chronaxis/legacy/decode_policy.py:8`](../../../src/chronaxis/legacy/decode_policy.py#L8)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

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

源码：[`src/chronaxis/legacy/decode_policy.py:16`](../../../src/chronaxis/legacy/decode_policy.py#L16)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
