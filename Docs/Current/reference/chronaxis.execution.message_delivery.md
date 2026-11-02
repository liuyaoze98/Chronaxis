# chronaxis.execution.message_delivery

在读取器已有预算内同步交付必要消息，不建立额外历史或结果副本。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`deliver_message`](#api-deliver_message)|先付本次投影费用，再同步调用消费者，返回后释放临时消息。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..results.budget import _reserve_owned_ram, _release_owned_ram
from .history import _metadata_bytes
```

</details>

<a id="api-deliver_message"></a>
## `deliver_message`

先付本次投影费用，再同步调用消费者，返回后释放临时消息。

```python
deliver_message(owner, projection, consumer, frame, sequence, values, time_ns, *, canonical_keys=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|具备_budget和_update_cost属性的读取器|是|无|位置或关键字。为本次临时消息投影预付和释放费用的读取器；消费者若延长消息寿命必须另行付费。|
|`projection`|CANUpdateProjection|是|无|位置或关键字。已经按当前需求筛选的字段/报文投影，决定这次交付哪些值。|
|`consumer`|Callable[[LegacyDecodedUpdate], None]|是|无|位置或关键字。同步处理当前所需报文更新；函数返回后读取器释放本次投影费用。|
|`frame`|can.Message &#124; LegacyRawFrame|是|无|位置或关键字。当前实际帧或冻结帧快照；通过公开ID、通道、标志及载荷属性检查和定位，不接受DBC定义代替输入帧。|
|`sequence`|int|是|无|位置或关键字。当前记录的非负顺序号；同一时刻记录仍有独立序号，不能当作时间戳。|
|`values`|Mapping[str, int &#124; float &#124; bool &#124; str &#124; None]|是|无|位置或关键字。当前所需字段到解码值的映射；缺失保留无效，不复制无关字段。|
|`time_ns`|int &#124; None|是|无|位置或关键字。当前记录的实际纳秒时刻；仅明确不需要采集时间的输入诊断可为None。|
|`canonical_keys`|bool|否|False|仅关键字。values的键是否已转换成当前接口规定的字段键；True复用受控内部键，不重新转一遍。|

### 返回说明

None，非目标帧不构造消息。

### 异常说明

预算/值/消费者及清理错误原样传播。

源码：[`src/chronaxis/execution/message_delivery.py:7`](../../../src/chronaxis/execution/message_delivery.py#L7)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
