# chronaxis.core.temporal_clock

检查本批实际边界对应的计时增量，不构造另一条时间轴。

实际模式不传增量；固定/DBC模式由上游仅在所选驱动更新时传入一个周期，
其余有效期、EOF等边界传0。增量仅供检测器当前候选计时，不进入事件输出。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`require_clock_advances`](#api-require_clock_advances)|核对计时模式和有限批增量。|

<a id="api-require_clock_advances"></a>
## `require_clock_advances`

核对计时模式和有限批增量。

```python
require_clock_advances(ticks, advances, record_clock, previous)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`ticks`|tuple[ConditionTick, ...]|是|无|位置或关键字。已经组成完整同一时刻组的条件记录，用于核对计时增量个数及首点规则。|
|`advances`|tuple[int, ...] &#124; None|是|无|位置或关键字。与本批完整时间组等长的非负计时增量；固定/DBC模式首组为0，实际时间模式必须为None。|
|`record_clock`|bool|是|无|位置或关键字。True按实际记录带来的累计步进处理时限；False沿日志真实时间推进，不另存完整计算时间轴。|
|`previous`|int &#124; None|是|无|位置或关键字。上一完整时间组的实际纳秒时刻；None表示尚无前序记录。|

### 返回说明

None。

### 异常说明

TypeError/ValueError，不推进任何状态；首点不能虚构前序周期。

源码：[`src/chronaxis/core/temporal_clock.py:8`](../../../src/chronaxis/core/temporal_clock.py#L8)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
