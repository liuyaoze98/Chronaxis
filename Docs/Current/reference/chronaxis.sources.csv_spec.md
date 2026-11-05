# `chronaxis.sources.csv_spec`

声明独立已解码信号表的格式，并保存每个CSV样本的位置。

SignalCSVSpec接收有序路径、时间列、时间单位、时区、编码、分隔符和
缺失标记，输出创建后不可修改的配置；构造仅检查声明，不打开文件或根据后缀猜格式。
CSVSourceRef在通用来源引用上增加文件路径、记录末物理行和原始单元格
文本，供实际读取后追溯。时间量化诊断单独保留，不从文件名推断观测范围。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 继承字段

- `CSVSourceRef`同时继承[SourceRef](chronaxis.core.models.md#api-SourceRef)字段：`session_id`, `source_name`, `field`。构造时须一并提供基类的必填字段；类型、默认值及约束按基类表。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[SourceRef](chronaxis.core.models.md#api-SourceRef)、[TimeType](chronaxis.core.types.md#api-TimeType)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

## 对象导航

|对象|用途|
|---|---|
|[`SignalCSVSpec`](#api-SignalCSVSpec)|保存已解码信号表的格式和时钟声明，保留paths的给定顺序。|
|[`SignalCSVSpec.__post_init__`](#api-SignalCSVSpec-__post_init__)|检查表格格式与时间声明，保持路径和缺失标记的原顺序。|
|[`CSVSourceRef`](#api-CSVSourceRef)|保留单个已读取样本的文件位置和原始文本。|
|[`CSVSourceRef.__post_init__`](#api-CSVSourceRef-__post_init__)|检查继承的来源身份和CSV附加定位，不访问路径。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from datetime import tzinfo
from pathlib import Path
from ..core.models import SourceRef, TimebaseSpec
from ..core.types import TimeType
from ..core.validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-SignalCSVSpec"></a>
## `SignalCSVSpec`

保存已解码信号表的格式和时钟声明，保留paths的给定顺序。

name标识来源，paths指定连续输入文件；timebase给出相对公共起点或绝对
时钟，time_column与unit解释时间单元格，offset_ns是显式纳秒偏移。
timezone只用于缺少自身时区的绝对日期。encoding、sep和missing_values
明确表格解析规则；声明检查不会核实文件存在性或实际表头。

实际适配器把每行每个请求列当作一次观测。缺失文本精确匹配后转None，
表示明确缺失更新；旧Filter输出中的空白未更新含义须另按旧来源契约接入。

```python
class SignalCSVSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|当前计划来源名。|
|`paths`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), ...]|是|无|明确连续文件顺序，不扫描目录自动排序。|
|`timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|relative公共起点/absolute明确声明。|
|`time_column`|str|是|无|原时间列名，必须在每个表头存在。|
|`unit`|str|是|无|s/ms/us/ns或absolute的ISO8601。|
|`offset_ns`|int|否|0|显式固定偏移，不能证明同步。|
|`timezone`|tzinfo &#124; None|否|None|ISO无offset时明确采用的时区。 None表示没有补充时区；ISO文本自身也不含时区时会报错，不采用电脑时区。|
|`encoding`|str|否|'utf-8'|不猜文件编码。|
|`delimiter`|str|否|','|单字符分隔符，不自动sniff。|
|`missing_values`|tuple[str, ...]|否|('',)|精确匹配原cell，不strip标记。|

源码：[`src/chronaxis/sources/csv_spec.py:28`](../../../src/chronaxis/sources/csv_spec.py#L28)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SignalCSVSpec-__post_init__"></a>
### `SignalCSVSpec.__post_init__`

检查表格格式与时间声明，保持路径和缺失标记的原顺序。

```python
SignalCSVSpec.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。使用name、paths、timebase、time_column、unit、offset_ns、
    timezone、encoding、sep和missing_values字段。

#### 返回说明

None。只检查冻结实例，不读取表头或数据。

#### 异常说明

TypeError: 路径、时区或声明结构类型错误。
    ValueError: 时间单位、名称、分隔符或缺失标记不合法。
    LookupError: 编码名称不受本机编码注册表支持。
    OverflowError: offset_ns超出整数纳秒范围。

返回类型：None。

源码：[`src/chronaxis/sources/csv_spec.py:51`](../../../src/chronaxis/sources/csv_spec.py#L51)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CSVSourceRef"></a>
## `CSVSourceRef`

保留单个已读取样本的文件位置和原始文本。

继承的session_id、source_name和field确定会话、来源及原字段。
path指出文件，line_number是CSV记录结束的物理行，time_text和value_text
保留原单元格文本；time_quantized标记时间是否发生纳秒量化。
引用不保存sequence，稳定原行序号由SignalSeries的sequence列另行保存。
引号内跨多行的记录以最后物理行为位置，不能把它解释成记录首行。

```python
class CSVSourceRef(SourceRef)
```

继承关系：[SourceRef](chronaxis.core.models.md#api-SourceRef)。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|实际读取路径原文。|
|`line_number`|int|是|无|csv reader给出的记录末物理行，1开始。|
|`time_text`|str|是|无|原时间cell文本。|
|`value_text`|str|是|无|原字段cell文本，解析异常诊断不丢原文。|
|`time_quantized`|bool|是|无|时间转换曾按纳秒half-even量化。|

源码：[`src/chronaxis/sources/csv_spec.py:98`](../../../src/chronaxis/sources/csv_spec.py#L98)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-CSVSourceRef-__post_init__"></a>
### `CSVSourceRef.__post_init__`

检查继承的来源身份和CSV附加定位，不访问路径。

```python
CSVSourceRef.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无。读取来源身份、path、line_number、time_text、value_text和time_quantized。

#### 返回说明

None。文本保持原样，缺失单元格允许value_text为空字符串。

#### 异常说明

TypeError或ValueError: 来源名称、字段、路径、正整数行号或附加字段类型错误。

本函数直接报告的具体错误：

- `ValueError`：CSVSourceRef行号/文本/量化类型错误。

#### 副作用说明

无文件访问；引用构造本身不能证明path已经成功打开。

返回类型：None。

源码：[`src/chronaxis/sources/csv_spec.py:114`](../../../src/chronaxis/sources/csv_spec.py#L114)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
