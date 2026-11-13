# chronaxis.extensions.ExtensionRegistry

`from chronaxis.extensions import ExtensionRegistry`

<a id="api-ExtensionRegistry"></a>
## `ExtensionRegistry`

构造不可变宿主扩展注册表；创建计划与执行计划须传同一个注册实例。配置只引用已注册名称，不自动导入Python模块。

```python
ExtensionRegistry(functions=(), reductions=(), transforms=())
```

|名称|类型|必填|默认值|用途|
|---|---|---|---|---|
|`functions`|tuple[FunctionSpec, ...]|否|()|FunctionSpec元组；省略为空，表示没有自定义逐点函数。|
|`reductions`|tuple[ReductionSpec, ...]|否|()|ReductionSpec元组；省略为空，表示没有自定义样本归约。|
|`transforms`|tuple[TransformSpec, ...]|否|()|TransformSpec元组；省略为空，表示没有自定义时序变换。|

### 返回

新ExtensionRegistry。functions/reductions/transforms为只读名称映射；identity是声明及实现版本的摘要。

### 异常

容器不是tuple或条目类型错误时抛TypeError；三类之间名称重复时抛ValueError。

### 执行与资源

只登记声明，不执行回调或创建运行状态；同次运行不能替换注册表。

[完整宿主示例](../host-extensions.md)

源码：[`src/chronaxis/extensions.py:147`](../../../src/chronaxis/extensions.py#L147)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

源码：[`src/chronaxis/extensions.py:154`](../../../src/chronaxis/extensions.py#L154)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
