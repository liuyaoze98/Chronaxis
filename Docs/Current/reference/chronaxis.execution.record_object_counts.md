# `chronaxis.execution.record_object_counts`

从已经封口的规则与窗口输出构建会话级对象计数，不回读结果仓。

规则检测器本就按事件身份输出一次，完整窗口核也只发布最终片段一次。
活动使用规则事件数，片段使用窗口发布次数，因此同一活动被多个窗口引用
不会重复计数。每个被请求的窗口仅保留一个整数。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[RecordTimeResult](chronaxis.execution.record_time_calculation.md#api-RecordTimeResult)

## 对象导航

|对象|用途|
|---|---|
|[`object_count_results`](#api-object_count_results)|逐项交付具有状态及质量的会话计数。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.counts_v4 import OBJECT_COUNTS, classify_count
from .record_time_calculation import RecordTimeResult
```

</details>

<a id="api-object_count_results"></a>
## `object_count_results`

逐项交付具有状态及质量的会话计数。

```python
object_count_results(plan, rules, segment_counts)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。本次已校验的计划，提供请求范围及分别引用规则或窗口的计数指标。|
|`rules`|Sequence[RecordRuleTimeline]|是|无|位置或关键字。本次已完成的规则时间线，按目标规则取得已发现对象数及可判定范围。|
|`segment_counts`|Mapping[str, int]|是|无|位置或关键字。按窗口名称保存最终实际生成的片段数，已合并的多个活动只贡献一个片段。|

### 返回说明

(CalculationPlan,RecordTimeResult)迭代器，输出单位固定为1。

### 异常说明

尚未完成的规则或不合法引用直接失败，不能在事件流前缀上报告完成。

源码：[`src/chronaxis/execution/record_object_counts.py:12`](../../../src/chronaxis/execution/record_object_counts.py#L12)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
