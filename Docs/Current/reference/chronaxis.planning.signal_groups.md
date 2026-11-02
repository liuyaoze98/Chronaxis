# chronaxis.planning.signal_groups

把同一报文的集中声明展开为既有信号绑定，不增加运行时分组或重复读取。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`signal_entries`](#api-signal_entries)|按原顺序提供信号副本和声明路径。|
|[`declared_signals`](#api-declared_signals)|遍历原声明的叶信号供默认展开使用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .checks import array_at, object_at, choice_at, text_at, model_at, PlanValidationError
```

</details>

<a id="api-signal_entries"></a>
## `signal_entries`

按原顺序提供信号副本和声明路径。

```python
signal_entries(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list|是|无|位置或关键字。signals数组，普通绑定与报文组均可；按原顺序产生独立叶信号及原声明位置。|

### 返回说明

迭代器。

### 异常说明

结构错误。

集中项仅接受声明一套报文定位；子项可覆盖周期、有效期和同一时刻策略，
不能把另一个报文塞进本组。没有额外组名、引用或运行时对象。

源码：[`src/chronaxis/planning/signal_groups.py:9`](../../../src/chronaxis/planning/signal_groups.py#L9)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-declared_signals"></a>
## `declared_signals`

遍历原声明的叶信号供默认展开使用。

```python
declared_signals(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list|是|无|位置或关键字。已经校验的signals数组，遍历原叶字典，供默认配置展开。|

### 返回说明

原字典迭代器。

### 异常说明

无。

源码：[`src/chronaxis/planning/signal_groups.py:55`](../../../src/chronaxis/planning/signal_groups.py#L55)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
