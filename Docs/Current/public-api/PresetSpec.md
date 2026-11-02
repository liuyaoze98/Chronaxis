# chronaxis.PresetSpec

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.planning.preset_models.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [PresetSpec](#api-PresetSpec)
- [PresetSpec.from_dict](#api-PresetSpec-from_dict)

<a id="api-PresetSpec"></a>
## `PresetSpec`

冻结预设ID、preset_type/version、角色别名及工程参数的独立JSON快照。

id只用简单标识；role_bindings值只引用当前计划简单别名，不能写领域属性路径。
parameters不保留调用者可变对象，实际preset_type参数在build_preset中统一校验。

```python
PresetSpec(id: str, preset_type: str, version: str, role_bindings: collections.abc.Mapping, parameters: collections.abc.Mapping) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`id`|str|是|无|设置本预设实例唯一名称，例如hot；生成规则和计算使用此前缀，须避免与已有节点重名。|
|`preset_type`|str|是|无|选择任务：charge_session分析充电，fault_context提取故障前后文，command_response配对请求响应，threshold_excursion累计阈值报警。各类型的角色和参数见预设指南。|
|`version`|str|是|无|选择预设模板版本，当前填写字符串"1"；不是整数1，也不是顶层config_version。|
|`role_bindings`|Mapping|是|无|将业务角色关联到signals中已定义的分析名，例如{"signal": "temperature"}。允许角色由preset_type决定；省略角色时须符合语义声明自动查找要求。|
|`parameters`|Mapping|是|无|提供所选预设的业务参数字典，例如阈值预设的unit、enter_threshold、exit_threshold。值来自业务阈值和设备单位；各类型字段不能互相套用，完整选项见预设指南。|

源码：[`src/chronaxis/planning/preset_models.py:52`](../../../src/chronaxis/planning/preset_models.py#L52)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-PresetSpec-from_dict"></a>
### `PresetSpec.from_dict`

从当前配置的预设对象构造公开不可变声明。

```python
PresetSpec.from_dict(value)
```

装饰器：`classmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, object]|是|无|位置或关键字。预设配置字典：name、preset_type和parameters必填；version省略为字符串1，role_bindings省略为空映射。角色映射与业务约束见[业务预设](../presets.md)。|

#### 返回说明

PresetSpec，role_bindings缺省为空。

#### 异常说明

PlanValidationError为未知键、缺项或构造协议错误。

#### 调用示例

```python
from chronaxis import PresetSpec

# 构造预设声明；绑定和阈值的完整语义在组装计划时继续检查。
spec = PresetSpec.from_dict({
    "name": "heat_alarm",
    "preset_type": "threshold_excursion",
    "version": "1",
    "role_bindings": {"signal": "temperature"},
    "parameters": {"unit": "degC", "enter_threshold": 80, "exit_threshold": 75},
})
print(spec.id, spec.preset_type)

```

源码：[`src/chronaxis/planning/preset_models.py:90`](../../../src/chronaxis/planning/preset_models.py#L90)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
