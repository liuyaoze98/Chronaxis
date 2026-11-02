# chronaxis.explain_analysis_plan

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.planning.reports.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [explain_analysis_plan](#api-explain_analysis_plan)

<a id="api-explain_analysis_plan"></a>
## `explain_analysis_plan`

列出计划依赖、各节点计算方式、历史需求和预算声明。

```python
explain_analysis_plan(plan: AnalysisPlan) -> ExplainReport
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|是|无|位置或关键字。提供已校验的AnalysisPlan，通过load_analysis_plan("analysis.yaml")取得，或用AnalysisPlan.from_dict(config)从Python字典建立；这里不接收YAML文件名字符串。|

### 返回说明

ExplainReport。包括同一校验限制、依赖节点、history_ns和budget只读映射。
    已有数值内核与尚未接入节点分别标记，不能将整份计划当作全数组执行。

### 异常说明

TypeError: 输入不是AnalysisPlan。

### 处理流程说明

展开派生、规则、窗口和指标依赖；事件或片段范围的条件也参与依赖收集。
    原信号有效期与所需窗口pre取较大时长，只报告需求，不修改输入读取范围。

### 副作用说明

不运行分析、不读取数据，也不测量内存峰值。

返回类型：[ExplainReport](../reference/chronaxis.planning.reports.md#api-ExplainReport)。

### 调用示例

```python
from chronaxis import load_analysis_plan, explain_analysis_plan
plan = load_analysis_plan("Docs/Current/examples/analysis.yaml")
print(explain_analysis_plan(plan))
```

源码：[`src/chronaxis/planning/reports.py:381`](../../../src/chronaxis/planning/reports.py#L381)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
