# chronaxis.core.windows_reference

独立用Python精确整数扩展、合并并裁剪事件窗口，输出完整片段事实。

输入已排序真实Event、WindowSpec和观测Interval，输出Segment tuple。
先按onset/点锚点扩展请求，再按明确政策分组，最后裁剪并计算覆盖。
single按真实活动间隔判断，pre重叠不扩大分组；相等deadline重入合并。
本实现不调用NumPy数值，只共享协议与元数据包装，不读写旧日志或重写事件。
输入和输出均完整保存在内存中，调用方负责资源预算。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Interval](chronaxis.core.models.md#api-Interval)

## 对象导航

|对象|用途|
|---|---|
|[`build_segments_reference`](#api-build_segments_reference)|根据真实事件构造请求窗口及其实际观测交集。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from ..timebase.conversion import checked_add_ns
from .models import Interval
from .windows import require_windows, make_segment, require_resolved_windows
```

</details>

<a id="api-build_segments_reference"></a>
## `build_segments_reference`

根据真实事件构造请求窗口及其实际观测交集。

```python
build_segments_reference(events, spec, observation, *, bounds=None, compact=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`events`|tuple[Event, ...]|是|无|位置或关键字。events为已排序Event tuple|
|`spec`|WindowSpec|是|无|位置或关键字。spec为WindowSpec|
|`observation`|[Interval](chronaxis.core.models.md#api-Interval)|是|无|位置或关键字。observation为真实半开范围。|
|`bounds`|tuple[tuple[int, int, bool, bool], ...] &#124; None|否|None|仅关键字。与事件同长的实际窗口边界，每项为起点、终点、左裁剪标志、右裁剪标志；None按原实际时长展开。|
|`compact`|bool|否|False|仅关键字。选择返回的窗口模型：True生成CompactSegment，保留实际区间、父事件ID、状态和质量；False生成含请求范围、覆盖等详细信息的Segment。默认False；这不改变输入事件。|

### 返回说明

Segment或compact的CompactSegment tuple；bounds为按所选周期解析的真实边界。空事件返回空tuple。

### 异常说明

模型、排序、归属错误传播；请求端点或跨度溢出明确拒绝。

### 流程说明

逐事件精确扩展，按none/重叠/相邻/真实退出间隔分组，逐组裁剪。
    不改变原Event，不增加旧writer调用，不凭EOF外的请求补观测。

源码：[`src/chronaxis/core/windows_reference.py:17`](../../../src/chronaxis/core/windows_reference.py#L17)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
