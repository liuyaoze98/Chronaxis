# chronaxis.extensions.TransformSpec

`from chronaxis.extensions import TransformSpec`

<a id="api-TransformSpec"></a>
## `TransformSpec`

声明有状态网格变换工厂factory(resources)，advance(time_ns, window_ns, values, weights_ns)计算窗口值。

```python
TransformSpec(name: str, version: str, input: chronaxis.extensions.ValueSpec, output: chronaxis.extensions.ValueSpec, reference: object = None, numpy: object = None, state_bytes: int = 0, history_ns: int = 0, interval_modes: tuple[str, ...] = ('actual', 'fixed', 'dbc')) -> None
```

|名称|类型|必填|默认值|用途|
|---|---|---|---|---|
|`name`|str|是|无默认值|在本次注册中唯一、且不与内置操作重名的表达式标识符。|
|`version`|str|是|无默认值|非空的实现版本；实现行为变化时由宿主递增。|
|`input`|chronaxis.extensions.ValueSpec|是|无默认值|一个ValueSpec端口，声明数值dtype与已登记单位；不接受BOOL或ENUM。|
|`output`|chronaxis.extensions.ValueSpec|是|无默认值|输出ValueSpec端口；声明回调结果的dtype与单位。|
|`reference`|object|否|None|状态工厂`factory(resources)`，每会话创建对象，必须提供advance(time_ns, window_ns, values, weights_ns)、cancel()、close()。advance接收实际输出时刻、窗口计量宽度、有效ScalarValue元组及对应时长权重，返回符合output的ScalarValue；时间数值单位ns。None表示不支持reference，两个后端至少提供一个。|
|`numpy`|object|否|None|状态工厂`factory(resources)`，必需方法与reference相同；advance中的values为有效NumericArray，weights_ns为对应时长数组，返回ScalarValue。None表示不支持numpy，不自动使用reference工厂。|
|`state_bytes`|int|否|0|状态预留费用，非负整数，单位byte；宿主按实际状态需求声明。|
|`history_ns`|int|否|0|必须显式填写正int64回看宽度；单位ns，按所选实际或周期口径计量。默认0不是有效声明。|
|`interval_modes`|tuple[str, ...]|否|('actual', 'fixed', 'dbc')|本实现支持的actual/fixed/dbc非空、无重复元组；不要声明尚未正确实现的权重口径。|

### 返回

不可变TransformSpec声明。

### 异常

非法端口、资源、历史宽度、重复或未知interval_modes抛ValueError/TypeError。输入与输出均须为数值。

### 执行与资源

每会话创建状态，advance仅接收有效ZOH区间及权重，返回网格时刻ScalarValue；按所声明历史及状态费用使用共享预算，关闭时释放资源。

端口通过`from chronaxis.extensions import ValueSpec`与`from chronaxis.core.types import SignalDType`声明。例如`ValueSpec(SignalDType.FLOAT64, "A")`表示浮点电流端口。

### `require_backend`

```python
TransformSpec.require_backend(backend)
```

继承的公开方法：必填backend只能为reference或numpy。返回对应已登记回调或工厂；未知后端或缺少该后端实现抛ValueError。

[完整宿主示例](../host-extensions.md)

源码：[`src/chronaxis/extensions.py:117`](../../../src/chronaxis/extensions.py#L117)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
