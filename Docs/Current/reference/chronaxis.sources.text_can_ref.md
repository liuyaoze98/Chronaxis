# chronaxis.sources.text_can_ref

保存新文本CAN样本的精确原行引用，供信号历史和结果白名单编码。

输入是已有规范CAN字段键和实际读取的文件/行/原时间，输出冻结SourceRef子类。
字段键仍区分通道、消息、信号、ID及帧型；本引用另外保留文件次序与文件内序号。
不打开文件、不解码、不将float秒当作精确时间，也不冒称冻结旧profile的输出。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 继承字段

- `CANTextSourceRef`同时继承[SourceRef](chronaxis.core.models.md#api-SourceRef)字段：`session_id`, `source_name`, `field`。构造时须一并提供基类的必填字段；类型、默认值及约束按基类表。

## 相关类型

[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`CANTextSourceRef`](#api-CANTextSourceRef)|定位一个实际文本记录中的信号；通用field保存完整规范CAN定位。|
|[`CANTextSourceRef.__post_init__`](#api-CANTextSourceRef-__post_init__)|核对冻结定位的结构。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.models import SourceRef
from ..core.validation import require_text
from .can_spec import can_field_from_key
```

</details>

<a id="api-CANTextSourceRef"></a>
## `CANTextSourceRef`

定位一个实际文本记录中的信号；通用field保存完整规范CAN定位。

```python
class CANTextSourceRef(SourceRef)
```

继承关系：[SourceRef](chronaxis.core.models.md#api-SourceRef)。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str|是|无|实际输入路径，保持读取声明，不做隐式resolve。|
|`parser_version`|str|是|无|ASC或原始CSV解析版本。|
|`line_number`|int &#124; None|是|无|文本物理行；BLF为None，以record_sequence定位。|
|`input_index`|int|是|无|显式文件列表中的0基位置。|
|`record_sequence`|int|是|无|文件内原记录序号，同一时刻不同帧不去重。|
|`yield_sequence`|int|是|无|本次连续文件读取的全局0基原帧序号。|
|`raw_time`|str &#124; None|是|无|文本原文字；BLF没有时间文字，不构造副本。|
|`time_quantized`|bool|是|无|源文字转纳秒时是否实际量化。|

源码：[`src/chronaxis/sources/text_can_ref.py:15`](../../../src/chronaxis/sources/text_can_ref.py#L15)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-CANTextSourceRef-__post_init__"></a>
### `CANTextSourceRef.__post_init__`

核对冻结定位的结构。

```python
CANTextSourceRef.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型/规范字段/位置非法。

本函数直接报告的具体错误：

- `TypeError`：文本CAN量化标志需要bool。

源码：[`src/chronaxis/sources/text_can_ref.py:27`](../../../src/chronaxis/sources/text_can_ref.py#L27)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
