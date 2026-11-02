# chronaxis.migration.start_end

核对旧start_end的显式业务选择及等待时限。

输入为已定位INI和用户映射，输出新开始/结束规则的初始化及时限字段。
旧模式先准备再确认切片，新模式从start记录到end；mapping必须声明
start_end_timeout-v1。本模块不执行条件、读取日志或修复旧入口。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)

## 对象导航

|对象|用途|
|---|---|
|[`start_end_options`](#api-start_end_options)|检查显式新语义，按已审旧字段解释正时限和不限时。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from decimal import Decimal, InvalidOperation
from ..timebase import parse_duration
from .ini import problem, field_path, locate
from .models import LegacyImportIssue
```

</details>

<a id="api-start_end_options"></a>
## `start_end_options`

检查显式新语义，按已审旧字段解释正时限和不限时。

```python
start_end_options(parser, fields, section, selected, issues)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`parser`|configparser.ConfigParser|是|无|位置或关键字。已经解析的旧INI，用它读取原段落和键值；不在这里重新读取文件。|
|`fields`|list[LegacyFieldMapping]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`selected`|dict|是|无|位置或关键字。selected为段映射|
|`issues`|list[[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)]|是|无|位置或关键字。接收本次转换的差异、警告和拒绝原因；调用者随后将它们写入迁移报告。|

### 返回说明

timeout/emit_initial字典。

### 异常说明

ImportProblem为配置非法；取消和内存错误原样传播。

本函数直接报告的具体错误：

- `ValueError`：duration_sec必须有限。
- `ValueError`：正时限不能小于可表示的纳秒。

源码：[`src/chronaxis/migration/start_end.py:14`](../../../src/chronaxis/migration/start_end.py#L14)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
