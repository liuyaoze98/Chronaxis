# `chronaxis.core.calculations_numpy`

用数组计算保持值积分、时间统计、TRUE时长及真实样本统计。

compute_numpy接收CalculationSeries和CalculationDefinition，打包成同长数值与质量列，
裁剪时间端点，计算区间掩码，再归约面积、样本及覆盖时长，输出CalculationResult。
时间轴为形状(N,)的int64纳秒列，积分区间为形状(N-1,)；先用整数端点
求差再换算秒。数值列保留声明类型，积分与样本平均先检查float64精度。
时间极值在正裁剪区间取左端值，time_weighted_mean先规范化有效时长权重，duration
用BOOL TRUE掩码归约时长；select_numpy批量筛选真实更新后逐行恢复带有明确类型的输出。

条件以known和condition两个bool掩码区分已知真假与UNKNOWN（未知）。
无效数值的零和条件的False仅是存储占位，不能当作正常数据。
样本统计只含半开窗口内的真实数值更新，窗口与有效期边界不造新样本。

依赖NumPy与核心模型；只共享检查、单位和结果分类，不调用参考数值。
所有计算使用新数组，不修改输入，不读写文件；完整内存布局不代表已满足
生产流式内存预算，性能提升也需要另行测量。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)、[NumpyIntegralSum](chronaxis.core.integral_sum_numpy.md#api-NumpyIntegralSum)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[SelectionRow](chronaxis.core.selection.md#api-SelectionRow)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`_sum_finite_numpy`](#api-_sum_finite_numpy)|保留原顺序归约一列有限浮点项，避免大数消去时丢掉低位。|
|[`select_numpy`](#api-select_numpy)|通过NumPy掩码筛选真实更新，再逐行装箱输出。|
|[`compute_numpy`](#api-compute_numpy)|批量计算保持面积、样本/时间统计、BOOL TRUE时长和覆盖。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .calculations import make_calculation_result, calculation_conversion
from .calculations_reference import require_calculation
from .models import Interval
from .numeric_numpy import DTYPES, NumericArray, to_float_numpy
from .types import QualityFlag as Q, Truth
from .selection import SelectionRow, require_selection, partial_selection
from .integral_sum_numpy import NumpyIntegralSum
from .calculation_output_numpy import convert_result_numpy
from .affine_numpy import affine_numpy
from .moments import MOMENTS, compute_moment_series
from .quantiles import SAMPLE_QUANTILES, compute_quantile_series
from .numeric import ScalarValue
```

</details>

<a id="api-_sum_finite_numpy"></a>
## `_sum_finite_numpy`

保留原顺序归约一列有限浮点项，避免大数消去时丢掉低位。

```python
_sum_finite_numpy(values)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|numpy.ndarray[float64]|是|无|位置或关键字。本次求和独占的一维数组，已筛出有效且有限的数值；未知项和NaN、无穷值不应放入此列。|

### 返回说明

(原量纲总和或None, 计算失败bool, QualityFlag)，不转换物理单位。

### 异常说明

结构错误、分配和取消直接传播；原序中间溢出由返回诊断说明。

### 流程说明

原面积、真实样本或已规范化权重项依次推进同一个数组误差核。
    容量取本次项数M：每项最多增加一个partial，因此不会引入固定4096阈值。
    完整内存入口仍为O(M)，不宣称有限批预算；不调用参考核或math.fsum。

源码：[`src/chronaxis/core/calculations_numpy.py:42`](../../../src/chronaxis/core/calculations_numpy.py#L42)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-select_numpy"></a>
## `select_numpy`

通过NumPy掩码筛选真实更新，再逐行装箱输出。

```python
select_numpy(series, spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。series完整CalculationSeries|
|`spec`|CalculationDefinition|是|无|位置或关键字。spec为select请求。|

### 返回说明

SelectionRow迭代器，TRUE与UNKNOWN保留，FALSE排除。

### 异常说明

开始消费时传播输入/配置错误，分配失败不吞。

### 流程说明

建立(N,)时间、actual、known和TRUE列，批量选取输出索引。
    输出循环只恢复带有明确类型的行，不承担筛选计算。索引占O(N)内存，输出不攒列表。

源码：[`src/chronaxis/core/calculations_numpy.py:70`](../../../src/chronaxis/core/calculations_numpy.py#L70)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-compute_numpy"></a>
## `compute_numpy`

批量计算保持面积、样本/时间统计、BOOL TRUE时长和覆盖。

```python
compute_numpy(series, spec, *, step_ns=None, budget=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。完整CalculationSeries；spec为CalculationDefinition，声明半开纳秒窗口与算子。 spec还提供输出单位及report或strict数据不全时的处理方式；duration需BOOL输入。|
|`spec`|CalculationDefinition|是|无|位置或关键字。spec为CalculationDefinition，声明半开纳秒窗口与算子。     spec还提供输出单位及report或strict数据不全时的处理方式|
|`step_ns`|int &#124; None|否|None|仅关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`budget`|ResourceBudget &#124; None|否|None|仅关键字。可传入本次运行共享的内存账本。精确样本分位数据此为候选样本与排序空间预付费用，普通统计沿用原路径。|

### 返回说明

CalculationResult，保存数值、覆盖、未知范围、来源与质量原因；select另用行流入口。
    积分区间使用(N-1,)数组，真实样本选择使用(N,)掩码；正常零与None分开。

### 异常说明

类型、模型或单位配置错误直接传播；内存分配异常不转换成质量问题。
    非有限计算、下溢和精度失败写入质量原因。

### 流程说明

先打包列并检查精度，再裁剪整数时间区间、按有效值与TRUE掩码计算。
    各覆盖时长独立归约，最后恢复未知区间并应用一次输出单位转换。
    不逐样本调用参考计算，不广播错位输入，也不修改原列。

源码：[`src/chronaxis/core/calculations_numpy.py:115`](../../../src/chronaxis/core/calculations_numpy.py#L115)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
