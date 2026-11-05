# `chronaxis.results.threshold_metadata`

保存一次阈值报警预设在实际观测范围内的时长汇总。

输入是同次迟滞状态机累计的整数纳秒，不再次读取信号或推算缺口内状态。
有未知时间时只报告已知报警累计，完整总时长为空；无观测不返回正常零。
快照只随有限预设数增长，由结果清单预算承担，重复发布不会重新计算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)

## 对象导航

|对象|用途|
|---|---|
|[`ThresholdDurationMetadata`](#api-ThresholdDurationMetadata)|冻结报警、已知与未知时长，完整总数只在整个观测范围已知时给出。|
|[`ThresholdDurationMetadata.__post_init__`](#api-ThresholdDurationMetadata-__post_init__)|检查固定计数和观测范围的一致性。|
|[`ThresholdDurationMetadata.observed_duration_ns`](#api-ThresholdDurationMetadata-observed_duration_ns)|取得实际半开范围长度。|
|[`ThresholdDurationMetadata.unknown_duration_ns`](#api-ThresholdDurationMetadata-unknown_duration_ns)|取得未确定报警状态的时长。|
|[`ThresholdDurationMetadata.total_duration_ns`](#api-ThresholdDurationMetadata-total_duration_ns)|完整总时长不能由未知区间推测。|
|[`ThresholdDurationMetadata.status`](#api-ThresholdDurationMetadata-status)|区分完整、部分、全未知和无观测。|
|[`ThresholdDurationMetadata.to_dict`](#api-ThresholdDurationMetadata-to_dict)|把记录的纳秒时长及换算后的秒数写入清单，便于程序处理和人工阅读。|
|[`SummaryThresholdDuration`](#api-SummaryThresholdDuration)|新合同只保存一个累计值和单位；partial说明它只是已知部分。|
|[`SummaryThresholdDuration.__post_init__`](#api-SummaryThresholdDuration-__post_init__)|检查唯一单位和未知总量。|
|[`SummaryThresholdDuration.to_dict`](#api-SummaryThresholdDuration-to_dict)|发布一种数值单位，不附重复ns/s或时间范围。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from math import isfinite
from ..core.models import Interval
from ..core.validation import require_identifier
```

</details>

<a id="api-ThresholdDurationMetadata"></a>
## `ThresholdDurationMetadata`

冻结报警、已知与未知时长，完整总数只在整个观测范围已知时给出。

```python
class ThresholdDurationMetadata
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`preset_id`|str|是|无|本次计划的预设ID。|
|`rule_id`|str|是|无|实际生成的迟滞规则ID，可关联事件表。|
|`observed_start_ns`|int &#124; None|是|无|实际时钟组起点，无观测为None。|
|`observed_end_ns`|int &#124; None|是|无|实际时钟组末点，不向请求末端外推。|
|`known_active_duration_ns`|int|是|无|已知报警区间的准确整数纳秒和。|
|`known_duration_ns`|int|是|无|已知报警或未报警的总纳秒。|

源码：[`src/chronaxis/results/threshold_metadata.py:15`](../../../src/chronaxis/results/threshold_metadata.py#L15)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ThresholdDurationMetadata-__post_init__"></a>
### `ThresholdDurationMetadata.__post_init__`

检查固定计数和观测范围的一致性。

```python
ThresholdDurationMetadata.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

TypeError/ValueError为身份、范围或计数矛盾。

本函数直接报告的具体错误：

- `ValueError`：阈值汇总观测端点必须同时存在或同时为空。
- `TypeError`：阈值汇总时长须原生整数纳秒。
- `ValueError`：报警/已知时长不得超过实际观测范围。
- `TypeError`：阈值汇总端点须原生整数纳秒。

源码：[`src/chronaxis/results/threshold_metadata.py:25`](../../../src/chronaxis/results/threshold_metadata.py#L25)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ThresholdDurationMetadata-observed_duration_ns"></a>
### `ThresholdDurationMetadata.observed_duration_ns`

取得实际半开范围长度。

```python
ThresholdDurationMetadata.observed_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/results/threshold_metadata.py:44`](../../../src/chronaxis/results/threshold_metadata.py#L44)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ThresholdDurationMetadata-unknown_duration_ns"></a>
### `ThresholdDurationMetadata.unknown_duration_ns`

取得未确定报警状态的时长。

```python
ThresholdDurationMetadata.unknown_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int纳秒。

#### 异常说明

无。

源码：[`src/chronaxis/results/threshold_metadata.py:49`](../../../src/chronaxis/results/threshold_metadata.py#L49)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ThresholdDurationMetadata-total_duration_ns"></a>
### `ThresholdDurationMetadata.total_duration_ns`

完整总时长不能由未知区间推测。

```python
ThresholdDurationMetadata.total_duration_ns
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

int或None。

#### 异常说明

无。

源码：[`src/chronaxis/results/threshold_metadata.py:54`](../../../src/chronaxis/results/threshold_metadata.py#L54)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ThresholdDurationMetadata-status"></a>
### `ThresholdDurationMetadata.status`

区分完整、部分、全未知和无观测。

```python
ThresholdDurationMetadata.status
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

状态文本。

#### 异常说明

无。

源码：[`src/chronaxis/results/threshold_metadata.py:59`](../../../src/chronaxis/results/threshold_metadata.py#L59)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-ThresholdDurationMetadata-to_dict"></a>
### `ThresholdDurationMetadata.to_dict`

把记录的纳秒时长及换算后的秒数写入清单，便于程序处理和人工阅读。

```python
ThresholdDurationMetadata.to_dict()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

独立dict。

#### 异常说明

无；调用方在复制前预付元数据费用。

源码：[`src/chronaxis/results/threshold_metadata.py:67`](../../../src/chronaxis/results/threshold_metadata.py#L67)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SummaryThresholdDuration"></a>
## `SummaryThresholdDuration`

新合同只保存一个累计值和单位；partial说明它只是已知部分。

```python
class SummaryThresholdDuration
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`preset_id`|str|是|无|读取产生摘要的presets[].id。|
|`rule_id`|str|是|无|读取该阈值预设生成的活动规则ID。|
|`value`|float &#124; None|是|无|读取累计报警秒数。complete是完整累计，partial只累计可确定的部分；indeterminate和no_observation时为None。|
|`status`|str|是|无|读取可用性：complete为全程可判断；partial为部分时段未知但有已知部分；indeterminate为有观测但状态全未知；no_observation为没有可统计时段。|
|`unit`|str|否|'s'|读取数值单位，固定为s；value不使用纳秒，也不能填写W或J。|

源码：[`src/chronaxis/results/threshold_metadata.py:82`](../../../src/chronaxis/results/threshold_metadata.py#L82)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SummaryThresholdDuration-__post_init__"></a>
### `SummaryThresholdDuration.__post_init__`

检查唯一单位和未知总量。

```python
SummaryThresholdDuration.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

非法身份/数值/状态。

源码：[`src/chronaxis/results/threshold_metadata.py:91`](../../../src/chronaxis/results/threshold_metadata.py#L91)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-SummaryThresholdDuration-to_dict"></a>
### `SummaryThresholdDuration.to_dict`

发布一种数值单位，不附重复ns/s或时间范围。

```python
SummaryThresholdDuration.to_dict()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

dict。

#### 异常说明

无。

源码：[`src/chronaxis/results/threshold_metadata.py:102`](../../../src/chronaxis/results/threshold_metadata.py#L102)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
