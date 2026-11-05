# `chronaxis.execution.where_state`

从最新完整组提取 where 的反事实输入和活动更新证据，不读历史文件。

同一组可能同时替换条件与两个分支。取状态已保存的旧规范标量，在本时刻检查
TTL 和来源范围，两种后端分别解释前后条件。所需临时空间由调用侧查询预付。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`before_context`](#api-before_context)|构造同一时刻排除最近组的点、右侧或左侧保持。|
|[`scalar_columns`](#api-scalar_columns)|单点 NumPy 调用保留原 dtype/标签。|
|[`group_updates`](#api-group_updates)|计算原子组是否更新输出。|
|[`group_active`](#api-group_active)|检查标记输入是否活动。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..core.numeric import ScalarValue
from ..core.types import QualityFlag as Q
from ..core.where_updates import reference_updates, numpy_updates, reference_active, numpy_active
```

</details>

<a id="api-before_context"></a>
## `before_context`

构造同一时刻排除最近组的点、右侧或左侧保持。

```python
before_context(state, names, time, *, ends=None, bounds=None, continuous=False, left_limit=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`state`|LatestSignalState|是|无|位置或关键字。已提交最近一组真实更新的状态容器，保存可回查的组前值和有效期。|
|`names`|Iterable[str]|是|无|位置或关键字。仅为当前表达式所依赖的信号别名构建反事实输入。|
|`time`|int|是|无|位置或关键字。用于组前保持和 TTL、来源观测边界检查的实际纳秒时刻。|
|`ends`|Mapping[str, int] &#124; None|否|None|仅关键字。可选的来源到观测结束纳秒数映射，未提供完整起止范围时使用。|
|`bounds`|Mapping[str, tuple[int, int]] &#124; None|否|None|仅关键字。可选的来源到观测起止纳秒坐标映射，优先于只包含终点的 ends。|
|`continuous`|bool|否|False|仅关键字。查询连续区间时，观测终点本身不再向后贡献时长。|
|`left_limit`|bool|否|False|仅关键字。为真时取该时刻之前的保持值，用于区分更新前后。|

### 返回说明

标量映射。

### 异常说明

声明或类型错误；不回退状态。

源码：[`src/chronaxis/execution/where_state.py:12`](../../../src/chronaxis/execution/where_state.py#L12)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-scalar_columns"></a>
## `scalar_columns`

单点 NumPy 调用保留原 dtype/标签。

```python
scalar_columns(context)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`context`|Mapping[str, [ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。当前标量视图，将每个别名装成单行列供数组后端求值。|

### 返回说明

单行列映射，大整数不转 float。

### 异常说明

非法标签或列类型。

源码：[`src/chronaxis/execution/where_state.py:40`](../../../src/chronaxis/execution/where_state.py#L40)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-group_updates"></a>
## `group_updates`

计算原子组是否更新输出。

```python
group_updates(root, context, previous, updates, backend)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|ExprNode|是|无|位置或关键字。要遍历的编译表达式树，从其中定位 where 的条件和可见分支。|
|`context`|Mapping[str, [ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。原子更新提交后的当前标量视图，选取活动条件及分支。|
|`previous`|Mapping[str, [ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。同一时间坐标上排除刚提交更新的组前值，判定条件切换或恢复。|
|`updates`|Mapping[str, bool]|是|无|位置或关键字。标记哪些别名在本次原子组实际收到新观测。|
|`backend`|str|是|无|位置或关键字。本次已经选定的 reference 或 numpy 后端，按相同更新语义分别求值。|

### 返回说明

bool。

### 异常说明

求值原错。

源码：[`src/chronaxis/execution/where_state.py:57`](../../../src/chronaxis/execution/where_state.py#L57)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-group_active"></a>
## `group_active`

检查标记输入是否活动。

```python
group_active(root, context, flags, backend)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|ExprNode|是|无|位置或关键字。要遍历的编译表达式树，从其中定位 where 的条件和可见分支。|
|`context`|Mapping[str, [ScalarValue](chronaxis.core.numeric.md#api-ScalarValue)]|是|无|位置或关键字。原子更新提交后的当前标量视图，选取活动条件及分支。|
|`flags`|Mapping[str, bool]|是|无|位置或关键字。待检查的输入标志，如结束、无效或缺失原因，只检查活动分支。|
|`backend`|str|是|无|位置或关键字。本次已经选定的 reference 或 numpy 后端，按相同更新语义分别求值。|

### 返回说明

bool。

### 异常说明

求值错误。

源码：[`src/chronaxis/execution/where_state.py:68`](../../../src/chronaxis/execution/where_state.py#L68)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
