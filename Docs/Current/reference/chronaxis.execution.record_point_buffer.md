# `chronaxis.execution.record_point_buffer`

共享有限驱动点的接收与失效处理，不执行数值统计或创建历史。

积分和时间统计沿用同一同一时刻/递增/条件门槛，具体owner负责预付缓冲费用并实现_flush。
该内部基类不能独立构造使用；没有独立预算或第二份输入缓冲。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`RecordPointBuffer`](#api-RecordPointBuffer)|复用一份有限点缓冲，子类初始化字段并拥有数值状态及关闭过程。|
|[`RecordPointBuffer._require_open`](#api-RecordPointBuffer-_require_open)|失败/清理/关闭后拒绝读取与推进。|
|[`RecordPointBuffer.consume`](#api-RecordPointBuffer-consume)|接收已按所选驱动求值的有限点，不先截掉窗口两侧记录。|
|[`RecordPointBuffer.expire_at`](#api-RecordPointBuffer-expire_at)|依赖中途失效时截断最后待结算驱动点，不新增驱动点或补计周期。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D
from ..results.errors import ResultClosedError
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-RecordPointBuffer"></a>
## `RecordPointBuffer`

复用一份有限点缓冲，子类初始化字段并拥有数值状态及关闭过程。

```python
class RecordPointBuffer
```


源码：[`src/chronaxis/execution/record_point_buffer.py:13`](../../../src/chronaxis/execution/record_point_buffer.py#L13)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordPointBuffer-_require_open"></a>
### `RecordPointBuffer._require_open`

失败/清理/关闭后拒绝读取与推进。

```python
RecordPointBuffer._require_open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/record_point_buffer.py:16`](../../../src/chronaxis/execution/record_point_buffer.py#L16)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordPointBuffer-consume"></a>
### `RecordPointBuffer.consume`

接收已按所选驱动求值的有限点，不先截掉窗口两侧记录。

```python
RecordPointBuffer.consume(rows, *, conditions=None, condition_valid_until_ns=None, actual_value_updates=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rows`|Sequence[tuple]|是|无|位置或关键字。有限计算点序列：实际时刻、ScalarValue、数值实际截止、条件ScalarValue及其实际截止；样本统计另附真实更新标志。|
|`conditions`|Sequence[tuple[int, [ScalarValue](chronaxis.core.numeric.md#api-ScalarValue), int &#124; None]] &#124; None|否|None|仅关键字。与值点对应的条件记录，分别含实际时间、布尔值及实际截止；None表示无外部条件。|
|`condition_valid_until_ns`|Sequence[int &#124; None] &#124; None|否|None|仅关键字。各筛选条件的真实有效截止，单位纳秒；条件未知不能当作False或补零。|
|`actual_value_updates`|tuple[bool, ...] &#124; None|否|None|仅关键字。逐点真实值更新标志；用于样本统计排除条件变化和有效期边界。None不额外附加样本标志。|

#### 返回说明

None。

#### 异常说明

类型、时间倒退/同一时刻、预算/取消；任何错误后不交付前缀结果。

#### 约束说明

上游处理同一时刻、条件及TTL；无效值必须传入，不能跳过后连接有效值。

源码：[`src/chronaxis/execution/record_point_buffer.py:21`](../../../src/chronaxis/execution/record_point_buffer.py#L21)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RecordPointBuffer-expire_at"></a>
### `RecordPointBuffer.expire_at`

依赖中途失效时截断最后待结算驱动点，不新增驱动点或补计周期。

```python
RecordPointBuffer.expire_at(time_ns, *, condition=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int &#124; None|是|无|位置或关键字。指定依赖失效的实际时刻，传已按时间顺序处理的整数纳秒；必须在下一驱动点前通知，不接受None。|
|`condition`|bool|否|False|仅关键字。是否操作条件列的有效截止；False操作数值列，True操作条件列。|

#### 返回说明

None。

#### 异常说明

非法/回退时间或对象关闭失败；调用方必须在下一驱动点进入前通知。

源码：[`src/chronaxis/execution/record_point_buffer.py:79`](../../../src/chronaxis/execution/record_point_buffer.py#L79)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
