# `chronaxis.legacy.sum_numpy`

用NumPy按输入顺序累计一块逐消息贡献值，保留与旧逐次加法相同的先后关系。它不改变每条消息的公式，也不把数据重新排序后求和。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`sum_numpy`](#api-sum_numpy)|从已有carry按原顺序一次生成整列前缀累计并核查所有中间值。|

<a id="api-sum_numpy"></a>
## `sum_numpy`

从已有carry按原顺序一次生成整列前缀累计并核查所有中间值。

```python
sum_numpy(carry: float, values: tuple[float, ...]) -> float
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`carry`|float|是|无|位置或关键字。carry为有限原生float|
|`values`|tuple[float, ...]|是|无|位置或关键字。values为按原序选出的有限原生float tuple，     本函数由预算owner在完成贡献结构与顺序校验后调用。|

### 返回说明

float；无贡献时原carry不变，有贡献时取最后前缀，保持原浮点尾数。

### 异常说明

OverflowError为任何中间累计非有限；NumPy分配、导入或取消原样传播。
    本核不提交累计器状态，费用及异常恢复由调用方管理。

本函数直接报告的具体错误：

- `OverflowError`：legacy_sum中间累计非有限，整批拒绝。

返回类型：float。

源码：[`src/chronaxis/legacy/sum_numpy.py:17`](../../../src/chronaxis/legacy/sum_numpy.py#L17)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
