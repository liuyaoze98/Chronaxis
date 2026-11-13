# `chronaxis.execution.record_value_history`

只为需要回看范围的消费者保存计算值，一份实际时间和必要有效截止。

同一表达式/条件/驱动可共享此文件。最后一点留在内存，便于非驱动失效更新
它的截止；其余记录定长保存，可二分定位而无需全量核验或JSON重建。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)、[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ScalarValue](chronaxis.core.scalar.md#api-ScalarValue)

## 对象导航

|对象|用途|
|---|---|
|[`RecordValueHistory`](#api-RecordValueHistory)|拥有单个必要临时文件和最后一个计算点；没有原帧、原文或第二时间轴。|
|[`RecordValueHistory.__init__`](#api-RecordValueHistory-__init__)|预付有限读写状态，不立即建文件。|
|[`RecordValueHistory.count`](#api-RecordValueHistory-count)|含内存末点的记录数。|
|[`RecordValueHistory.last_time`](#api-RecordValueHistory-last_time)|最后真实驱动时刻。|
|[`RecordValueHistory._open`](#api-RecordValueHistory-_open)|拒绝失败/关闭后使用。|
|[`RecordValueHistory.append`](#api-RecordValueHistory-append)|写前一点并留下新点；输入是本执行器已验证的求值结果。|
|[`RecordValueHistory.expire_at`](#api-RecordValueHistory-expire_at)|非驱动失效只裁最后点，不添加假记录。|
|[`RecordValueHistory.at`](#api-RecordValueHistory-at)|读取一个实际记录，不全量扫描。|
|[`RecordValueHistory.lower`](#api-RecordValueHistory-lower)|二分首个不早于time_ns的索引。|
|[`RecordValueHistory.rows`](#api-RecordValueHistory-rows)|只借出范围两侧及其中的记录，保留裁剪分母。|
|[`RecordValueHistory.closed`](#api-RecordValueHistory-closed)|返回自有资源关闭状态。|
|[`RecordValueHistory.close`](#api-RecordValueHistory-close)|关闭必要文件并退款，不碰原输入。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from struct import Struct
from tempfile import TemporaryFile
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D, QualityFlag as Q
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
```

</details>

<a id="api-RecordValueHistory"></a>
## `RecordValueHistory`

拥有单个必要临时文件和最后一个计算点；没有原帧、原文或第二时间轴。

```python
RecordValueHistory(budget, path, dtype, conditioned=False, *, sample_updates=False, labels=())
```


源码：[`src/chronaxis/execution/record_value_history.py:14`](../../../src/chronaxis/execution/record_value_history.py#L14)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-__init__"></a>
### `RecordValueHistory.__init__`

预付有限读写状态，不立即建文件。

```python
RecordValueHistory.__init__(budget, path, dtype, conditioned=False, *, sample_updates=False, labels=())
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`path`|str &#124; Path|是|无|位置或关键字。本次任务专用路径；只操作本次登记的资源，不能指向原始输入或历史项目目录。|
|`dtype`|SignalDType|是|无|位置或关键字。计算值的数据类型；决定整数范围、浮点计算或枚举处理，不得隐式转float丢失整数精度。|
|`conditioned`|bool|否|False|位置或关键字。是否同时保存和处理筛选条件；False时不创建无用条件列或条件历史。|
|`sample_updates`|bool|否|False|仅关键字。是否额外保存真实样本更新标志；仅样本统计或select回读需要时开启。|
|`labels`|tuple[str, ...]|否|()|仅关键字。ENUM类型共享的合法标签表；历史中只保存索引，不逐行复制标签表。|

#### 返回说明

owner。

#### 异常说明

原构造错。

源码：[`src/chronaxis/execution/record_value_history.py:17`](../../../src/chronaxis/execution/record_value_history.py#L17)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-count"></a>
### `RecordValueHistory.count`

含内存末点的记录数。

```python
RecordValueHistory.count
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_value_history.py:42`](../../../src/chronaxis/execution/record_value_history.py#L42)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-last_time"></a>
### `RecordValueHistory.last_time`

最后真实驱动时刻。

```python
RecordValueHistory.last_time
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int或None。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_value_history.py:47`](../../../src/chronaxis/execution/record_value_history.py#L47)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-_open"></a>
### `RecordValueHistory._open`

拒绝失败/关闭后使用。

```python
RecordValueHistory._open()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

ResultClosedError。

源码：[`src/chronaxis/execution/record_value_history.py:51`](../../../src/chronaxis/execution/record_value_history.py#L51)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-append"></a>
### `RecordValueHistory.append`

写前一点并留下新点；输入是本执行器已验证的求值结果。

```python
RecordValueHistory.append(row, condition=None, *, actual_update=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|tuple[int, [ScalarValue](chronaxis.core.scalar.md#api-ScalarValue), int &#124; None]|是|无|位置或关键字。当前计算点的实际纳秒时刻、值以及实际有效截止；必须按递增时刻提交。|
|`condition`|tuple[int, [ScalarValue](chronaxis.core.scalar.md#api-ScalarValue), int &#124; None] &#124; None|否|None|位置或关键字。对应条件点的实际时刻、布尔值及有效截止；None表示没有外部条件。|
|`actual_update`|bool|否|False|仅关键字。该点是否由真实值记录更新产生；False的条件/失效边界不计作新样本。|

#### 返回说明

None。

#### 异常说明

顺序/短写/预算错误，失败后只能清理。

源码：[`src/chronaxis/execution/record_value_history.py:56`](../../../src/chronaxis/execution/record_value_history.py#L56)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-expire_at"></a>
### `RecordValueHistory.expire_at`

非驱动失效只裁最后点，不添加假记录。

```python
RecordValueHistory.expire_at(time_ns, *, condition=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|
|`condition`|bool|否|False|仅关键字。是否操作条件列的有效截止；False操作数值列，True操作条件列。|

#### 返回说明

None。

#### 异常说明

时间回退。

源码：[`src/chronaxis/execution/record_value_history.py:90`](../../../src/chronaxis/execution/record_value_history.py#L90)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-at"></a>
### `RecordValueHistory.at`

读取一个实际记录，不全量扫描。

```python
RecordValueHistory.at(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。当前内部序列的记录索引；读取时检查范围，不把越界当作空输入。|

#### 返回说明

点及条件五元组。

#### 异常说明

越界/短读。

源码：[`src/chronaxis/execution/record_value_history.py:101`](../../../src/chronaxis/execution/record_value_history.py#L101)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-lower"></a>
### `RecordValueHistory.lower`

二分首个不早于time_ns的索引。

```python
RecordValueHistory.lower(time_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`time_ns`|int|是|无|位置或关键字。本次操作对应的实际时刻，单位纳秒；必须按输入的单调顺序推进，不是累计的固定周期数。|

#### 返回说明

int。

#### 异常说明

原读取错。

源码：[`src/chronaxis/execution/record_value_history.py:124`](../../../src/chronaxis/execution/record_value_history.py#L124)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-rows"></a>
### `RecordValueHistory.rows`

只借出范围两侧及其中的记录，保留裁剪分母。

```python
RecordValueHistory.rows(start_ns, end_ns)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`start_ns`|int|是|无|位置或关键字。本次查询或计算的实际开始时刻，单位纳秒。|
|`end_ns`|int|是|无|位置或关键字。本次查询或计算的实际结束时刻，单位纳秒；按具体函数保留必要右端点供半开范围计算。|

#### 返回说明

迭代器。

#### 异常说明

原读取错。

源码：[`src/chronaxis/execution/record_value_history.py:135`](../../../src/chronaxis/execution/record_value_history.py#L135)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-closed"></a>
### `RecordValueHistory.closed`

返回自有资源关闭状态。

```python
RecordValueHistory.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool。

#### 异常说明

无。

源码：[`src/chronaxis/execution/record_value_history.py:148`](../../../src/chronaxis/execution/record_value_history.py#L148)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RecordValueHistory-close"></a>
### `RecordValueHistory.close`

关闭必要文件并退款，不碰原输入。

```python
RecordValueHistory.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错，可重试。

源码：[`src/chronaxis/execution/record_value_history.py:152`](../../../src/chronaxis/execution/record_value_history.py#L152)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
