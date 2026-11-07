# `chronaxis.timebase.numpy_ops`

对一列纳秒时间执行固定偏移或计算相邻时间差，返回独立的新数组。

输入必须是shape=(N,)、dtype=int64的ndarray，不接受浮点、uint64、object或
MaskedArray。先通过比较和布尔掩码证明加减安全，再执行NumPy数组运算，
保留同时间的零差值，允许空输入。输入只读使用，不排序或去重。
本模块只共享时间常量和标量偏移校验，不调用Python参考数值内核。输出和
临时掩码占用O(N)空间；没有文件操作、CAN访问或全局状态。这里只实现时间
运算，不能据此认定全部分析均已有数组实现。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[TimeOverflowError](chronaxis.timebase.conversion.md#api-TimeOverflowError)

## 对象导航

|对象|用途|
|---|---|
|[`_require_time_array`](#api-_require_time_array)|检查数组形状和定宽dtype，不以转换/广播修补错误输入。|
|[`shift_times_numpy`](#api-shift_times_numpy)|给全部时间坐标添加固定纳秒偏移，运算前先检查每项结果的范围。|
|[`time_deltas_numpy`](#api-time_deltas_numpy)|计算非递减时间轴的相邻纳秒差，先检查顺序及跨度再做数组减法。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .conversion import INT64_MAX, INT64_MIN, TimeOverflowError, require_int64_ns
```

</details>

<a id="api-_require_time_array"></a>
## `_require_time_array`

检查数组形状和定宽dtype，不以转换/广播修补错误输入。

```python
_require_time_array(times: np.ndarray) -> None
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|np.ndarray|是|无|位置或关键字。shape=(N,)、dtype=int64的纳秒列。|

### 返回说明

None: 只读验证，不转换或复制输入。

### 异常说明

TypeError: 非ndarray、MaskedArray或dtype不为原生int64。
    ValueError: 不是一维列数组。

本函数直接报告的具体错误：

- `TypeError`：时间数组必须为无MaskedArray掩码、dtype=int64的ndarray。
- `ValueError`：时间数组形状必须为(N,)。

返回类型：None。

源码：[`src/chronaxis/timebase/numpy_ops.py:18`](../../../src/chronaxis/timebase/numpy_ops.py#L18)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-shift_times_numpy"></a>
## `shift_times_numpy`

给全部时间坐标添加固定纳秒偏移，运算前先检查每项结果的范围。

```python
shift_times_numpy(times: np.ndarray, offset_ns: int) -> np.ndarray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|np.ndarray|是|无|位置或关键字。纳秒坐标，允许负值和未排序输入。|
|`offset_ns`|int|是|无|位置或关键字。int64范围内的固定偏移，单位为纳秒。|

### 返回说明

ndarray[int64], shape=(N,): 独立的新数组；输入不修改，空输入返回空数组。

### 异常说明

TypeError或ValueError: 输入类型、数据类型或形状不符合要求。
    TimeOverflowError: 偏移本身或任一偏移后坐标超出int64范围。

### 副作用说明

只分配输出和比较掩码，不调用参考相加函数或读取文件。

返回类型：np.ndarray。

源码：[`src/chronaxis/timebase/numpy_ops.py:39`](../../../src/chronaxis/timebase/numpy_ops.py#L39)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-time_deltas_numpy"></a>
## `time_deltas_numpy`

计算非递减时间轴的相邻纳秒差，先检查顺序及跨度再做数组减法。

```python
time_deltas_numpy(times: np.ndarray) -> np.ndarray
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`times`|np.ndarray|是|无|位置或关键字。非递减纳秒轴，允许相同时间。|

### 返回说明

ndarray[int64], shape=(max(N-1, 0),): 独立的新数组，保存非负相邻跨度。

### 异常说明

TypeError或ValueError: 输入类型、数据类型或形状错误，或者时间严格回退。
    TimeOverflowError: 两端坐标均合法，但相邻跨度超过int64上限。

### 处理流程说明

对负左端计算MAX+left作为安全右端阈值，右端严格超出阈值时拒绝。
    全部检查通过后再减法，不先计算可能回绕的差值。

### 副作用说明

输入只读使用；输出、阈值和掩码需要与输入长度成比例的空间。

返回类型：np.ndarray。

源码：[`src/chronaxis/timebase/numpy_ops.py:69`](../../../src/chronaxis/timebase/numpy_ops.py#L69)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
