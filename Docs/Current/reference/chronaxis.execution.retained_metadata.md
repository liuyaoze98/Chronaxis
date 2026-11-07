# `chronaxis.execution.retained_metadata`

估算一个指标结果继续留在内存中需要多少字节。这个值用于申请资源额度，与把结果转成JSON时使用的临时内存分开计算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ResultFormatError](chronaxis.results.errors.md#api-ResultFormatError)

## 对象导航

|对象|用途|
|---|---|
|[`retained_metadata_bytes`](#api-retained_metadata_bytes)|核算冻结对象实体及其字段，不把共享引用解释成深复制。|
|[`reference_workspace`](#api-reference_workspace)|预付去重期间新list及返回tuple的指针空间，不重复支付旧ref实体。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from sys import getsizeof
from ..results.errors import ResultFormatError
```

</details>

<a id="api-retained_metadata_bytes"></a>
## `retained_metadata_bytes`

核算冻结对象实体及其字段，不把共享引用解释成深复制。

```python
retained_metadata_bytes(value, depth=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。用于估算内存的元数据树，包含已登记模型、元组和原生标量；逐层计算对象及字段大小，不读取信号样本文件。|
|`depth`|int|否|0|位置或关键字。depth为内部深度计数。|

### 返回说明

保守整数bytes，重复引用也独立计数，不需要无界身份集合。

### 异常说明

ResultFormatError为超过32层或含未支持可变/数组类型。

本函数直接报告的具体错误：

- `ResultFormatError`：保留元数据类型无法估算。
- `ResultFormatError`：保留元数据超过32层。

源码：[`src/chronaxis/execution/retained_metadata.py:23`](../../../src/chronaxis/execution/retained_metadata.py#L23)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-reference_workspace"></a>
## `reference_workspace`

预付去重期间新list及返回tuple的指针空间，不重复支付旧ref实体。

```python
reference_workspace(existing_count, incoming_count)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`existing_count`|int|是|无|位置或关键字。当前已经保留的来源引用个数，非负原生整数。|
|`incoming_count`|int|是|无|位置或关键字。本批将加入的来源引用个数，非负原生整数。|

### 返回说明

保守bytes。

### 异常说明

无主动异常；内部调用者保证非负原生int。

源码：[`src/chronaxis/execution/retained_metadata.py:63`](../../../src/chronaxis/execution/retained_metadata.py#L63)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
