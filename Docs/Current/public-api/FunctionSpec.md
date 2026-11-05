# chronaxis.extensions.FunctionSpec

`from chronaxis.extensions import FunctionSpec`

<a id="api-FunctionSpec"></a>
## `FunctionSpec`

声明无历史的逐点函数，回调impl(args, resources)返回同形状ScalarValue或NumericArray。

```python
FunctionSpec(name: str, version: str, inputs: tuple[chronaxis.extensions.ValueSpec, ...], output: chronaxis.extensions.ValueSpec, reference: object = None, numpy: object = None) -> None
```

|名称|类型|必填|默认值|用途|
|---|---|---|---|---|
|`name`|str|是|无默认值|在本次注册中唯一、且不与内置操作重名的表达式标识符。|
|`version`|str|是|无默认值|非空的实现版本；实现行为变化时由宿主递增。|
|`inputs`|tuple[chronaxis.extensions.ValueSpec, ...]|是|无默认值|非空ValueSpec元组，按函数的位置参数顺序声明dtype与单位。BOOL端口单位为1，ENUM需先取编码。|
|`output`|chronaxis.extensions.ValueSpec|是|无默认值|输出ValueSpec端口；声明回调结果的dtype与单位。|
|`reference`|object|否|None|逐点实现`impl(args, resources)`。args按inputs声明顺序提供ScalarValue元组，返回一个符合output的ScalarValue；resources用于申请/释放临时内存。None表示不支持此后端；两个后端至少提供一个，不自动回退。|
|`numpy`|object|否|None|数组逐点实现`impl(args, resources)`。args是按inputs排列的NumericArray元组，返回同长度、符合output的NumericArray；只接收到全部必要输入有效的行。None表示不支持numpy，不以reference替代。|

### 返回

不可变FunctionSpec声明。

### 异常

名称、端口、版本或回调声明不合法时拒绝构造；ValueError或TypeError保留具体原因。

### 执行与资源

必要输入无效时传播无效；未选where分支不执行。注册只检查声明，不调用计算实现。

端口通过`from chronaxis.extensions import ValueSpec`与`from chronaxis.core.types import SignalDType`声明。例如`ValueSpec(SignalDType.FLOAT64, "A")`表示浮点电流端口。

### `require_backend`

```python
FunctionSpec.require_backend(backend)
```

继承的公开方法：必填backend只能为reference或numpy。返回对应已登记回调或工厂；未知后端或缺少该后端实现抛ValueError。

[完整宿主示例](../host-extensions.md)

源码：[`src/chronaxis/extensions.py:73`](../../../src/chronaxis/extensions.py#L73)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
