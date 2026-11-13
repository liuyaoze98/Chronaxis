# `chronaxis.core.where_updates`

按 where 当前选择判断某一组是否更新输出，独立于输出的数值是否改变。

输入是原子提交后的输入、同一时刻排除该组的旧输入，以及各别名的真实更新标志。
只在条件实际更新时比较前后选择；因此仅刷新有效条件不会采样，失效后恢复会采样。
普通算子取各参数更新并集，嵌套选择递归套用同一协议；不保存时间历史。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)

## 对象导航

|对象|用途|
|---|---|
|[`contains_where`](#api-contains_where)|检查已编译 DAG 是否需要分支更新口径。|
|[`reference_updates`](#api-reference_updates)|按原子组计算标量更新标志。|
|[`reference_updates.visit`](#api-reference_updates-visit)|判断当前活动路径。|
|[`numpy_updates`](#api-numpy_updates)|以 NumPy 活动子批检查整列更新证据，不逐点解释。|
|[`numpy_updates.condition_at`](#api-numpy_updates-condition_at)|按活动行解释。|
|[`numpy_updates.visit`](#api-numpy_updates-visit)|同一活动行集内复用证据。|
|[`reference_active`](#api-reference_active)|只检查活动输入。|
|[`numpy_active`](#api-numpy_active)|按活动子批检查输入。|

<a id="api-contains_where"></a>
## `contains_where`

检查已编译 DAG 是否需要分支更新口径。

```python
contains_where(root)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|ExprNode|是|无|位置或关键字。要遍历的编译表达式树，从其中定位 where 的条件和可见分支。|

### 返回说明

bool。

### 异常说明

非法节点。

源码：[`src/chronaxis/core/where_updates.py:9`](../../../src/chronaxis/core/where_updates.py#L9)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-reference_updates"></a>
## `reference_updates`

按原子组计算标量更新标志。

```python
reference_updates(root, current, before, updates)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|ExprNode|是|无|位置或关键字。要遍历的编译表达式树，从其中定位 where 的条件和可见分支。|
|`current`|Mapping[str, ScalarValue]|是|无|位置或关键字。完整原子更新组生效后的别名输入，用于确定当前布尔条件及活动分支。|
|`before`|Mapping[str, ScalarValue] &#124; None|是|无|位置或关键字。排除本次原子组后的输入，比较更新前后的分支；None 表示只判定标记来源的活动性。|
|`updates`|Mapping[str, bool]|是|无|位置或关键字。各输入别名本次是否有真实更新的标志，未选分支的更新不会单独产生输出样本。|

### 返回说明

是否存在活动更新。

### 异常说明

输入/节点与绑定不符时沿用标量表达式核错误。

源码：[`src/chronaxis/core/where_updates.py:22`](../../../src/chronaxis/core/where_updates.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-reference_updates-visit"></a>
### `reference_updates.visit`

判断当前活动路径。

```python
reference_updates.visit(node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。正在处理的已编译子节点，包含操作、参数和输入依赖。|

#### 返回说明

bool。

#### 异常说明

同外层求值。

源码：[`src/chronaxis/core/where_updates.py:32`](../../../src/chronaxis/core/where_updates.py#L32)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-numpy_updates"></a>
## `numpy_updates`

以 NumPy 活动子批检查整列更新证据，不逐点解释。

```python
numpy_updates(root, current, before, updates, size)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|ExprNode|是|无|位置或关键字。要遍历的编译表达式树，从其中定位 where 的条件和可见分支。|
|`current`|Mapping[str, [NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)]|是|无|位置或关键字。完整原子更新组生效后的别名输入，用于确定当前布尔条件及活动分支。|
|`before`|Mapping[str, [NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)] &#124; None|是|无|位置或关键字。排除本次原子组后的输入，比较更新前后的分支；None 表示只判定标记来源的活动性。|
|`updates`|Mapping[str, numpy.ndarray]|是|无|位置或关键字。各输入别名本次是否有真实更新的标志，未选分支的更新不会单独产生输出样本。|
|`size`|int|是|无|位置或关键字。当前完整输入批的行数，所有值列和证据掩码必须对齐到这一长度。|

### 返回说明

一维布尔列。

### 异常说明

原数组布局/求值错误传播。

源码：[`src/chronaxis/core/where_updates.py:59`](../../../src/chronaxis/core/where_updates.py#L59)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-numpy_updates-condition_at"></a>
### `numpy_updates.condition_at`

按活动行解释。

```python
numpy_updates.condition_at(node, inputs, indices)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。正在处理的已编译子节点，包含操作、参数和输入依赖。|
|`inputs`|Mapping[str, [NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)]|是|无|位置或关键字。当前组或组前的原始输入列，按子批行号提取并求条件。|
|`indices`|numpy.ndarray|是|无|位置或关键字。当前活动子批在原始输入列中的行索引，筛选后保持原始坐标。|

#### 返回说明

BOOL 列。

#### 异常说明

数组求值错误。

源码：[`src/chronaxis/core/where_updates.py:69`](../../../src/chronaxis/core/where_updates.py#L69)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-numpy_updates-visit"></a>
### `numpy_updates.visit`

同一活动行集内复用证据。

```python
numpy_updates.visit(node, indices, cache)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。正在处理的已编译子节点，包含操作、参数和输入依赖。|
|`indices`|numpy.ndarray|是|无|位置或关键字。当前活动子批在原始输入列中的行索引，筛选后保持原始坐标。|
|`cache`|dict[ExprNode, numpy.ndarray]|是|无|位置或关键字。仅在行集合一致的子批内复用各节点的更新掩码。|

#### 返回说明

布尔列。

#### 异常说明

数组错误。

源码：[`src/chronaxis/core/where_updates.py:77`](../../../src/chronaxis/core/where_updates.py#L77)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-reference_active"></a>
## `reference_active`

只检查活动输入。

```python
reference_active(root, current, flags)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|ExprNode|是|无|位置或关键字。要遍历的编译表达式树，从其中定位 where 的条件和可见分支。|
|`current`|Mapping[str, ScalarValue]|是|无|位置或关键字。完整原子更新组生效后的别名输入，用于确定当前布尔条件及活动分支。|
|`flags`|Mapping[str, bool]|是|无|位置或关键字。按输入别名传入的待检查事件标志，如来源观测结束或原值无效。|

### 返回说明

bool。

### 异常说明

标量求值错误。

源码：[`src/chronaxis/core/where_updates.py:107`](../../../src/chronaxis/core/where_updates.py#L107)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-numpy_active"></a>
## `numpy_active`

按活动子批检查输入。

```python
numpy_active(root, current, flags, size)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|ExprNode|是|无|位置或关键字。要遍历的编译表达式树，从其中定位 where 的条件和可见分支。|
|`current`|Mapping[str, [NumericArray](chronaxis.core.numeric_numpy.md#api-NumericArray)]|是|无|位置或关键字。完整原子更新组生效后的别名输入，用于确定当前布尔条件及活动分支。|
|`flags`|Mapping[str, numpy.ndarray]|是|无|位置或关键字。按输入别名传入的待检查事件标志，如来源观测结束或原值无效。|
|`size`|int|是|无|位置或关键字。当前完整输入批的行数，所有值列和证据掩码必须对齐到这一长度。|

### 返回说明

布尔列。

### 异常说明

数组错误。

源码：[`src/chronaxis/core/where_updates.py:112`](../../../src/chronaxis/core/where_updates.py#L112)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
