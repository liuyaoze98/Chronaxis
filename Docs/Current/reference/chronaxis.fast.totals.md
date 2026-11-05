# `chronaxis.fast.totals`

按独立文件模板的声明顺序汇总同一业务指标。只在请求 --total 时使用。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_semantics`](#api-_semantics)|比较业务绑定、计算指令、时间范围及解码选项。单文件路径和展示格式可不同。|
|[`FastTotals`](#api-FastTotals)|在开始读文件前冻结可求和的指标，以及这些指标应当来自哪些任务。|
|[`FastTotals.from_specs`](#api-FastTotals-from_specs)|specs 为按模板输入顺序排列的 job_id→fast 声明。返回只读求和计划。|
|[`FastTotals.finish`](#api-FastTotals-finish)|按计算项和方向桶分别求和。失败/取消/未运行任务须显式写为 None。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from pathlib import Path
```

</details>

<a id="api-_semantics"></a>
## `_semantics`

比较业务绑定、计算指令、时间范围及解码选项。单文件路径和展示格式可不同。

```python
_semantics(spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。一个文件的已绑定参数，包括 DBC、通道、数值公式和输出单位。|

源码：[`src/chronaxis/fast/totals.py:9`](../../../src/chronaxis/fast/totals.py#L9)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-FastTotals"></a>
## `FastTotals`

在开始读文件前冻结可求和的指标，以及这些指标应当来自哪些任务。

```python
class FastTotals
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`members`|tuple[str, ...]|是|无|按模板声明顺序固定的成员任务名，决定跨文件求和顺序。|
|`metrics`|tuple[tuple[str, str], ...]|是|无|需要在全部成员中逐项核对的计算项名和单位。|

源码：[`src/chronaxis/fast/totals.py:17`](../../../src/chronaxis/fast/totals.py#L17)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-FastTotals-from_specs"></a>
### `FastTotals.from_specs`

specs 为按模板输入顺序排列的 job_id→fast 声明。返回只读求和计划。

只接受同模板、可核实相同绑定和累计口径的不同文件。失败发生在任务分派前。

```python
FastTotals.from_specs(specs, *, template)
```

装饰器：`classmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`specs`|dict|是|无|位置或关键字。按任务名保存的执行参数，用于核验绑定、DBC 和计算口径。|
|`template`|bool|是|无|仅关键字。本批是否来自同一个显式分析模板，决定能否请求固定总量。|

源码：[`src/chronaxis/fast/totals.py:24`](../../../src/chronaxis/fast/totals.py#L24)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-FastTotals-finish"></a>
### `FastTotals.finish`

按计算项和方向桶分别求和。失败/取消/未运行任务须显式写为 None。

outcomes 的正常值是 worker 返回的未舍入行。成员或行不符合计划属于协议错误。
数值缺失导致该项总计不可用。有限加数之和溢出时抛出 OverflowError。

```python
FastTotals.finish(outcomes)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`outcomes`|dict|是|无|位置或关键字。成员任务映射到未舍入结果行；取消、失败或未运行记为空。|

源码：[`src/chronaxis/fast/totals.py:48`](../../../src/chronaxis/fast/totals.py#L48)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
