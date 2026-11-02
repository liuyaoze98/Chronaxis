# chronaxis.build_preset

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.presets.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [build_preset](#api-build_preset)

<a id="api-build_preset"></a>
## `build_preset`

校验v1预设并展开公共声明，不执行I/O或数值分析。

```python
build_preset(spec: PresetSpec, signals: tuple[SignalDefinition, ...]) -> PlanFragment
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|[PresetSpec](PresetSpec.md#api-PresetSpec)|是|无|位置或关键字。提供PresetSpec预设声明，可用PresetSpec.from_dict({...})从必填name、preset_type、parameters，以及可选version、role_bindings的Python字典建立；完整可运行调用见预设API示例。|
|`signals`|tuple[[SignalDefinition](../reference/chronaxis.core.binding.md#api-SignalDefinition), ...]|是|无|位置或关键字。提供本计划的SignalDefinition元组，例如tuple(item.definition for item in plan.signals)，其中plan由load_analysis_plan取得；角色引用这些定义的name，不直接填CSV列名。|

### 返回说明

PlanFragment，生成请求的功率/Wh/Ah、报警、阈值迟滞/逐段时长或响应配对。

### 异常说明

PlanValidationError为参数/角色契约、模式编码范围及生成ID与信号冲突。

- PlanValidationError：模式编码超出已声明dtype/valid_range。

### 流程说明

检查角色→生成简单别名DSL→构造类型化节点→拒绝当前可见ID冲突。
    用户其他节点/多个预设的冲突由AnalysisPlan合入时继续检查。

返回类型：[PlanFragment](PlanFragment.md#api-PlanFragment)。

源码：[`src/chronaxis/presets.py:158`](../../../src/chronaxis/presets.py#L158)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
