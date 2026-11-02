# chronaxis.migration.slope

把旧 slope 字符串拆为明确的完整窗口规则，不执行旧配置。

输入为一个原表达式、显式名称映射和该段的迁移选择；输出 window_delta
字段及可定位的差异报告。先识别固定前缀，再从右侧取阈值，剩余原信号名
必须完整命中 aliases，因此信号名可以包含下划线。此模块不读数据或 DBC，
不修复旧构造器，也不把完整窗口计算声称为旧样本口径的逐帧等价实现。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)

## 对象导航

|对象|用途|
|---|---|
|[`slope_rule`](#api-slope_rule)|按显式迁移选择生成一个完整窗口规则。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from decimal import Decimal, InvalidOperation
from ..timebase import parse_duration
from .ini import field_path, locate, problem
from .models import LegacyImportIssue
```

</details>

<a id="api-slope_rule"></a>
## `slope_rule`

按显式迁移选择生成一个完整窗口规则。

```python
slope_rule(text, aliases, selected, fields, section, issues)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。旧配置中的斜率判断表达式，解析后生成window_delta规则；不执行任意Python代码。|
|`aliases`|Mapping[str, str]|是|无|位置或关键字。旧表达式名称到新信号别名的映射，例如{"Voltage": "u"}；表达式中的Voltage据此改成u。|
|`selected`|dict|是|无|位置或关键字。selected 为 段映射|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`issues`|list[[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)]|是|无|位置或关键字。接收本次转换的差异、警告和拒绝原因；调用者随后将它们写入迁移报告。|

### 返回说明

可交给 AnalysisPlan 的规则字典。

### 异常说明

ImportProblem 表示有定位的
配置问题；内存错误及取消原样传播。阈值沿用信号单位，不除以窗口时长。

本函数直接报告的具体错误：

- `ValueError`：窗口必须大于零。
- `ValueError`：阈值须为十进制数值。
- `ValueError`：阈值必须有限且非负。
- `ValueError`：阈值超出可表示的数值范围。

源码：[`src/chronaxis/migration/slope.py:18`](../../../src/chronaxis/migration/slope.py#L18)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
