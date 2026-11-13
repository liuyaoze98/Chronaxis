# `chronaxis.core.lookup_compiler`

将 v4 lookup 的固定签名和表名引用编译为单输入节点。

输入只接受表达式 AST 和当前有身份的绑定。先校验关键字、单位与类型，
随后准备引用表的只读列；不访问其他配置或数据来源。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[D](chronaxis.core.types.md#api-SignalDType)

## 对象导航

|对象|用途|
|---|---|
|[`compile_lookup`](#api-compile_lookup)|编译查表调用。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from .expression import _node
from .types import SignalDType as D
from .unit_registry import output_label, resolve_unit
```

</details>

<a id="api-compile_lookup"></a>
## `compile_lookup`

编译查表调用。

```python
compile_lookup(compiler, node)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`compiler`|UnitCompiler|是|无|位置或关键字。负责解析输入表达式及表的物理单位、输出类型的本次编译器。|
|`node`|ast.Call|是|无|位置或关键字。原始 lookup 调用节点，其位置参数和关键字选择表名、模式及越界政策。|

### 返回说明

有单位的节点。

### 异常说明

签名、表名、类型或单位错。

源码：[`src/chronaxis/core/lookup_compiler.py:14`](../../../src/chronaxis/core/lookup_compiler.py#L14)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
