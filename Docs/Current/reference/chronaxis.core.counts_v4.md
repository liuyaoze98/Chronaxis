# `chronaxis.core.counts_v4`

定义v4计数结果及对象发现的完整性，不保存事件或原始样本。

样本计数沿用既有真实更新与选择政策，对象计数只计指定规则或窗口在本会话
最终产生的对象。计数保留整数；有证据的空集、发现不完整及没有观测分别报告。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[QualityFlag（源码别名Q）](chronaxis.core.types.md#api-QualityFlag)

## 对象导航

|对象|用途|
|---|---|
|[`classify_count`](#api-classify_count)|由已知计数及范围证据决定整数结果、状态、原因与额外质量。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .types import QualityFlag as Q
```

</details>

<a id="api-classify_count"></a>
## `classify_count`

由已知计数及范围证据决定整数结果、状态、原因与额外质量。

```python
classify_count(count, policy, *, observed, determinate, complete)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`count`|int|是|无|位置或关键字。本次已实际发现的目标对象数。非负整数超出 uint64 时报告溢出。|
|`policy`|str|是|无|位置或关键字。对象发现有缺口时采用的政策，report 可给出已知数，strict 隐去部分值。|
|`observed`|bool|是|无|仅关键字。请求范围是否存在有关来源的观测。无观测时返回空值并给出 no_observation。|
|`determinate`|bool|是|无|仅关键字。请求范围中是否有能够确定对象存在或不存在的时段；全未知时不能断言计数为零。|
|`complete`|bool|是|无|仅关键字。证据是否足以判断整个请求范围。发现完整且计数为零时，返回完整的没有数据满足筛选条件。|

### 返回说明

(value,status,reason,quality)，完全未知为None。

### 异常说明

ValueError为计数或数据不全时的处理方式不合法。

源码：[`src/chronaxis/core/counts_v4.py:14`](../../../src/chronaxis/core/counts_v4.py#L14)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
