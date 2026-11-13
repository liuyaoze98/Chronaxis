# `chronaxis.results.aggregation_row`

保存组级值、明确总体和互斥的纳入/排除计数，版本15不改变旧结果行。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`SummaryAggregationRow`](#api-SummaryAggregationRow)|一个实际分组的结果；配对小计是观测请求分类，参与率不是时间覆盖率。|
|[`SummaryAggregationRow.__post_init__`](#api-SummaryAggregationRow-__post_init__)|检查组身份、有限值、数值政策和计数守恒。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from ..core.types import QualityFlag as Q
from ..core.validation import require_identifier, require_text
```

</details>

<a id="api-SummaryAggregationRow"></a>
## `SummaryAggregationRow`

一个实际分组的结果；配对小计是观测请求分类，参与率不是时间覆盖率。

```python
class SummaryAggregationRow
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sequence`|int|是|无|本行在聚合输出中的非负稳定序号。|
|`dataset_id`|str|是|无|该结果所属分析数据集的标识，与其来源行关联。|
|`entity_id`|str|是|无|配置中被分析设备或对象的身份，分组可显式选用此键。|
|`session_id`|str|是|无|本次分析会话的身份，用于区分不同会话产生的结果。|
|`aggregation_id`|str|是|无|生成本行的根级聚合名称，可据此找到该项操作与总体定义。|
|`source_kind`|str|是|无|提供候选的来源类型，取 calculation、sequence、rule 或 window。|
|`source_id`|str|是|无|来源类型内唯一的已声明指标、配对、规则或窗口名称。|
|`operation`|str|是|无|实际执行的组内运算，如 count、mean 或 quantile。|
|`group_keys`|tuple[str, ...]|是|无|组身份的配置键名，顺序与 group_values 一一对应。|
|`group_values`|tuple[str, ...]|是|无|本组在各分组键上取得的身份值，全体一组时为空元组。|
|`value`|int &#124; float &#124; None|是|无|以结果单位表示的组数值；严格政策、空数值总体或无法判定时可为空。|
|`unit`|str|是|无|结果数值的物理单位，计数为 1，方差为平方单位。|
|`status`|str|是|无|组结果状态，complete、partial、indeterminate 或 empty，需结合原因阅读。|
|`reason`|str|是|无|解释组值与完整性判定，例如 ok、empty_population、partial_population 或 insufficient_count。|
|`candidate_count`|int|是|无|此组实际发现的全部候选行数，等于参与数加两类互斥的排除数。|
|`included_count`|int|是|无|按该操作和质量政策实际参与的候选数，对象计数的数值等于它。|
|`definition_excluded_count`|int|是|无|按业务定义不提供数值的候选数，如成功延迟总体中已确认超时的请求。|
|`quality_excluded_count`|int|是|无|因质量、覆盖或缺少所需证据而被排除的候选数。|
|`included_partial_count`|int|是|无|已纳入的数值指标中仍带部分状态的个数，是参与数的子集。|
|`matched_count`|int|是|无|配对来源中已成功匹配响应的请求数，其他来源为零。|
|`timeout_count`|int|是|无|在规定等待期有充分观测且确认超时的请求数。|
|`insufficient_observation_count`|int|是|无|响应观测不足而无法判定的请求数，与已确认超时分列。|
|`pending_count`|int|是|无|配对总体中未决请求的小计，本版最终聚合输出固定为零。|
|`discovery_complete`|bool|是|无|是否具备发现请求范围内全部候选对象的证据，独立于已发现行的参与质量。|
|`quality`|QualityFlag|是|无|本组来源证据和数值计算累积的质量位，用于解释何种数据或精度限制影响结果。|

源码：[`src/chronaxis/results/aggregation_row.py:10`](../../../src/chronaxis/results/aggregation_row.py#L10)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SummaryAggregationRow-__post_init__"></a>
### `SummaryAggregationRow.__post_init__`

检查组身份、有限值、数值政策和计数守恒。

```python
SummaryAggregationRow.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

无效协议直接拒绝。

源码：[`src/chronaxis/results/aggregation_row.py:39`](../../../src/chronaxis/results/aggregation_row.py#L39)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
