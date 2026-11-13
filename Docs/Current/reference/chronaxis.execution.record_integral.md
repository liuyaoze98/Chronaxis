# `chronaxis.execution.record_integral`

在有限内存内累计已求值的驱动记录对，保留实际端点直到比例裁剪完成。

输入为已归一化并按驱动同一时刻政策归组的(time_ns, ScalarValue[, valid_until_ns])有限批；输出仅含
积分值、单位、完成状态和质量的内部结果。复用原两后端面积及原序误差求和，
一次只持当前批和一条跨批前值，不创建历史文件、原帧副本、贡献或未知范围列表。
调用方负责绑定/表达式/有效期判定，并在输入确实结束后调用finish；本组件不
读取文件或证明来源EOF。实际间隔使用必要更新间的真实差，固定/DBC使用
所选驱动记录对；有效期都按实际截止裁剪，没有完整记录对时不虚构尾段。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)、[CalculationSeries](chronaxis.core.calculations.md#api-CalculationSeries)、[D](chronaxis.core.types.md#api-SignalDType)、[Interval](chronaxis.core.models.md#api-Interval)、[NumpyIntegralSum](chronaxis.core.integral_sum_numpy.md#api-NumpyIntegralSum)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[RecordPointBuffer](chronaxis.execution.record_point_buffer.md#api-RecordPointBuffer)、[ReferenceIntegralSum](chronaxis.core.integral_sum_reference.md#api-ReferenceIntegralSum)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`RecordIntegralResult`](#api-RecordIntegralResult)|内部积分结果，不附逐条输入、时间对照或默认贡献记录；不充当公开发布清单。|
|[`RecordIntegral`](#api-RecordIntegral)|拥有有限驱动点缓冲和累计状态；失败后只能关闭，完成后只读结果。|
|[`RecordIntegral.__init__`](#api-RecordIntegral-__init__)|预付有界状态及点缓冲，数值临时数组在每次归约前另预约。|
|[`RecordIntegral._flush`](#api-RecordIntegral-_flush)|消费当前完整记录对并留下一个共享端点，首条/末条不凭空增加周期。|
|[`RecordIntegral.finish`](#api-RecordIntegral-finish)|输入调用方确认结束后结算最后完整记录对，返回精简内部结果。|
|[`RecordIntegral.closed`](#api-RecordIntegral-closed)|读取自有费用完全释放状态。|
|[`RecordIntegral.close`](#api-RecordIntegral-close)|释放自有缓冲/数值状态及费用，不操作外部输入和目录。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.integral_sum import require_partial_limit
from ..core.integral_sum_reference import ReferenceIntegralSum
from ..core.integral_sum_numpy import NumpyIntegralSum
from ..core.integral_terms_reference import compute_integral_terms_reference
from ..core.integral_terms_numpy import compute_integral_terms_numpy
from ..core.conditional_integral_terms_reference import compute_conditional_integral_terms_reference
from ..core.conditional_integral_terms_numpy import compute_conditional_integral_terms_numpy
from ..core.calculations import CalculationDefinition, CalculationSeries, calculation_unit, classify_calculation_value
from ..core.calculations import classify_coverage
from ..core.models import Interval
from ..core.numeric import ScalarValue
from ..core.record_intervals import require_record_step
from ..core.types import SignalDType as D, QualityFlag as Q
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from .record_point_buffer import RecordPointBuffer
from .history import _metadata_bytes
```

</details>

<a id="api-RecordIntegralResult"></a>
## `RecordIntegralResult`

内部积分结果，不附逐条输入、时间对照或默认贡献记录；不充当公开发布清单。

```python
class RecordIntegralResult
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|float &#124; None|是|无|已换到请求单位；未知与有效零分开。|
|`unit`|str|是|无|输出单位，仅最终转换一次。|
|`status`|str|是|无|沿既有complete/partial/indeterminate政策。|
|`reason`|str|是|无|正常、观测不足或数值失败等必要原因。|
|`quality`|[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)|是|无|输入和数值计算质量，不包含逐条副本。|
|`coverage_status`|str &#124; None|否|None|对明确配置的覆盖门槛给出的结论；独立于数值本身的complete/partial/indeterminate状态。|

源码：[`src/chronaxis/execution/record_integral.py:33`](../../../src/chronaxis/execution/record_integral.py#L33)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordIntegral"></a>
## `RecordIntegral`

拥有有限驱动点缓冲和累计状态；失败后只能关闭，完成后只读结果。

consume借用外部有限批；留下的点只含整数时间和冻结数值，费用归本实例。
同一时刻冲突须由上游既有同一时刻政策解决，不能在此任意覆盖或累计零跨度记录。

```python
RecordIntegral(budget, spec, input_unit, dtype, step_ns, *, backend='numpy', batch_intervals=64, partial_limit=4096, conditioned=False)
```

继承关系：[RecordPointBuffer](chronaxis.execution.record_point_buffer.md#api-RecordPointBuffer)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/execution/record_integral.py:44`](../../../src/chronaxis/execution/record_integral.py#L44)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordIntegral-__init__"></a>
### `RecordIntegral.__init__`

预付有界状态及点缓冲，数值临时数组在每次归约前另预约。

```python
RecordIntegral.__init__(budget, spec, input_unit, dtype, step_ns, *, backend='numpy', batch_intervals=64, partial_limit=4096, conditioned=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`spec`|[CalculationDefinition](chronaxis.core.calculations.md#api-CalculationDefinition)|是|无|位置或关键字。已核对的指标声明，包含算子、实际请求范围、数据不全时的处理方式和输出单位。|
|`input_unit`|str|是|无|位置或关键字。送入数值核的原计算值单位，用于校验输出单位以及积分的单位转换。|
|`dtype`|SignalDType|是|无|位置或关键字。计算值的数据类型；决定整数范围、浮点计算或枚举处理，不得隐式转float丢失整数精度。|
|`step_ns`|int &#124; None|是|无|位置或关键字。所选固定或DBC周期，单位纳秒且大于0；None表示采用实际时间间隔，不生成第二套时间坐标。|
|`backend`|str|否|'numpy'|仅关键字。计算实现：reference使用独立参考核，numpy使用数组核；两者遵守相同的业务和缺失数据规则。|
|`batch_intervals`|int|否|64|仅关键字。本对象一次交给数值核的相邻区间上限；为正整数，并受共享内存预算约束。|
|`partial_limit`|int|否|4096|仅关键字。一次数值归约允许保留的中间部分和数量上限，防止累计状态无界增长。|
|`conditioned`|bool|否|False|仅关键字。是否同时保存和处理筛选条件；False时不创建无用条件列或条件历史。|

#### 返回说明

新owner。

#### 异常说明

配置/预算/取消错误；构造清理失败通过异常的
    record_integral_cleanup_owner提供重试入口。

源码：[`src/chronaxis/execution/record_integral.py:51`](../../../src/chronaxis/execution/record_integral.py#L51)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordIntegral-_flush"></a>
### `RecordIntegral._flush`

消费当前完整记录对并留下一个共享端点，首条/末条不凭空增加周期。

```python
RecordIntegral._flush()
```

参数：无显式参数。


#### 参数说明

无，使用当前自有缓冲。

#### 返回说明

None。

#### 异常说明

数值结构/预算/取消；
    清理异常不覆盖原错误，临时申请保留在owner供close重试。

源码：[`src/chronaxis/execution/record_integral.py:100`](../../../src/chronaxis/execution/record_integral.py#L100)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordIntegral-finish"></a>
### `RecordIntegral.finish`

输入调用方确认结束后结算最后完整记录对，返回精简内部结果。

```python
RecordIntegral.finish()
```

参数：无显式参数。


#### 参数说明

无；不能代替读取器EOF/关闭成功的确认。

#### 返回说明

RecordIntegralResult，
    重复调用返回同一结果。

#### 异常说明

预算/数值结构/取消错误，不发布前缀。

源码：[`src/chronaxis/execution/record_integral.py:159`](../../../src/chronaxis/execution/record_integral.py#L159)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordIntegral-closed"></a>
### `RecordIntegral.closed`

读取自有费用完全释放状态。

```python
RecordIntegral.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_integral.py:188`](../../../src/chronaxis/execution/record_integral.py#L188)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordIntegral-close"></a>
### `RecordIntegral.close`

释放自有缓冲/数值状态及费用，不操作外部输入和目录。

```python
RecordIntegral.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；重复关闭安全。

#### 异常说明

预算释放失败可重试，不假报已关闭。

源码：[`src/chronaxis/execution/record_integral.py:192`](../../../src/chronaxis/execution/record_integral.py#L192)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
