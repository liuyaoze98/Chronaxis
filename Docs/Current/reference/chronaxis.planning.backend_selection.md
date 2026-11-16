# `chronaxis.planning.backend_selection`

依据整个计划的静态类别选择数值后端，不读取输入或试跑计算。

auto 覆盖已测量的简单积分和已完成对照验证的普通流式类别，后者可包含规则、窗口。
选择依据是当前验证范围，不代表任意表达式与数据的两后端结果均已逐位验证；
其他组合沿用 NumPy，显式选择始终优先。
选择结果供校验、说明和运行共用，不保存逐条执行记录，也不在失败后重试。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)

## 对象导航

|对象|用途|
|---|---|
|[`BackendSelection`](#api-BackendSelection)|保存一次静态选择：请求值、实际后端及可读原因，不代表已运行。|
|[`simple_numeric_expression`](#api-simple_numeric_expression)|检查首批实测的简单数值表达式。|
|[`select_backend`](#api-select_backend)|为整个计划选择一次后端。|
|[`_streaming_selection`](#api-_streaming_selection)|按已验证的算子范围为普通流式计划选择 reference，其余保留 NumPy。|
|[`execution_plan`](#api-execution_plan)|取得实际执行视图。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
```

</details>

<a id="api-BackendSelection"></a>
## `BackendSelection`

保存一次静态选择：请求值、实际后端及可读原因，不代表已运行。

```python
class BackendSelection
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`requested`|str|是|无|原配置或调用覆盖。|
|`selected`|str|是|无|reference/numpy；非法 带有明确类型的 声明为 unavailable。|
|`reason`|str|是|无|解释选择依据，不承诺具体提速比例。|

源码：[`src/chronaxis/planning/backend_selection.py:34`](../../../src/chronaxis/planning/backend_selection.py#L34)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-simple_numeric_expression"></a>
## `simple_numeric_expression`

检查首批实测的简单数值表达式。

```python
simple_numeric_expression(expression: StaticExpression | None) -> bool
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`expression`|[StaticExpression](chronaxis.core.expression.md#api-StaticExpression) &#124; None|是|无|位置或关键字。已经编译的表达式，None或不支持运算返回False；只遍历静态树。|

### 返回说明

bool。

### 异常说明

非法 带有明确类型的 结构。

仅遍历配置树；短路、查表、宿主函数和时序运算留在通用类别。

返回类型：bool。

源码：[`src/chronaxis/planning/backend_selection.py:42`](../../../src/chronaxis/planning/backend_selection.py#L42)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-select_backend"></a>
## `select_backend`

为整个计划选择一次后端。

```python
select_backend(plan: AnalysisPlan) -> BackendSelection
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。完整且已解析的原计划；保留raw_config和identity，不试读或试跑输入。|

### 返回说明

BackendSelection。

### 异常说明

非法 带有明确类型的 结构的属性错误；未知后端作为 unavailable 交给静态诊断。
不读取 DBC、日志或路径元数据，不修改原计划、身份或用户配置。

返回类型：[BackendSelection](chronaxis.planning.backend_selection.md#api-BackendSelection)。

源码：[`src/chronaxis/planning/backend_selection.py:61`](../../../src/chronaxis/planning/backend_selection.py#L61)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-_streaming_selection"></a>
## `_streaming_selection`

按已验证的算子范围为普通流式计划选择 reference，其余保留 NumPy。

```python
_streaming_selection(plan: AnalysisPlan, conservative: BackendSelection) -> BackendSelection
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。已解析且至少含一项计算的计划；上层已排除宿主扩展、时序变换、序列、结果聚合和逐消息计算。本函数只按每项operation是否属于已验证流式集合选择数值后端。|
|`conservative`|[BackendSelection](chronaxis.planning.backend_selection.md#api-BackendSelection)|是|无|位置或关键字。上层预先建立的保守BackendSelection结果，当前为auto请求下选择numpy；遇到集合外计算项时原样返回，不在此试跑或切换读取路径。|

### 返回说明

BackendSelection。

### 异常说明

无；只读静态声明，不读取数据。这里只选择数值后端；是否采用同帧直接积分由独立资格检查决定。

返回类型：[BackendSelection](chronaxis.planning.backend_selection.md#api-BackendSelection)。

源码：[`src/chronaxis/planning/backend_selection.py:108`](../../../src/chronaxis/planning/backend_selection.py#L108)（行号对应 Chronaxis 0.1.0.dev5 源码）。

<a id="api-execution_plan"></a>
## `execution_plan`

取得实际执行视图。

```python
execution_plan(plan: AnalysisPlan) -> AnalysisPlan
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。完整且已解析的原计划；保留raw_config和identity，不试读或试跑输入。|

### 返回说明

原计划或仅后端变化的视图。

### 异常说明

未支持后端为 ValueError；不修改 raw_config/identity，不重载来源。

返回类型：[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)。

源码：[`src/chronaxis/planning/backend_selection.py:119`](../../../src/chronaxis/planning/backend_selection.py#L119)（行号对应 Chronaxis 0.1.0.dev5 源码）。
