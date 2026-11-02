# chronaxis.core.condition_evidence

整理事件检测器需要的条件结果。对同一个时刻，分别保存更新前、更新后以及该时刻本身的真假状态，并标明是否收到真实更新、是否结束读取。这样可以区分“条件变假”“数据失效”和“文件读完”。输出是ConditionTick序列；本模块不重新计算表达式。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)、[ConditionTick](chronaxis.core.temporal.md#api-ConditionTick)、[D](chronaxis.core.types.md#api-SignalDType)、[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)、[Truth](chronaxis.core.types.md#api-Truth)

## 对象导航

|对象|用途|
|---|---|
|[`_reference_truth`](#api-_reference_truth)|把已经验证的BOOL标量转为三值，未知存储占位不参加真假判断。|
|[`condition_ticks_reference`](#api-condition_ticks_reference)|独立逐点组装完整条件证据，不从来源推断更新标志或补造时间。|
|[`condition_ticks_numpy`](#api-condition_ticks_numpy)|独立按列构造因果与三值证据，最后仅恢复不可变ConditionTick模型。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .expression_reference import Evaluation
from .numeric import ScalarValue
from .temporal import ConditionTick
from .types import QualityFlag as Q, SignalDType as D, Truth
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-_reference_truth"></a>
## `_reference_truth`

把已经验证的BOOL标量转为三值，未知存储占位不参加真假判断。

```python
_reference_truth(result)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation)|是|无|位置或关键字。条件表达式的一次标量求值结果；其ScalarValue必须声明为BOOL，再转换为TRUE、FALSE或UNKNOWN。|

### 返回说明

Truth.TRUE、Truth.FALSE或Truth.UNKNOWN。

### 异常说明

无主动异常；调用者必须先完成带有明确类型的结果校验。

源码：[`src/chronaxis/core/condition_evidence.py:22`](../../../src/chronaxis/core/condition_evidence.py#L22)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-condition_ticks_reference"></a>
## `condition_ticks_reference`

独立逐点组装完整条件证据，不从来源推断更新标志或补造时间。

```python
condition_ticks_reference(times, before, continuous, point, actual_updates, invalid_updates, observation_ends, terminals)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|tuple[int, ...]|是|无|位置或关键字。严格递增的整数纳秒时间。使用不可修改的tuple。其余条件与标记列的项数必须与它一致。|
|`before`|tuple[[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation), ...]|是|无|位置或关键字。该时刻更新发生前的条件计算结果。须为BOOL，且与times中各时刻逐一对应；它与另外两个视图分别传入，不能用一个结果代替三种时间含义。|
|`continuous`|tuple[[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation), ...]|是|无|位置或关键字。该时刻更新后、接下来一段连续时间的条件计算结果。须为BOOL，且与times中各时刻逐一对应；它与另外两个视图分别传入，不能用一个结果代替三种时间含义。|
|`point`|tuple[[Evaluation](chronaxis.core.expression_reference.md#api-Evaluation), ...]|是|无|位置或关键字。该时刻本身的条件计算结果。须为BOOL，且与times中各时刻逐一对应；它与另外两个视图分别传入，不能用一个结果代替三种时间含义。|
|`actual_updates`|tuple|是|无|位置或关键字。同长原生bool tuple，当前条件依赖中是否有真实更新。|
|`invalid_updates`|tuple|是|无|位置或关键字。同长原生bool tuple，实际选中的更新样本是否无效； 不把保持值因TTL到期而无效算作真实无效更新，True必须同时有actual。|
|`observation_ends`|tuple|是|无|位置或关键字。同长原生bool tuple，条件依赖的来源是否在此刻结束观测。|
|`terminals`|tuple|是|无|位置或关键字。同长原生bool tuple，会话连续域是否结束；至多唯一末项， 不要求同时存在来源EOF，普通批次全False与空输入均合法。|

### 返回说明

tuple[ConditionTick, ...]，保留连续/点质量、真实因果及当前依赖诊断。

### 异常说明

TypeError为容器、原生元素、模型或非BOOL；ValueError为长度、回退/重复时间、
    非末terminal或invalid缺actual；OverflowError为时间越界；MemoryError为分配失败。

### 副作用说明

只创建当前有限输入的输出模型，不修改任何输入；申请预算由调用者负责。

源码：[`src/chronaxis/core/condition_evidence.py:36`](../../../src/chronaxis/core/condition_evidence.py#L36)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-condition_ticks_numpy"></a>
## `condition_ticks_numpy`

独立按列构造因果与三值证据，最后仅恢复不可变ConditionTick模型。

```python
condition_ticks_numpy(times, before, continuous, point, actual_updates, invalid_updates, observation_ends, terminals)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|numpy.ndarray[int64]|是|无|位置或关键字。严格递增的整数纳秒时间。要求一维int64数组。其余条件与标记列的项数必须与它一致。|
|`before`|[ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)|是|无|位置或关键字。该时刻更新发生前的条件计算结果。须为BOOL，且与times中各时刻逐一对应；它与另外两个视图分别传入，不能用一个结果代替三种时间含义。|
|`continuous`|[ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)|是|无|位置或关键字。该时刻更新后、接下来一段连续时间的条件计算结果。须为BOOL，且与times中各时刻逐一对应；它与另外两个视图分别传入，不能用一个结果代替三种时间含义。|
|`point`|[ArrayEvaluation](chronaxis.core.expression_numpy.md#api-ArrayEvaluation)|是|无|位置或关键字。该时刻本身的条件计算结果。须为BOOL，且与times中各时刻逐一对应；它与另外两个视图分别传入，不能用一个结果代替三种时间含义。|
|`actual_updates`|numpy.ndarray|是|无|位置或关键字。精确ndarray，形状(N,)的bool真实更新列。|
|`invalid_updates`|numpy.ndarray[bool]|是|无|位置或关键字。与时间轴等长的无效更新标记。True表示此刻实际收到的样本无效，因此actual_updates同一位置也必须为True；TTL到期不算收到新样本。|
|`observation_ends`|numpy.ndarray[bool]|是|无|位置或关键字。与时间轴等长；True表示条件依赖的某来源在此刻结束观测。|
|`terminals`|numpy.ndarray[bool]|是|无|位置或关键字。与时间轴等长的会话终点标记；最多最后一项为True。没有终点的分块可全部为False，空轴可传空数组。|

### 返回说明

tuple[ConditionTick, ...]；数值/因果计算整列完成，装箱不调用参考实现。

### 异常说明

TypeError为数组布局、模型或非BOOL；ValueError为shape、非递增时间或矛盾标志；
    MemoryError为列/输出分配失败。不隐式cast、不调用vectorize或标量参考数值核。
内存与

### 副作用说明

临时状态/quality/因果/诊断列均为(N,)，不修改借用的输入；预算须由调用者先申请。

源码：[`src/chronaxis/core/condition_evidence.py:114`](../../../src/chronaxis/core/condition_evidence.py#L114)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
