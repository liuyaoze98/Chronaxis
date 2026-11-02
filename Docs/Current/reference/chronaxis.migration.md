# chronaxis.migration

公开安全旧配置导入及冻结迁移报告，不启动来源扫描或旧配置对象。

输入为原INI bytes与显式mapping，或两个配置路径；输出完整静态AnalysisPlan
和逐字段报告。当前模式能力以各入口返回的report为准；导入成功不是数据验收。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyFieldMapping](chronaxis.migration.models.md#api-LegacyFieldMapping)、[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)、[LegacyImportReport](chronaxis.migration.models.md#api-LegacyImportReport)、[LegacyImportResult](chronaxis.migration.models.md#api-LegacyImportResult)

## 对象导航

|对象|用途|
|---|---|

## 导出名称

`import_legacy_ini`, `load_legacy_ini`, `LegacyImportResult`, `LegacyImportReport`, `LegacyImportIssue`, `LegacyFieldMapping`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from .api import import_legacy_ini, load_legacy_ini
from .models import LegacyFieldMapping, LegacyImportIssue, LegacyImportReport, LegacyImportResult
```

</details>
