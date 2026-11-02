# chronaxis.core.windows_numpy

独立用NumPy扩展、分组和裁剪事件窗口，再恢复片段模型。

输入已排序Event tuple、WindowSpec和实际观测Interval，输出Segment tuple。
时间端点为(N,) int64纳秒列，先检查扩展溢出，再执行UFUNC；按真实活动间隔
或请求窗口重叠建立组边界，reduceat归约每组范围，数组裁剪并计算覆盖。
输出循环只打包模型/元数据，不逐事件执行参考数值；不调用参考窗口算法。
输入和数组完整物化，不读旧链、不写文件、不承诺整个AnalysisRunner的预算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)、[TimeOverflowError](chronaxis.timebase.conversion.md#api-TimeOverflowError)

## 对象导航

|对象|用途|
|---|---|
|[`build_segments_numpy`](#api-build_segments_numpy)|以数组计算请求与实际范围，输出保留原事件关联的片段。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..timebase.conversion import INT64_MIN, INT64_MAX, TimeOverflowError
from .models import Interval
from .windows import require_windows, make_segment, require_resolved_windows
```

</details>

<a id="api-build_segments_numpy"></a>
## `build_segments_numpy`

以数组计算请求与实际范围，输出保留原事件关联的片段。

```python
build_segments_numpy(events, spec, observation, *, bounds=None, compact=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`events`|tuple|是|无|位置或关键字。events已排序真实事件|
|`spec`|WindowSpec|是|无|位置或关键字。spec为WindowSpec|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。observation为真实Interval。|
|`bounds`|tuple[tuple[int, int, bool, bool], ...] &#124; None|否|None|仅关键字。与事件同长的实际窗口边界，每项为起点、终点、左裁剪标志、右裁剪标志；None按原实际时长展开。|
|`compact`|bool|否|False|仅关键字。选择返回的窗口模型：True生成CompactSegment，保留实际区间、父事件ID、状态和质量；False生成含请求范围、覆盖等详细信息的Segment。默认False；这不改变输入事件。|

### 返回说明

Segment或compact的CompactSegment tuple；bounds为已解析的实际边界。旧覆盖保持独立float64比值。

### 异常说明

配置/模型错误传播；端点或跨度溢出明确拒绝；分配失败不吞。

本函数直接报告的具体错误：

- `TimeOverflowError`：窗口请求扩展超出int64纳秒。

### 流程说明

扩展前校验int64上下界，批量建立连接掩码/组索引、归约、裁剪及覆盖。
    恢复Interval时校验请求跨度，再做安全整数差；不改变原事件。

源码：[`src/chronaxis/core/windows_numpy.py:18`](../../../src/chronaxis/core/windows_numpy.py#L18)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
