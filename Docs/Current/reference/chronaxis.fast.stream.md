# `chronaxis.fast.stream`

流式读取单文件并产出当前帧贡献，不维护跨帧信号或最终累计。

输入为已编译声明和DBC；输出(time_ns, 原记录序号, 计算项贡献tuple)。
只保存当前帧，文件关闭后才提供最终计数。父会话负责顺序和结果发布。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)

## 对象导航

|对象|用途|
|---|---|
|[`FileContributions`](#api-FileContributions)|持有一个读取器和有限公式组；同帧仅解码一次，计数按计算项隔离。|
|[`FileContributions.__init__`](#api-FileContributions-__init__)|打开单文件。|
|[`FileContributions._measured`](#api-FileContributions-_measured)|仅诊断运行计量解析迭代。|
|[`FileContributions._selected_time`](#api-FileContributions-_selected_time)|确定ASC精确时间检查集合。|
|[`FileContributions.__iter__`](#api-FileContributions-__iter__)|返回自身。|
|[`FileContributions.__next__`](#api-FileContributions-__next__)|跳过无关帧并返回一条目标贡献。|
|[`FileContributions.summary`](#api-FileContributions-summary)|取得关闭后的文件事实。|
|[`FileContributions.close`](#api-FileContributions-close)|释放读取器。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from time import perf_counter
from ..legacy.decode_policy import check_decode_length
from ..timebase.conversion import convert_time, checked_add_ns
from .can_io import _prepare, _UNSUPPORTED_FD
```

</details>

<a id="api-FileContributions"></a>
## `FileContributions`

持有一个读取器和有限公式组；同帧仅解码一次，计数按计算项隔离。

```python
FileContributions(spec, database, cancel=None, budget=None)
```


源码：[`src/chronaxis/fast/stream.py:16`](../../../src/chronaxis/fast/stream.py#L16)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FileContributions-__init__"></a>
### `FileContributions.__init__`

打开单文件。

```python
FileContributions.__init__(spec, database, cancel=None, budget=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。本次已编译会话或单文件声明，包含来源、公式、顺序和执行资源；调用过程不改写它。|
|`database`|cantools.database.Database|是|无|位置或关键字。已加载的DBC定义，可在本进程复用；省略时由会话加载，不能与冻结声明冲突。|
|`cancel`|Event &#124; None|否|None|位置或关键字。调用方取消事件；is_set为真时停止继续读取或调度，None表示没有外部取消信号。|
|`budget`|[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)|否|None|位置或关键字。本次会话共享的受管理资源用量记录；先预约空间，再构造缓冲或暂存。|

#### 返回说明

迭代器。

#### 异常说明

配置、文件或DBC错误；构造失败不遗留读取器。

源码：[`src/chronaxis/fast/stream.py:19`](../../../src/chronaxis/fast/stream.py#L19)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FileContributions-_measured"></a>
### `FileContributions._measured`

仅诊断运行计量解析迭代。

```python
FileContributions._measured(iterator)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`iterator`|Iterator|是|无|位置或关键字。底层ASC/BLF原始记录迭代器；诊断包装只计量每次读取，不修改记录。|

#### 返回说明

原记录生成器。

#### 异常说明

原错误。
正式执行不使用此包装，避免每条原始报文计时开销。

源码：[`src/chronaxis/fast/stream.py:59`](../../../src/chronaxis/fast/stream.py#L59)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FileContributions-_selected_time"></a>
### `FileContributions._selected_time`

确定ASC精确时间检查集合。

```python
FileContributions._selected_time(frame)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`frame`|can.Message|是|无|位置或关键字。当前原始CAN帧，用通道、ID和实际帧型判断是否需要时间顺序检查。|

#### 返回说明

bool。

#### 异常说明

无。
范围过滤前选择，零贡献和方向不影响集合；无时间消费者不加强检查。

源码：[`src/chronaxis/fast/stream.py:73`](../../../src/chronaxis/fast/stream.py#L73)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FileContributions-__iter__"></a>
### `FileContributions.__iter__`

返回自身。

```python
FileContributions.__iter__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

当前迭代器。

#### 异常说明

无。

源码：[`src/chronaxis/fast/stream.py:81`](../../../src/chronaxis/fast/stream.py#L81)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FileContributions-__next__"></a>
### `FileContributions.__next__`

跳过无关帧并返回一条目标贡献。

```python
FileContributions.__next__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

时间/序号/贡献元组。

#### 异常说明

解析、时间、解码、公式错误或取消；EOF在读取资源成功关闭后抛出。

源码：[`src/chronaxis/fast/stream.py:85`](../../../src/chronaxis/fast/stream.py#L85)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FileContributions-summary"></a>
### `FileContributions.summary`

取得关闭后的文件事实。

```python
FileContributions.summary()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

有限dict。

#### 异常说明

未成功EOF时拒绝。

源码：[`src/chronaxis/fast/stream.py:152`](../../../src/chronaxis/fast/stream.py#L152)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-FileContributions-close"></a>
### `FileContributions.close`

释放读取器。

```python
FileContributions.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

原关闭错误，不伪造完成。

源码：[`src/chronaxis/fast/stream.py:159`](../../../src/chronaxis/fast/stream.py#L159)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
