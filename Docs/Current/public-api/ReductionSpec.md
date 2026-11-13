# chronaxis.extensions.ReductionSpec

`from chronaxis.extensions import ReductionSpec`

<a id="api-ReductionSpec"></a>
## `ReductionSpec`

声明对真实样本归约的工厂factory(resources)。每个统计范围独立创建状态。

```python
ReductionSpec(name: str, version: str, input: chronaxis.extensions.ValueSpec, output: chronaxis.extensions.ValueSpec, reference: object = None, numpy: object = None, state_bytes: int = 0, mergeable: bool = False) -> None
```

|名称|类型|必填|默认值|用途|
|---|---|---|---|---|
|`name`|str|是|无默认值|在本次注册中唯一、且不与内置操作重名的表达式标识符。|
|`version`|str|是|无默认值|非空的实现版本；实现行为变化时由宿主递增。|
|`input`|chronaxis.extensions.ValueSpec|是|无默认值|一个ValueSpec端口，声明数值dtype与已登记单位；不接受BOOL或ENUM。|
|`output`|chronaxis.extensions.ValueSpec|是|无默认值|输出ValueSpec端口；声明回调结果的dtype与单位。|
|`reference`|object|否|None|状态工厂`factory(resources)`，每个统计范围创建一个对象。对象必须提供consume(values)、finalize()、cancel()和close()；values是有效ScalarValue元组，finalize返回符合output的ScalarValue。mergeable=True还须merge(other)。None表示不支持reference，两个后端至少提供一个。|
|`numpy`|object|否|None|状态工厂`factory(resources)`，必需方法与reference相同；consume(values)接收有效NumericArray，finalize()仍返回ScalarValue。None表示不支持numpy，不自动使用reference工厂。|
|`state_bytes`|int|否|0|状态预留费用，非负整数，单位byte；宿主按实际状态需求声明。|
|`mergeable`|bool|否|False|True要求状态实现merge(other)，False不承诺可合并。|

### 返回

不可变ReductionSpec声明。

### 异常

非法端口、后端、state_bytes或mergeable抛ValueError/TypeError；输入与输出均须为数值。

### 执行与资源

状态consume接收选定真实样本，finalize返回ScalarValue；cancel和close均为必需方法，分别处理取消与资源释放。mergeable=True须实现merge(other)。

端口通过`from chronaxis.extensions import ValueSpec`与`from chronaxis.core.types import SignalDType`声明。例如`ValueSpec(SignalDType.FLOAT64, "A")`表示浮点电流端口。

### `require_backend`

```python
ReductionSpec.require_backend(backend)
```

继承的公开方法：必填backend只能为reference或numpy。返回对应已登记回调或工厂；未知后端或缺少该后端实现抛ValueError。

[完整宿主示例](../host-extensions.md)

源码：[`src/chronaxis/extensions.py:92`](../../../src/chronaxis/extensions.py#L92)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
