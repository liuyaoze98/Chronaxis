# chronaxis.execution.record_diagnostics

仅在请求追溯或完整性诊断时观察同次输入，不增加来源扫描。

trace逐条保存所需输入值和来源序号；integrity随这些记录计算摘要，两者独立。
来源配置只在清单保存一次。借入值在调用结束释放，固定哈希状态按来源付费；
最终明细使用已有结果仓的有界外排和生命周期，不建立第二份历史。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[InputDiagnostic](chronaxis.results.input_diagnostics.md#api-InputDiagnostic)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)

## 对象导航

|对象|用途|
|---|---|
|[`RecordDiagnostics`](#api-RecordDiagnostics)|保存每来源一个计数及可选摘要；逐条明细同步交给最终结果消费者。|
|[`RecordDiagnostics.__init__`](#api-RecordDiagnostics-__init__)|预约实际来源状态。|
|[`RecordDiagnostics.consume`](#api-RecordDiagnostics-consume)|借入必要输入，按请求追溯/取摘要。|
|[`RecordDiagnostics.summaries`](#api-RecordDiagnostics-summaries)|仅EOF后交付有限来源清单。|
|[`RecordDiagnostics.close`](#api-RecordDiagnostics-close)|断开哈希/回调后归还本owner费用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from math import isfinite
from ..results.input_diagnostics import InputDiagnostic
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from .history import _metadata_bytes
```

</details>

<a id="api-RecordDiagnostics"></a>
## `RecordDiagnostics`

保存每来源一个计数及可选摘要；逐条明细同步交给最终结果消费者。

```python
RecordDiagnostics(plan, requirements, budget, consumer)
```


源码：[`src/chronaxis/execution/record_diagnostics.py:16`](../../../src/chronaxis/execution/record_diagnostics.py#L16)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDiagnostics-__init__"></a>
### `RecordDiagnostics.__init__`

预约实际来源状态。

```python
RecordDiagnostics.__init__(plan, requirements, budget, consumer)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|AnalysisPlan|是|无|位置或关键字。已完成静态解析的分析计划，包含来源、绑定、规则、指标、间隔选择和输出要求。|
|`requirements`|InputRequirements &#124; SourceInputRequirements|是|无|位置或关键字。需求分析所得的当前任务或单来源输入范围，用来跳过没有消费者的值、时间和历史。|
|`budget`|ResourceBudget|是|无|位置或关键字。本次分析共享的资源用量记录；新对象先预约所需内存和磁盘额度，关闭时归还自己的内存费用。|
|`consumer`|Callable &#124; None|是|无|位置或关键字。追溯行接收函数，参数依次为来源、原序号、实际时间、种类、定位、值JSON及质量；None不生成追溯行。|

#### 返回说明

owner。

#### 异常说明

预算错误。

源码：[`src/chronaxis/execution/record_diagnostics.py:18`](../../../src/chronaxis/execution/record_diagnostics.py#L18)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDiagnostics-consume"></a>
### `RecordDiagnostics.consume`

借入必要输入，按请求追溯/取摘要。

```python
RecordDiagnostics.consume(source, sequence, time_ns, record_type, locator, values, quality)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|位置或关键字。当前结果或记录所属的来源名称，必须对应计划中已经定义的source。|
|`sequence`|int|是|无|位置或关键字。当前记录的非负顺序号；同一时刻记录仍有独立序号，不能当作时间戳。|
|`time_ns`|int &#124; None|是|无|位置或关键字。当前记录的实际纳秒时刻；仅明确不需要采集时间的输入诊断可为None。|
|`record_type`|str|是|无|位置或关键字。输入记录种类：decoded_message表示所需报文解码值，signal_sample表示普通信号值，signal_clock表示只保留更新时间的记录。|
|`locator`|str|是|无|位置或关键字。当前报文或字段的非空定位文本，配合来源和原记录序号定位所需输入。|
|`values`|Mapping[str, int &#124; float &#124; bool &#124; str &#124; None]|是|无|位置或关键字。当前所需字段到解码值的映射；缺失保留无效，不复制无关字段。|
|`quality`|QualityFlag|是|无|位置或关键字。该值或结果的质量位组合；缺失、过期等原因不能通过清零掩盖。|

#### 返回说明

None。

#### 异常说明

编码/预算/取消。

源码：[`src/chronaxis/execution/record_diagnostics.py:43`](../../../src/chronaxis/execution/record_diagnostics.py#L43)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDiagnostics-summaries"></a>
### `RecordDiagnostics.summaries`

仅EOF后交付有限来源清单。

```python
RecordDiagnostics.summaries(cursors)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`cursors`|Sequence[RecordSourceCursor]|是|无|位置或关键字。本次实际打开的来源游标，借用其真实首末时刻和EOF状态；调用方保留关闭责任。|

#### 返回说明

InputDiagnostic tuple。

#### 异常说明

不完整来源。

源码：[`src/chronaxis/execution/record_diagnostics.py:65`](../../../src/chronaxis/execution/record_diagnostics.py#L65)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-RecordDiagnostics-close"></a>
### `RecordDiagnostics.close`

断开哈希/回调后归还本owner费用。

```python
RecordDiagnostics.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

预算释放错误。

源码：[`src/chronaxis/execution/record_diagnostics.py:81`](../../../src/chronaxis/execution/record_diagnostics.py#L81)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
