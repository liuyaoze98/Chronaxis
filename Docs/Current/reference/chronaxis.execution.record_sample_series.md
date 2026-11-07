# `chronaxis.execution.record_sample_series`

把一小批实际记录及有效截止交给既有样本统计/选择核。

只在当前批插入必要的失效边界，不保存另一条时间轴；这些边界的真实更新标志为False。
半开范围及共享右端由原CalculationSeries/CalculationDefinition处理，不把保持值当作新样本。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[Interval](chronaxis.core.models.md#api-Interval)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`sample_series`](#api-sample_series)|构造有界核输入。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.calculations import CalculationSeries
from ..core.models import Interval
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q
```

</details>

<a id="api-sample_series"></a>
## `sample_series`

构造有界核输入。

```python
sample_series(rows, unit, conditioned)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rows`|Sequence[tuple]|是|无|位置或关键字。有限计算点序列：实际时刻、ScalarValue、数值实际截止、条件ScalarValue及其实际截止；样本统计另附真实更新标志。|
|`unit`|str|是|无|位置或关键字。物理量或结果单位，如W、J、s；按本接口的单位检查与换算规则使用。|
|`conditioned`|bool|是|无|位置或关键字。是否同时保存和处理筛选条件；False时不创建无用条件列或条件历史。|

### 返回说明

CalculationSeries。

### 异常说明

类型/时间错误。

源码：[`src/chronaxis/execution/record_sample_series.py:12`](../../../src/chronaxis/execution/record_sample_series.py#L12)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
