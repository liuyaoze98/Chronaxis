# `chronaxis.core.state_numpy`

用二分索引和质量掩码查询信号的最新观测，按有效期判断能否使用。

输入为已校验SignalSeries及shape=(N,)、dtype=int64的查询时间轴；输出等长的
值、valid、uint16质量、原样本索引和实际更新列。构造SignalArray只进行存储
编码，保持查询通过批量searchsorted和掩码执行，不调用参考对齐函数。
值保持声明类型，无效位置只是存储占位；原诊断保留在series.samples。
本模块依赖NumPy和核心模型，没有来源读取或文件操作；列数组复制后由本层
持有并标为只读，不修改调用者输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag](chronaxis.core.types.md#api-QualityFlag)、[SignalDType](chronaxis.core.types.md#api-SignalDType)、[SignalSeries](chronaxis.core.state.md#api-SignalSeries)

## 对象导航

|对象|用途|
|---|---|
|[`_require_axis`](#api-_require_axis)|检查完整一维int64非递减时间列，不做隐式cast或排序。|
|[`_readonly`](#api-_readonly)|复制局部列并标为只读，不修改调用者共享输入。|
|[`SignalArray`](#api-SignalArray)|保存一个信号的规范历史，将值、时间、有效性和质量分列存储。|
|[`SignalArray.__post_init__`](#api-SignalArray-__post_init__)|校验列布局，再复制持有只读数组。|
|[`build_signal_array`](#api-build_signal_array)|将规范逻辑样本存为按声明dtype的只读列，不进行归一化算术。|
|[`AlignedArray`](#api-AlignedArray)|保存查询轴上的保持结果，以及每个结果所用的原样本索引。|
|[`AlignedArray.__post_init__`](#api-AlignedArray-__post_init__)|校验对齐结果形状并复制只读，保持局部所有权。|
|[`align_numpy`](#api-align_numpy)|批量取最新样本，结合整数有效期及观测范围计算保持结果。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from types import MappingProxyType
from .state import SignalSeries
from .types import QualityFlag, SignalDType
```

</details>

<a id="api-_require_axis"></a>
## `_require_axis`

检查完整一维int64非递减时间列，不做隐式cast或排序。

```python
_require_axis(times_ns: np.ndarray) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times_ns`|np.ndarray|是|无|位置或关键字。times_ns为ndarray，形状(N,)，dtype=int64，单位纳秒|

### 返回说明

None；不修改输入所有权、writeable或内容。

### 异常说明

TypeError为类型/dtype/masked数组；ValueError为形状/回退。

本函数直接报告的具体错误：

- `TypeError`：时间轴必须为完整int64 ndarray。
- `ValueError`：时间轴必须为一维非递减。

返回类型：None。

源码：[`src/chronaxis/core/state_numpy.py:30`](../../../src/chronaxis/core/state_numpy.py#L30)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_readonly"></a>
## `_readonly`

复制局部列并标为只读，不修改调用者共享输入。

```python
_readonly(values: np.ndarray) -> np.ndarray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`values`|np.ndarray|是|无|位置或关键字。values为ndarray列|

### 返回说明

本层持有的独立只读连续副本。

### 异常说明

NumPy分配错误传播；不宣称整体执行器内存有界。

返回类型：np.ndarray。

源码：[`src/chronaxis/core/state_numpy.py:47`](../../../src/chronaxis/core/state_numpy.py#L47)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalArray"></a>
## `SignalArray`

保存一个信号的规范历史，将值、时间、有效性和质量分列存储。

所有列shape=(Ni,)，时间int64且严格递增。values保持声明dtype，enum使用
int64代码及固定标签域；valid为bool，quality为uint16。无效值只作占位，
原诊断仍可从series.samples获取。构造时独立复制列并设只读；这是NumPy
写保护约定，不能作为防恶意内存改写保证。

```python
class SignalArray
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[SignalSeries](chronaxis.core.state.md#api-SignalSeries)|是|无|原规范样本/来源/绑定，提供完整身份。|
|`times_ns`|np.ndarray|是|无|(Ni,) int64纳秒。|
|`values`|np.ndarray|是|无|(Ni,) 声明数值/bool或enum int64编码。|
|`valid`|np.ndarray|是|无|(Ni,) bool，invalid占位不参加计算。|
|`quality`|np.ndarray|是|无|(Ni,) uint16，最高质量位256。|
|`labels`|tuple[str, ...]|否|()|enum代码对应标签，其他dtype为空。|

源码：[`src/chronaxis/core/state_numpy.py:63`](../../../src/chronaxis/core/state_numpy.py#L63)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalArray-__post_init__"></a>
### `SignalArray.__post_init__`

校验列布局，再复制持有只读数组。

```python
SignalArray.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；读取series及Ni等长带有明确类型的列/labels。

#### 返回说明

None；调用者数组保持原状，本对象列独立。

#### 异常说明

TypeError/ValueError为dtype/形状/质量矛盾或不匹配历史。

本函数直接报告的具体错误：

- `TypeError`：SignalArray需要SignalSeries。
- `TypeError`：signal列必须为完整ndarray。
- `ValueError`：signal列形状/样本数量不一致。
- `TypeError`：signal列dtype不匹配声明。
- `ValueError`：规范历史时间必须严格递增。
- `ValueError`：signal有效性与质量矛盾或有未知位。
- `TypeError`：labels必须为enum tuple域。
- `ValueError`：enum标签与当前定义不符。
- `ValueError`：数组时间与原规范观测不符。
- `ValueError`：数组valid/quality与原观测不符。
- `ValueError`：数组有效值与规范观测不符。

返回类型：None。

源码：[`src/chronaxis/core/state_numpy.py:79`](../../../src/chronaxis/core/state_numpy.py#L79)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-build_signal_array"></a>
## `build_signal_array`

将规范逻辑样本存为按声明dtype的只读列，不进行归一化算术。

```python
build_signal_array(series: SignalSeries) -> SignalArray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|[SignalSeries](chronaxis.core.state.md#api-SignalSeries)|是|无|位置或关键字。series为SignalSeries|

### 返回说明

SignalArray；invalid存储占位0/False，仅valid位置可计算。

### 异常说明

TypeError为序列；结构/分配异常传播。

本函数直接报告的具体错误：

- `TypeError`：build_signal_array需要SignalSeries。

返回类型：[SignalArray](chronaxis.core.state_numpy.md#api-SignalArray)。

源码：[`src/chronaxis/core/state_numpy.py:145`](../../../src/chronaxis/core/state_numpy.py#L145)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-AlignedArray"></a>
## `AlignedArray`

保存查询轴上的保持结果，以及每个结果所用的原样本索引。

所有列shape=(N,)并独立只读。sample_indices=-1表示无历史，不能直接
用来取数组末项；非负索引可从history.series.samples取得原诊断。
actual_update只在当前会话视图中真实更新时成立。无效values仅为存储占位，
必须结合valid与quality决定能否计算。

```python
class AlignedArray
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|[SignalArray](chronaxis.core.state_numpy.md#api-SignalArray)|是|无|原列及完整绑定身份。|
|`times_ns`|np.ndarray|是|无|(N,) 当前查询轴int64。|
|`values`|np.ndarray|是|无|(N,) 与历史相同dtype。|
|`valid`|np.ndarray|是|无|(N,) 可使用掩码。|
|`quality`|np.ndarray|是|无|(N,) uint16原因组合。|
|`sample_indices`|np.ndarray|是|无|(N,) int64，-1为没有历史。|
|`actual_update`|np.ndarray|是|无|(N,) bool，计时器不伪造更新。|

源码：[`src/chronaxis/core/state_numpy.py:172`](../../../src/chronaxis/core/state_numpy.py#L172)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-AlignedArray-__post_init__"></a>
### `AlignedArray.__post_init__`

校验对齐结果形状并复制只读，保持局部所有权。

```python
AlignedArray.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无；各列须为与查询轴等长的一维数组。

#### 返回说明

None；所有结果列独立只读副本。

#### 异常说明

TypeError/ValueError为内部结果结构或质量矛盾。

本函数直接报告的具体错误：

- `TypeError`：aligned需要SignalArray history。
- `ValueError`：aligned结果列形状不一致。
- `TypeError`：aligned结果dtype不匹配。
- `ValueError`：aligned原样本索引超界。
- `ValueError`：aligned有效性与质量矛盾。

返回类型：None。

源码：[`src/chronaxis/core/state_numpy.py:189`](../../../src/chronaxis/core/state_numpy.py#L189)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-align_numpy"></a>
## `align_numpy`

批量取最新样本，结合整数有效期及观测范围计算保持结果。

```python
align_numpy(history: SignalArray, times_ns: np.ndarray, *, point: bool=False, strict_before: bool=False, left_limit: bool=False) -> AlignedArray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`history`|[SignalArray](chronaxis.core.state_numpy.md#api-SignalArray)|是|无|位置或关键字。当前信号的已校验只读历史。|
|`times_ns`|np.ndarray|是|无|位置或关键字。非递减整数纳秒查询轴。|
|`point`|bool|否|False|仅关键字。默认False，连续范围左闭右开；True包含真实观测末端。|
|`strict_before`|bool|否|False|仅关键字。默认False；True只取sample_time < t的样本， 在当前t检查有效期和来源范围，不计算可能溢出的t-1。|
|`left_limit`|bool|否|False|仅关键字。仅可用于 strict_before，检查 t 的左侧保持；到期恰为 t 时 旧值仍覆盖左邻域。不会改变普通查询的有效期和来源端点。|

### 返回说明

AlignedArray: 等长值列、有效掩码、质量原因、原索引及实际更新证据。
    值类型保持原声明，最新无效更新仍覆盖旧值；无历史使用索引-1。

### 异常说明

TypeError或ValueError: 历史、模式标志、时间列类型、形状或顺序错误。
    MemoryError: 输出或临时数组分配失败。

本函数直接报告的具体错误：

- `TypeError`：数组对齐需要SignalArray及bool point。

### 处理流程说明

用searchsorted查最新更新，先排除会话外索引，再按整数差计算有效期，
    最后叠加来源缺失原因；点/右侧保持要求 age < valid_for_ns。

### 副作用说明

输入只读使用，结果列由模型复制持有；输出和临时列占用O(N)空间。

返回类型：[AlignedArray](chronaxis.core.state_numpy.md#api-AlignedArray)。

源码：[`src/chronaxis/core/state_numpy.py:226`](../../../src/chronaxis/core/state_numpy.py#L226)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
