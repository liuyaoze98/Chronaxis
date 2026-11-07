# `chronaxis.execution.signal_validity`

从本次已经加载的DBC元数据补全必要信号的有效期。

仅处理尚未确定valid_for的信号，在读取首帧前按所属报文周期乘三。
不加载DBC、不扫描报文、不改变实际时间；返回的新定义交给计算状态使用，
静态配置仍保留缺省声明。无需有效期的无关信号不会额外请求周期。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`resolve_signal_validity`](#api-resolve_signal_validity)|复用当前来源初始化取得的周期，补齐本次计算真正需要的信号有效期。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from ..legacy.records import field_to_dict
from ..sources.can_spec import can_field_from_key
from ..planning.signal_validity import triple_period
```

</details>

<a id="api-resolve_signal_validity"></a>
## `resolve_signal_validity`

复用当前来源初始化取得的周期，补齐本次计算真正需要的信号有效期。

```python
resolve_signal_validity(definitions, source_cursors)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`definitions`|tuple[SignalDefinition, ...]|是|无|位置或关键字。实际使用的信号定义；已明确有效期的对象原样复用。|
|`source_cursors`|Mapping[str, RecordSourceCursor]|是|无|位置或关键字。来源名到已初始化游标的映射，元数据含同次locator及cycle_ns；本函数不额外读取DBC或日志。|

### 返回说明

全部有效期已确定的SignalDefinition元组；原静态声明不被修改。

### 异常说明

ValueError：缺少唯一周期；PlanValidationError：周期3倍超出纳秒范围。

### 副作用说明

无，不修改原声明或游标，不读取文件。

源码：[`src/chronaxis/execution/signal_validity.py:14`](../../../src/chronaxis/execution/signal_validity.py#L14)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
