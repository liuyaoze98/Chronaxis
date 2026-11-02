# chronaxis.sources.text_can_spec

冻结ASC/BLF连续来源或原始CSV到DBC信号的声明，不在构造时读取文件。

每个输入保留A/B已校验的解析配置，文件严格按声明顺序接续，不排序或猜测换日。
时间在各解析器中已变为纳秒；本层不再施加偏移。通用时基由调用方显式提供。
混合BLF复用python-can格式读取；既有纯BLF的LegacyCANSpec调用路径保持原样。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ASCSpec](chronaxis.sources.asc.md#api-ASCSpec)、[BLFSpec](chronaxis.sources.blf.md#api-BLFSpec)、[CANCSVSpec](chronaxis.sources.raw_csv.md#api-CANCSVSpec)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)

## 对象导航

|对象|用途|
|---|---|
|[`CANTextSpec`](#api-CANTextSpec)|同一来源的显式连续输入、单通道/DBC和已声明的共同时间基准。|
|[`CANTextSpec.__post_init__`](#api-CANTextSpec-__post_init__)|核声明与支持范围。|
|[`CANTextSpec.source_type`](#api-CANTextSpec-source_type)|区分原始来源。返回can_asc、asc_or_blf或raw_can_csv，不发生I/O。|
|[`CANTextSpec.offset_ns`](#api-CANTextSpec-offset_ns)|说明本层不再移动解析后时间。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from pathlib import Path
from ..core.models import TimebaseSpec
from ..core.validation import require_identifier
from .asc import ASCSpec
from .raw_csv import CANCSVSpec
from .blf import BLFSpec
```

</details>

<a id="api-CANTextSpec"></a>
## `CANTextSpec`

同一来源的显式连续输入、单通道/DBC和已声明的共同时间基准。

```python
class CANTextSpec
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|来源安全名称，不是DBC消息名。|
|`inputs`|tuple[[ASCSpec](chronaxis.sources.asc.md#api-ASCSpec) &#124; [CANCSVSpec](chronaxis.sources.raw_csv.md#api-CANCSVSpec) &#124; [BLFSpec](chronaxis.sources.blf.md#api-BLFSpec), ...]|是|无|ASC/BLF可混合；CSV需统一布局。|
|`dbc_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|单次只读加载的DBC，不在构造时核存在性。|
|`channel`|int|是|无|0基目标信号通道；其他通道原帧仍向导出层交付。|
|`timebase`|[TimebaseSpec](chronaxis.core.models.md#api-TimebaseSpec)|是|无|相同ID本身不证明物理同步。|
|`decode_policy`|str|否|'legacy'|旧文本失败停止；新strict/partial解码失败置无效继续。|
|`input_check`|str|否|'auto'|auto按任务所需的时间序列检查；full要求完整来源顺序。普通ASC/混合来源的auto只核所需通道/ID顺序，全部已解析帧在同次读取中用于来源最早/最晚范围；原帧导出仍要求完整顺序。不是解码范围或输出开关。|

源码：[`src/chronaxis/sources/text_can_spec.py:18`](../../../src/chronaxis/sources/text_can_spec.py#L18)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANTextSpec-__post_init__"></a>
### `CANTextSpec.__post_init__`

核声明与支持范围。

```python
CANTextSpec.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

名称/类型/文件集合或时基不合法。

本函数直接报告的具体错误：

- `ValueError`：文本CAN需要1到4096个同格式解析声明。
- `TypeError`：文本CAN需要DBC Path及TimebaseSpec。
- `ValueError`：文本CAN通道需要非负原生整数。

源码：[`src/chronaxis/sources/text_can_spec.py:30`](../../../src/chronaxis/sources/text_can_spec.py#L30)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANTextSpec-source_type"></a>
### `CANTextSpec.source_type`

区分原始来源。返回can_asc、asc_or_blf或raw_can_csv，不发生I/O。

```python
CANTextSpec.source_type
```

装饰器：`property`。

读取属性，不使用调用括号。


源码：[`src/chronaxis/sources/text_can_spec.py:50`](../../../src/chronaxis/sources/text_can_spec.py#L50)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANTextSpec-offset_ns"></a>
### `CANTextSpec.offset_ns`

说明本层不再移动解析后时间。

```python
CANTextSpec.offset_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

0。

#### 异常说明

无。

源码：[`src/chronaxis/sources/text_can_spec.py:58`](../../../src/chronaxis/sources/text_can_spec.py#L58)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
