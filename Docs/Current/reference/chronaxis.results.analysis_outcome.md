# `chronaxis.results.analysis_outcome`

说明一次执行为何有或没有业务结果，不保存逐条输入或重复时间记录。

执行层在原有规则推进、指标写出时累计少量状态；本模块只冻结并校验这些事实，
供清单和CLI共用。事件存在与指标是否完整分别表示，不能以completed代替业务有效性。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`RuleOutcome`](#api-RuleOutcome)|一条规则的结果概况；未知可与已生成事件并存。|
|[`RuleOutcome.__post_init__`](#api-RuleOutcome-__post_init__)||
|[`RuleOutcome.to_dict`](#api-RuleOutcome-to_dict)||
|[`AnalysisOutcome`](#api-AnalysisOutcome)|规则状态与指标行计数；不根据事件数推断能量正确或数据完整。|
|[`AnalysisOutcome.__post_init__`](#api-AnalysisOutcome-__post_init__)||
|[`AnalysisOutcome.to_dict`](#api-AnalysisOutcome-to_dict)||

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass, asdict
from ..core.validation import require_identifier
```

</details>

<a id="api-RuleOutcome"></a>
## `RuleOutcome`

一条规则的结果概况；未知可与已生成事件并存。

```python
class RuleOutcome
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rule_id`|str|是|无|本条概况对应的规则名称，与事件表rule_id关联。|
|`status`|str|是|无|events_found表示生成事件；no_observation表示没有观测；insufficient_data表示缺少可判定数据；duration_not_met表示条件曾成立但未满足持续要求；condition_not_met表示条件未成立；no_event用于其他规则未生成事件。不能仅靠任务completed推断此状态。|
|`event_count`|int|是|无|该规则本次生成的事件数量，非负整数；不等于输入行数。|
|`has_unknown`|bool|是|无|是否出现无法确定的规则状态，可与events_found并存；不自动否定已输出的合格事件。|
|`unobserved_signals`|tuple[str, ...]|否|()|本规则需要但本次未观测到的信号别名元组；不包含未被该规则使用的信号。|

源码：[`src/chronaxis/results/analysis_outcome.py:12`](../../../src/chronaxis/results/analysis_outcome.py#L12)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RuleOutcome-__post_init__"></a>
### `RuleOutcome.__post_init__`



```python
RuleOutcome.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

TypeError/ValueError，状态或计数不合法。

源码：[`src/chronaxis/results/analysis_outcome.py:21`](../../../src/chronaxis/results/analysis_outcome.py#L21)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-RuleOutcome-to_dict"></a>
### `RuleOutcome.to_dict`



```python
RuleOutcome.to_dict()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

小型JSON对象。

#### 异常说明

无；不读取结果或输入。

源码：[`src/chronaxis/results/analysis_outcome.py:36`](../../../src/chronaxis/results/analysis_outcome.py#L36)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-AnalysisOutcome"></a>
## `AnalysisOutcome`

规则状态与指标行计数；不根据事件数推断能量正确或数据完整。

```python
class AnalysisOutcome
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rules`|tuple[[RuleOutcome](chronaxis.results.analysis_outcome.md#api-RuleOutcome), ...]|否|()|逐条RuleOutcome元组，说明每个规则为什么有或没有事件。|
|`complete`|int|否|0|计算结果中status为complete的行数，不是数值总和。|
|`partial`|int|否|0|计算结果中status为partial的行数；这些行的value只代表已知部分。|
|`indeterminate`|int|否|0|计算结果中status为indeterminate的行数；不能把空值当作0。|
|`no_observation`|int|否|0|计算结果中reason为no_observation的行数，是上述状态计数的子集，不能再与它们相加。|

源码：[`src/chronaxis/results/analysis_outcome.py:42`](../../../src/chronaxis/results/analysis_outcome.py#L42)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-AnalysisOutcome-__post_init__"></a>
### `AnalysisOutcome.__post_init__`



```python
AnalysisOutcome.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

TypeError/ValueError，重复规则或错误计数。

源码：[`src/chronaxis/results/analysis_outcome.py:51`](../../../src/chronaxis/results/analysis_outcome.py#L51)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-AnalysisOutcome-to_dict"></a>
### `AnalysisOutcome.to_dict`



```python
AnalysisOutcome.to_dict()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

清单/CLI同用的JSON对象。

#### 异常说明

无。

源码：[`src/chronaxis/results/analysis_outcome.py:63`](../../../src/chronaxis/results/analysis_outcome.py#L63)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
