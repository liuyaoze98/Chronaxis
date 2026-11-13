# `chronaxis.execution.groups`

定义现役记录流一次交付的完整同一时刻组，不执行磁盘回放或排序。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[HistorySample](chronaxis.execution.history_records.md#api-HistorySample)、[RecordSample](chronaxis.execution.record_sample.md#api-RecordSample)

## 对象导航

|对象|用途|
|---|---|
|[`DecodedTimeGroup`](#api-DecodedTimeGroup)|保存一个session在同一整数ns的全部更新；来源和原sequence仍独立。|
|[`DecodedTimeGroup.__post_init__`](#api-DecodedTimeGroup-__post_init__)|检查同一时刻、同会话和唯一原身份，不执行绑定或表达式。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..timebase.conversion import require_int64_ns
from .record_sample import RecordSample
from .history_records import HistorySample
```

</details>

<a id="api-DecodedTimeGroup"></a>
## `DecodedTimeGroup`

保存一个session在同一整数ns的全部更新；来源和原sequence仍独立。

```python
class DecodedTimeGroup
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|完整组的共同纳秒坐标。|
|`samples`|tuple[[HistorySample](chronaxis.execution.history_records.md#api-HistorySample) &#124; [RecordSample](chronaxis.execution.record_sample.md#api-RecordSample), ...]|是|无|同组全部原观测，不套用last_by_sequence策略。|

源码：[`src/chronaxis/execution/groups.py:8`](../../../src/chronaxis/execution/groups.py#L8)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-DecodedTimeGroup-__post_init__"></a>
### `DecodedTimeGroup.__post_init__`

检查同一时刻、同会话和唯一原身份，不执行绑定或表达式。

```python
DecodedTimeGroup.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；读取time_ns/samples。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError/OverflowError为结构或身份错误。

本函数直接报告的具体错误：

- `TypeError`：完整时间组需要非空HistorySample tuple。
- `ValueError`：时间组不能混用时间或session。
- `ValueError`：完整时间组重复原观测。

返回类型：None。

源码：[`src/chronaxis/execution/groups.py:14`](../../../src/chronaxis/execution/groups.py#L14)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
