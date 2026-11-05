# `chronaxis.legacy.disjunction`

按当前报文中的方向信号，把一次计算的贡献值分到正向或负向组。它保存原方向值和来源位置，便于核对分组原因；分组本身不对贡献值取绝对值或改变公式符号。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[SourceRef](chronaxis.core.models.md#api-SourceRef)

## 对象导航

|对象|用途|
|---|---|
|[`LegacyDisjunction`](#api-LegacyDisjunction)|选择同条消息的原数值方向桶，不修改表达式贡献的正负号。|
|[`LegacyDisjunction.__post_init__`](#api-LegacyDisjunction-__post_init__)|校验安全别名和固定桶/取值策略，不解析来源或输入值。|
|[`LegacyDisjunctionTrace`](#api-LegacyDisjunctionTrace)|保存本次方向的原定位和值，结构冻结但不假造真实读取证明。|
|[`LegacyDisjunctionTrace.__post_init__`](#api-LegacyDisjunctionTrace-__post_init__)|核选择器、原字段、原生值及引用一致性，不作数值强制转换。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.models import SourceRef
from ..core.validation import require_identifier, require_text
```

</details>

<a id="api-LegacyDisjunction"></a>
## `LegacyDisjunction`

选择同条消息的原数值方向桶，不修改表达式贡献的正负号。

signal是分析别名，原字段和完整消息定位仍由当前绑定解析；bucket仅接受
positive/negative。该声明不自行拆分指标，也不证明方向在表达式依赖中。

```python
class LegacyDisjunction
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`signal`|str|是|无|已绑定简单别名，可不出现在表达式中。|
|`bucket`|str|是|无|`"positive"`选择方向原值大于0的报文；`"negative"`选择小于0的报文。方向为0不进入任何一组，公式结果保留原符号。|
|`value_policy`|str|否|'raw_decoded-v1'|填`"raw_decoded-v1"`：根据当前报文刚解码出的原始方向值分组，不先应用scale、offset或方向转换，也不使用前一次报文的值。|

源码：[`src/chronaxis/legacy/disjunction.py:23`](../../../src/chronaxis/legacy/disjunction.py#L23)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyDisjunction-__post_init__"></a>
### `LegacyDisjunction.__post_init__`

校验安全别名和固定桶/取值策略，不解析来源或输入值。

```python
LegacyDisjunction.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取三个创建后不可修改的字段。

#### 返回说明

None，保原生文本原样。

#### 异常说明

TypeError为非原生文本；ValueError为别名、桶或策略不支持。

本函数直接报告的具体错误：

- `TypeError`：disjunction别名、桶和value_policy需要原生str。
- `ValueError`：disjunction.bucket仅支持positive或negative。
- `ValueError`：disjunction.value_policy仅支持raw_decoded-v1。

返回类型：None。

源码：[`src/chronaxis/legacy/disjunction.py:34`](../../../src/chronaxis/legacy/disjunction.py#L34)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyDisjunctionTrace"></a>
## `LegacyDisjunctionTrace`

保存本次方向的原定位和值，结构冻结但不假造真实读取证明。

raw_value保int/float/bool原类型，None只表示明确缺字段；非有限float不在
模型层改写或拒绝。source_ref原对象保持，实际CAN逐序身份由运行/结果层核。

```python
class LegacyDisjunctionTrace
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`selection`|[LegacyDisjunction](chronaxis.legacy.disjunction.md#api-LegacyDisjunction)|是|无|实际指标使用的同一选择器。|
|`field`|str|是|无|原SignalDefinition.field；CAN绑定包含channel、frame_id、signal及已指定的可选帧型，不包含报文名称。|
|`raw_value`|int &#124; float &#124; bool &#124; None|是|无|未归一化方向值；None为缺失。|
|`source_ref`|[SourceRef](chronaxis.core.models.md#api-SourceRef)|是|无|同条原消息的真实来源引用。|

源码：[`src/chronaxis/legacy/disjunction.py:51`](../../../src/chronaxis/legacy/disjunction.py#L51)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-LegacyDisjunctionTrace-__post_init__"></a>
### `LegacyDisjunctionTrace.__post_init__`

核选择器、原字段、原生值及引用一致性，不作数值强制转换。

```python
LegacyDisjunctionTrace.__post_init__() -> None
```

参数：无显式参数。


#### 参数说明

无，读取冻结追溯字段。

#### 返回说明

None；保NaN/Inf、负零和原bool。

#### 异常说明

TypeError为非模型/原生数值；ValueError为原字段与引用不一致。

本函数直接报告的具体错误：

- `TypeError`：disjunction追溯需要LegacyDisjunction及原生field文本。
- `TypeError`：disjunction原值需要原生int/float/bool或明确缺失None。
- `TypeError`：disjunction追溯需要SourceRef。
- `ValueError`：disjunction原field与来源引用不一致。

返回类型：None。

源码：[`src/chronaxis/legacy/disjunction.py:63`](../../../src/chronaxis/legacy/disjunction.py#L63)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
