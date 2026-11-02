# chronaxis.results.binding_metadata

在运行清单中记录使用了哪个预设版本，以及每个角色最终对应哪个信号。这里只保存已有选择，不重新读取来源或再次检查信号的业务含义。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`PresetRoleMetadata`](#api-PresetRoleMetadata)|保留角色选择和声明契约版本，字段冻结且不代表物理事实已验。|
|[`PresetRoleMetadata.__post_init__`](#api-PresetRoleMetadata-__post_init__)|检查记录字段的类型和内容；预设角色是否满足业务要求已由前面的解析步骤检查。|
|[`PresetBindingMetadata`](#api-PresetBindingMetadata)|按原计划顺序保存一个预设的版本和全部角色，角色不可重复。|
|[`PresetBindingMetadata.__post_init__`](#api-PresetBindingMetadata-__post_init__)|核快照及角色唯一性。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.validation import require_identifier, require_text
```

</details>

<a id="api-PresetRoleMetadata"></a>
## `PresetRoleMetadata`

保留角色选择和声明契约版本，字段冻结且不代表物理事实已验。

```python
class PresetRoleMetadata
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`role`|str|是|无|原预设角色。|
|`alias`|str|是|无|最终实际信号别名。|
|`resolution`|str|是|无|`"explicit"`表示用户通过role_bindings指定了信号；`"semantic_unique"`表示按semantic_id和角色要求恰好找到了一个符合要求的信号。|
|`contract_version`|str|是|无|实际检查的角色契约版本。|
|`contract_status`|str|否|'checked_against_declared_metadata'|校验的是给定声明。|

源码：[`src/chronaxis/results/binding_metadata.py:15`](../../../src/chronaxis/results/binding_metadata.py#L15)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PresetRoleMetadata-__post_init__"></a>
### `PresetRoleMetadata.__post_init__`

检查记录字段的类型和内容；预设角色是否满足业务要求已由前面的解析步骤检查。

```python
PresetRoleMetadata.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型或非法状态。

本函数直接报告的具体错误：

- `ValueError`：预设角色查找方式需explicit或semantic_unique。
- `ValueError`：预设角色状态只能说明已检查声明元数据。

源码：[`src/chronaxis/results/binding_metadata.py:24`](../../../src/chronaxis/results/binding_metadata.py#L24)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PresetBindingMetadata"></a>
## `PresetBindingMetadata`

按原计划顺序保存一个预设的版本和全部角色，角色不可重复。

```python
class PresetBindingMetadata
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`preset_id`|str|是|无|原预设ID。|
|`preset_type`|str|是|无|原预设种类，不从名称推断领域事实。|
|`version`|str|是|无|原预设版本，与角色契约版本独立。|
|`roles`|tuple[[PresetRoleMetadata](chronaxis.results.binding_metadata.md#api-PresetRoleMetadata), ...]|是|无|有限冻结记录，不含输入行。|

源码：[`src/chronaxis/results/binding_metadata.py:37`](../../../src/chronaxis/results/binding_metadata.py#L37)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-PresetBindingMetadata-__post_init__"></a>
### `PresetBindingMetadata.__post_init__`

核快照及角色唯一性。

```python
PresetBindingMetadata.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

类型、空身份或重复角色。

本函数直接报告的具体错误：

- `TypeError`：预设清单角色需冻结PresetRoleMetadata tuple。
- `ValueError`：预设清单不能重复同一角色。

源码：[`src/chronaxis/results/binding_metadata.py:45`](../../../src/chronaxis/results/binding_metadata.py#L45)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
