# chronaxis.results.readable

将结果流关联成可直接阅读的CSV，不重新读取或计算输入。

事件、窗口及计算的既有排序不同，先用临时SQLite索引关联，再逐行发布。
索引只有本次结果，固定缓存、禁止mmap、写前预付页面；关闭后删除，不发布
原表副本。CSV、JSONL旧路径不调用本模块。所有权保存在AnalysisResult供失败恢复。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`_json`](#api-_json)|编码临时索引值。|
|[`ReadableWriter`](#api-ReadableWriter)|拥有单次发布的关联索引及有限列定义；close可重试，不拥有输入或正式结果。|
|[`ReadableWriter.__init__`](#api-ReadableWriter-__init__)|仅安装可恢复字段，资源在prepare取得。|
|[`ReadableWriter._execute`](#api-ReadableWriter-_execute)|写前预留SQLite页面，上限由数据库本身强制执行。|
|[`ReadableWriter._rows`](#api-ReadableWriter-_rows)|按原游标逐条读已计算结果，保持严格解析和真实关闭。|
|[`ReadableWriter.prepare`](#api-ReadableWriter-prepare)|建立必要关联和列定义，不读取原始日志。|
|[`ReadableWriter._number`](#api-ReadableWriter-_number)|将完整父ID映射为本次表编号，缺失关系直接报错。|
|[`ReadableWriter._metric_columns`](#api-ReadableWriter-_metric_columns)|创建已付预算的有限指标列。|
|[`ReadableWriter._metric_values`](#api-ReadableWriter-_metric_values)|按同一完整身份取指标，未产生的指标不伪装为完整或零。|
|[`ReadableWriter._base`](#api-ReadableWriter-_base)|形成业务列，保留事件/窗口/配对不同含义。|
|[`ReadableWriter._write`](#api-ReadableWriter-_write)|直接写最终CSV并随写计算可选摘要，不写后回读。|
|[`ReadableWriter.write`](#api-ReadableWriter-write)|发布全部关联主表；明细由后续专门分支逐条处理。|
|[`ReadableWriter._detail_rows`](#api-ReadableWriter-_detail_rows)|直接输出请求的明细，保留未知、值类型及必要定位。|
|[`ReadableWriter._main_rows`](#api-ReadableWriter-_main_rows)|按索引顺序产生一行，查询不在RAM排序全表。|
|[`ReadableWriter.presentation`](#api-ReadableWriter-presentation)|仅返回共同身份和必要使用说明，不增加ID映射副本。|
|[`ReadableWriter.close`](#api-ReadableWriter-close)|关闭并删除本次索引，失败保留真实owner供重试。|
|[`_with_header`](#api-_with_header)|逐条提供表头及内容。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from contextlib import closing
from math import ceil
from .budget import _reserve_owned_ram, _release_owned_ram
from .errors import ResultFormatError
from .summary import summary_fields
from .readable_format import STATES, REASONS, seconds, explanation, quality_text
```

</details>

<a id="api-_json"></a>
## `_json`

编码临时索引值。

```python
_json(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict|是|无|位置或关键字。已校验的平坦字段，用于有限JSON编码。|

### 返回说明

JSON文本。

### 异常说明

非有限值拒绝。

源码：[`src/chronaxis/results/readable.py:27`](../../../src/chronaxis/results/readable.py#L27)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter"></a>
## `ReadableWriter`

拥有单次发布的关联索引及有限列定义；close可重试，不拥有输入或正式结果。

```python
ReadableWriter(owner, directory, iterator_factory)
```


源码：[`src/chronaxis/results/readable.py:32`](../../../src/chronaxis/results/readable.py#L32)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-__init__"></a>
### `ReadableWriter.__init__`

仅安装可恢复字段，资源在prepare取得。

```python
ReadableWriter.__init__(owner, directory, iterator_factory)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|AnalysisResult|是|无|位置或关键字。本次已封口结果；提供预算、请求的表和真实关闭责任。|
|`directory`|Path|是|无|位置或关键字。本次发布临时目录，不是输入或最终已有目录。|
|`iterator_factory`|Callable|是|无|位置或关键字。构造已校验结果行游标的内部工厂，游标必须关闭。|

#### 返回说明

未准备的writer。

#### 异常说明

无文件副作用。

源码：[`src/chronaxis/results/readable.py:35`](../../../src/chronaxis/results/readable.py#L35)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-_execute"></a>
### `ReadableWriter._execute`

写前预留SQLite页面，上限由数据库本身强制执行。

```python
ReadableWriter._execute(sql, values=(), size=0)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`sql`|str|是|无|位置或关键字。内部固定SQL语句，不拼接用户业务值。|
|`values`|tuple|否|()|位置或关键字。绑定到SQL占位符的标量参数。|
|`size`|int|否|0|位置或关键字。当前索引JSON的字符数，用于写前估算磁盘页上限。|

#### 返回说明

cursor。

#### 异常说明

配额、SQL、IO或取消传播。预留包含B树分裂余量，不按总行数预占RAM。

源码：[`src/chronaxis/results/readable.py:54`](../../../src/chronaxis/results/readable.py#L54)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-_rows"></a>
### `ReadableWriter._rows`

按原游标逐条读已计算结果，保持严格解析和真实关闭。

```python
ReadableWriter._rows(table)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。本次已启用的结果表名称。|

#### 返回说明

平坦字段生成器。

#### 异常说明

读取/校验/关闭错误传播。

源码：[`src/chronaxis/results/readable.py:69`](../../../src/chronaxis/results/readable.py#L69)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-prepare"></a>
### `ReadableWriter.prepare`

建立必要关联和列定义，不读取原始日志。

```python
ReadableWriter.prepare()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

重复身份、重复指标、配额/IO传播。

源码：[`src/chronaxis/results/readable.py:92`](../../../src/chronaxis/results/readable.py#L92)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-_number"></a>
### `ReadableWriter._number`

将完整父ID映射为本次表编号，缺失关系直接报错。

```python
ReadableWriter._number(kind, row, identifier)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`kind`|str|是|无|位置或关键字。父对象表：events或segments。|
|`row`|dict|是|无|位置或关键字。已校验的单条平坦结果，包含完整关联身份。|
|`identifier`|str &#124; None|是|无|位置或关键字。完整父ID；None表示该关系没有响应或不适用。|

#### 返回说明

编号或空字符串。

#### 异常说明

ResultFormatError为悬空父关联。

源码：[`src/chronaxis/results/readable.py:156`](../../../src/chronaxis/results/readable.py#L156)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-_metric_columns"></a>
### `ReadableWriter._metric_columns`

创建已付预算的有限指标列。

```python
ReadableWriter._metric_columns(scope)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`scope`|str|是|无|位置或关键字。指标范围：session、event或segment。|

#### 返回说明

列名列表。

#### 异常说明

无。

源码：[`src/chronaxis/results/readable.py:172`](../../../src/chronaxis/results/readable.py#L172)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-_metric_values"></a>
### `ReadableWriter._metric_values`

按同一完整身份取指标，未产生的指标不伪装为完整或零。

```python
ReadableWriter._metric_values(scope, row, parent)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`scope`|str|是|无|位置或关键字。指标范围：session、event或segment。|
|`row`|dict|是|无|位置或关键字。已校验的单条平坦结果，包含完整关联身份。|
|`parent`|str &#124; None|是|无|位置或关键字。该范围完整父ID；会话使用空值。|

#### 返回说明

有限单行列表。

#### 异常说明

关联/JSON错误传播。

源码：[`src/chronaxis/results/readable.py:180`](../../../src/chronaxis/results/readable.py#L180)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-_base"></a>
### `ReadableWriter._base`

形成业务列，保留事件/窗口/配对不同含义。

```python
ReadableWriter._base(table, row, number)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。本次已启用的结果表名称。|
|`row`|dict|是|无|位置或关键字。已校验的单条平坦结果，包含完整关联身份。|
|`number`|int|是|无|位置或关键字。本次可读表内从1开始的稳定编号。|

#### 返回说明

单行列表。

#### 异常说明

悬空关联传播。

源码：[`src/chronaxis/results/readable.py:197`](../../../src/chronaxis/results/readable.py#L197)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-_write"></a>
### `ReadableWriter._write`

直接写最终CSV并随写计算可选摘要，不写后回读。

```python
ReadableWriter._write(table, columns, rows)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。本次已启用的结果表名称。|
|`columns`|list[str]|是|无|位置或关键字。本次CSV的有限表头列名。|
|`rows`|Iterable[list]|是|无|位置或关键字。逐条提供的CSV单元格，不收集整张表。|

#### 返回说明

路径。

#### 异常说明

编码、IO或取消传播。

源码：[`src/chronaxis/results/readable.py:218`](../../../src/chronaxis/results/readable.py#L218)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-write"></a>
### `ReadableWriter.write`

发布全部关联主表；明细由后续专门分支逐条处理。

```python
ReadableWriter.write(quality_handle=None, coverage=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`quality_handle`|TextIO &#124; None|否|None|位置或关键字。仅显式详细诊断时提供的质量记录流，默认None不生成。|
|`coverage`|dict &#124; None|否|None|位置或关键字。显式诊断使用的有限状态计数；默认None。|

#### 返回说明

路径tuple。

#### 异常说明

关联/预算/IO错误传播。

源码：[`src/chronaxis/results/readable.py:256`](../../../src/chronaxis/results/readable.py#L256)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-_detail_rows"></a>
### `ReadableWriter._detail_rows`

直接输出请求的明细，保留未知、值类型及必要定位。

```python
ReadableWriter._detail_rows(table)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。本次已启用的结果表名称。|

#### 返回说明

有界CSV行。

#### 异常说明

缺失父对象或原读取错误。

源码：[`src/chronaxis/results/readable.py:292`](../../../src/chronaxis/results/readable.py#L292)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-_main_rows"></a>
### `ReadableWriter._main_rows`

按索引顺序产生一行，查询不在RAM排序全表。

```python
ReadableWriter._main_rows(table)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`table`|str|是|无|位置或关键字。本次已启用的结果表名称。|

#### 返回说明

CSV行生成器。

#### 异常说明

JSON/关联错误。

源码：[`src/chronaxis/results/readable.py:314`](../../../src/chronaxis/results/readable.py#L314)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-presentation"></a>
### `ReadableWriter.presentation`

仅返回共同身份和必要使用说明，不增加ID映射副本。

```python
ReadableWriter.presentation()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

清单字典。

#### 异常说明

无。

源码：[`src/chronaxis/results/readable.py:326`](../../../src/chronaxis/results/readable.py#L326)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-ReadableWriter-close"></a>
### `ReadableWriter.close`

关闭并删除本次索引，失败保留真实owner供重试。

```python
ReadableWriter.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

IO/释放错误传播，不删除输入或其他文件。

源码：[`src/chronaxis/results/readable.py:336`](../../../src/chronaxis/results/readable.py#L336)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_with_header"></a>
## `_with_header`

逐条提供表头及内容。

```python
_with_header(columns, rows)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`columns`|list[str]|是|无|位置或关键字。本次CSV的有限表头列名。|
|`rows`|Iterable[list]|是|无|位置或关键字。逐条提供的CSV单元格，不收集整张表。|

### 返回说明

生成器。

### 异常说明

原流错误传播。

源码：[`src/chronaxis/results/readable.py:352`](../../../src/chronaxis/results/readable.py#L352)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
