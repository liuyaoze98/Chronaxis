# `chronaxis.planning.legacy_execution`

在读取前校验逐消息计划的时间域与CAN读取策略；不选择历史兼容路径。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[LegacyCANSpec](chronaxis.sources.can_spec.md#api-LegacyCANSpec)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`require_can_decode_scope`](#api-require_can_decode_scope)|在资源创建前检查请求时间域及CAN策略，不自动更换执行方式。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.models import Interval
from ..sources.can_spec import LegacyCANSpec
from .checks import PlanValidationError
```

</details>

<a id="api-require_can_decode_scope"></a>
## `require_can_decode_scope`

在资源创建前检查请求时间域及CAN策略，不自动更换执行方式。

```python
require_can_decode_scope(plan) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。plan为完整AnalysisPlan|

### 返回说明

None；requested按统一需求接普通、消息和原帧消费者，all保留显式完整诊断。

### 异常说明

PlanValidationError定位时间域、陈旧绑定或来源策略错误；其他属性错误原样传播。

本函数直接报告的具体错误：

- `PlanValidationError`：$.dataset.domain。

### 边界说明

不读文件、DBC或信号值；纯参数指标和空signals仍可请求其指标报文。

返回类型：None。

源码：[`src/chronaxis/planning/legacy_execution.py:8`](../../../src/chronaxis/planning/legacy_execution.py#L8)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
