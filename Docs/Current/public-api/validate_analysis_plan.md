# chronaxis.validate_analysis_plan

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.planning.reports.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [validate_analysis_plan](#api-validate_analysis_plan)

<a id="api-validate_analysis_plan"></a>
## `validate_analysis_plan`

报告静态配置有效性及当前读取、执行和发布能力限制。

```python
validate_analysis_plan(plan: AnalysisPlan) -> ValidationReport
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|是|无|位置或关键字。提供已校验的AnalysisPlan，通过load_analysis_plan("analysis.yaml")取得，或用AnalysisPlan.from_dict(config)从Python字典建立；这里不接收YAML文件名字符串。|

### 返回说明

ValidationReport。合法已接入计划valid为True且errors为空；warnings保留尚未核实的
    字段、观测范围和单位状态，capability_status记录当前接入情况。
    execution_ready随静态能力错误为False或True，不表示已读取或保证实际RAM。

### 异常说明

TypeError: 输入不是AnalysisPlan；配置构建错误应由构建入口先报告。

本函数直接报告的具体错误：

- `TypeError`：validate_analysis_plan需要AnalysisPlan。

### 副作用说明

无来源读取，不重新核实CSV、BLF/DBC、实际字段或物理测量含义。

返回类型：[ValidationReport](../reference/chronaxis.planning.reports.md#api-ValidationReport)。

### 调用示例

```python
from chronaxis import load_analysis_plan, validate_analysis_plan
plan = load_analysis_plan("Docs/Current/examples/analysis.yaml")
report = validate_analysis_plan(plan)
print(report.valid, report.execution_ready)
```

源码：[`src/chronaxis/planning/reports.py:231`](../../../src/chronaxis/planning/reports.py#L231)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
