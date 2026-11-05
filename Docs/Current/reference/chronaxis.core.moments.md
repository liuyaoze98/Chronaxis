# `chronaxis.core.moments`

声明 v4 样本与时间二阶统计的操作、自由度和输出量纲。

这里只校验静态契约。归约器使用实际有效更新或选中区间的权重，
其标量算法与数组算法各自实现，不在本模块累计任何历史。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`moment_ddof`](#api-moment_ddof)|检查显式自由度。|
|[`moment_source_unit`](#api-moment_source_unit)|推导归约数值的自然单位。|
|[`compute_moment_series`](#api-compute_moment_series)|让内存入口沿同后端的分块归约协议执行一次，返回完整数值和覆盖。|

<a id="api-moment_ddof"></a>
## `moment_ddof`

检查显式自由度。

```python
moment_ddof(operation, value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。已声明的计算操作。样本方差和标准差允许修正分母，时间总体仅接受零，RMS 不使用该参数。|
|`value`|int &#124; None|是|无|位置或关键字。配置中的自由度修正整数，省略传 None。适用的方差或标准差此时取默认零。|

### 返回说明

适用的整数或None。

### 异常说明

不适用或越界。

源码：[`src/chronaxis/core/moments.py:13`](../../../src/chronaxis/core/moments.py#L13)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-moment_source_unit"></a>
## `moment_source_unit`

推导归约数值的自然单位。

```python
moment_source_unit(operation, unit)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`operation`|str|是|无|位置或关键字。决定自然输出量纲的操作名称，方差取平方，标准差取差量单位，RMS 保留原单位。|
|`unit`|Unit &#124; None|是|无|位置或关键字。输入表达式经注册表解析得到的单位；未知单位无法推导，绝对摄氏需先转为开尔文才能求 RMS。|

### 返回说明

Unit。

### 异常说明

未知单位或偏移RMS。

源码：[`src/chronaxis/core/moments.py:26`](../../../src/chronaxis/core/moments.py#L26)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-compute_moment_series"></a>
## `compute_moment_series`

让内存入口沿同后端的分块归约协议执行一次，返回完整数值和覆盖。

```python
compute_moment_series(series, spec, sample_kernel, time_kernel, conditioned_kernel, step_ns)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`series`|CalculationSeries|是|无|位置或关键字。含区间、数值、实际更新及可选选择条件的内存时间序列。|
|`spec`|CalculationDefinition|是|无|位置或关键字。已校验的统计定义，提供操作、请求范围、选择政策和结果单位。|
|`sample_kernel`|type|是|无|位置或关键字。所选后端的真实样本归约器类，样本方差、标准差或 RMS 通过它累计。|
|`time_kernel`|type|是|无|位置或关键字。所选后端无筛选条件的时间归约器类，按有效保持时长加权。|
|`conditioned_kernel`|type|是|无|位置或关键字。所选后端带条件的时间归约器类，同时核对条件已知和有效时长。|
|`step_ns`|int &#124; None|是|无|位置或关键字。选定计时间隔的固定周期纳秒数；使用实际时间间隔时传 None。|

### 返回说明

CalculationResult。

### 异常说明

与分块公开执行相同的类型、单位和时间错误。

源码：[`src/chronaxis/core/moments.py:41`](../../../src/chronaxis/core/moments.py#L41)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
