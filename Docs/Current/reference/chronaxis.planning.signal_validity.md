# `chronaxis.planning.signal_validity`

确定信号的有效期声明，不读取DBC或日志。

显式valid_for优先；否则使用本信号period的三倍。原始报文未填period时
保留None，执行启动再从本次已有DBC元数据取得周期。已解码数据不能借用
别的信号或计算驱动的周期。所有数值以正int64纳秒表示，无I/O或全局缓存。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`triple_period`](#api-triple_period)|将当前信号周期乘3，检查有效期仍在int64纳秒范围内。|
|[`declared_valid_for`](#api-declared_valid_for)|在不读取DBC的情况下选择显式有效期、固定周期默认值或待解析状态。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .checks import PlanValidationError, duration_at
from ..timebase.conversion import require_int64_ns
```

</details>

<a id="api-triple_period"></a>
## `triple_period`

将当前信号周期乘3，检查有效期仍在int64纳秒范围内。

```python
triple_period(period_ns, path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`period_ns`|int|是|无|位置或关键字。本信号的正整数纳秒周期，不接受bool。|
|`path`|str|是|无|位置或关键字。配置错误位置，用于明确指出哪一个信号的有效期无法得到。|

### 返回说明

正整数纳秒有效期。

### 异常说明

PlanValidationError：周期非法或乘3后溢出。

### 副作用说明

无，不读取文件。

源码：[`src/chronaxis/planning/signal_validity.py:12`](../../../src/chronaxis/planning/signal_validity.py#L12)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-declared_valid_for"></a>
## `declared_valid_for`

在不读取DBC的情况下选择显式有效期、固定周期默认值或待解析状态。

```python
declared_valid_for(raw, path, *, dbc_available)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`raw`|dict|是|无|位置或关键字。单信号配置；valid_for明确填写时优先，period为可选正时长字符串。|
|`path`|str|是|无|位置或关键字。该信号在配置中的字段路径。|
|`dbc_available`|bool|是|无|仅关键字。来源是否为可使用DBC的原始报文；False且缺少period/valid_for时拒绝。|

### 返回说明

正整数纳秒；只有等待DBC时返回None。

### 异常说明

PlanValidationError：空值、非法时长、无周期依据或默认有效期溢出。

### 副作用说明

无；validate/explain不会因此打开DBC。

源码：[`src/chronaxis/planning/signal_validity.py:28`](../../../src/chronaxis/planning/signal_validity.py#L28)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
