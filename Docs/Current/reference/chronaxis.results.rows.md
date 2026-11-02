# chronaxis.results.rows

为当前平坦结果确定所属表和稳定排序键，不构造额外结果包装。

输入为已计算的冻结行；输出为固定表名和纯标量tuple，不读取来源或复制数值历史。
每个表按会话、业务对象和真实顺序排序，父ID明确关联事件或片段。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[SummaryCalculationRow](chronaxis.results.summary.md#api-SummaryCalculationRow)、[SummaryContributionRow](chronaxis.results.summary.md#api-SummaryContributionRow)、[SummaryCoverageCalculationRow](chronaxis.results.summary.md#api-SummaryCoverageCalculationRow)、[SummaryEventRow](chronaxis.results.summary.md#api-SummaryEventRow)、[SummaryInputRow](chronaxis.results.summary.md#api-SummaryInputRow)、[SummarySegmentRow](chronaxis.results.summary.md#api-SummarySegmentRow)、[SummarySelectionRow](chronaxis.results.summary.md#api-SummarySelectionRow)、[SummarySequenceRow](chronaxis.results.summary.md#api-SummarySequenceRow)

## 对象导航

|对象|用途|
|---|---|
|[`row_table`](#api-row_table)|返回行所属表名，不依赖外部对象属性反射。|
|[`row_sort_key`](#api-row_sort_key)|给出session、规则、起点、序号为主的确定排序键。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .summary import SummaryCalculationRow, SummaryCoverageCalculationRow, SummaryEventRow, SummarySequenceRow, SummarySegmentRow, SummaryContributionRow, SummaryInputRow, SummarySelectionRow, SUMMARY_MODELS
```

</details>

<a id="api-row_table"></a>
## `row_table`

返回行所属表名，不依赖外部对象属性反射。

```python
row_table(row: ResultRow) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|ResultRow|是|无|位置或关键字。row为已登记的结果行之一。|

### 返回说明

当前固定表名。

### 异常说明

TypeError为未注册类型。

本函数直接报告的具体错误：

- `TypeError`：未注册结果行类型。

返回类型：str。

源码：[`src/chronaxis/results/rows.py:12`](../../../src/chronaxis/results/rows.py#L12)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-row_sort_key"></a>
## `row_sort_key`

给出session、规则、起点、序号为主的确定排序键。

```python
row_sort_key(row: ResultRow) -> tuple
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|ResultRow|是|无|位置或关键字。row为带有明确类型的结果行。|

### 返回说明

不含浮点值或可变对象的tuple。

### 异常说明

TypeError为非法行；不在这里排序或重复原数据读取。

返回类型：tuple。

源码：[`src/chronaxis/results/rows.py:28`](../../../src/chronaxis/results/rows.py#L28)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
