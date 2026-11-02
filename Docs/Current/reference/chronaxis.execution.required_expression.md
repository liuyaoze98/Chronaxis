# chronaxis.execution.required_expression

在真实部分投影上编译结果需要的表达式，保留完整静态声明检查。

输入是原 StaticExpression、真实 DecodedBindings 和全部派生定义；输出身份
与公开 compile_expression 一致的 CompiledExpression。先在声明绑定上重新
检查所有派生，再核对原静态对象；真实绑定只解析当前根递归需要的派生，不把
未用派生变成要求输入投影的运行根。公共编译和静态校验入口保持原行为。
本模块不读取数据、不求值、不持有长期缓存。调用阶段须先为完整声明树、编译
临时对象及身份材料预付费用；失败时清理本层借用引用，原异常交给阶段处理。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[CompiledExpression](chronaxis.core.expression.md#api-CompiledExpression)、[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)、[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)、[_Compiler](chronaxis.core.expression.md#api-_Compiler)

## 对象导航

|对象|用途|
|---|---|
|[`compile_required_expression`](#api-compile_required_expression)|完整核实静态声明，再按本结果根建立真实输入表达式。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from hashlib import sha256
from ..core.decoded_binding import DecodedBindings
from ..core.expression import CompiledExpression, StaticExpression, _Compiler, _identity, validate_expression
```

</details>

<a id="api-compile_required_expression"></a>
## `compile_required_expression`

完整核实静态声明，再按本结果根建立真实输入表达式。

```python
compile_required_expression(static, bindings, *, derived=(), unit=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`static`|[StaticExpression](chronaxis.core.expression.md#api-StaticExpression)|是|无|位置或关键字。原 StaticExpression；bindings: 当前实际 DecodedBindings。|
|`bindings`|[DecodedBindings](chronaxis.core.decoded_binding.md#api-DecodedBindings)|是|无|位置或关键字。bindings: 当前实际 DecodedBindings。     derived: 与绑定名称空间一致的完整 DerivedDefinition tuple。     unit: 原表达式的显式单位，省略时使用原编译器推导，不做输出换算。|
|`derived`|tuple[DerivedDefinition, ...]|否|()|仅关键字。与绑定名称空间一致的完整 DerivedDefinition tuple。|
|`unit`|str &#124; None|否|None|仅关键字。原表达式的显式单位，省略时使用原编译器推导，不做输出换算。|

### 返回说明

CompiledExpression。身份公式、依赖、类型和单位沿用公开编译规则。

### 异常说明

TypeError 为对象域不符；ValueError 为静态内容被替换、未知名称、
    循环、类型/单位或实际依赖未投影；取消和内存错误原样传播。

### 边界说明

未使用派生仍接受语法和单位检查，但不要求其原字段已读取。当前根需要
    的字段必须有真实投影证明。预算由调用阶段在本函数执行前承担。

源码：[`src/chronaxis/execution/required_expression.py:18`](../../../src/chronaxis/execution/required_expression.py#L18)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
