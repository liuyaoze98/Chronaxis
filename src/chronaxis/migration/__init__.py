"""公开安全旧配置导入及冻结迁移报告，不启动来源扫描或旧配置对象。

输入为原INI bytes与显式mapping，或两个配置路径；输出完整静态AnalysisPlan
和逐字段报告。当前模式能力以各入口返回的report为准；导入成功不是数据验收。
"""

from .api import import_legacy_ini, load_legacy_ini
from .models import LegacyFieldMapping, LegacyImportIssue, LegacyImportReport, LegacyImportResult

__all__ = ['import_legacy_ini', 'load_legacy_ini', 'LegacyImportResult', 'LegacyImportReport',
           'LegacyImportIssue', 'LegacyFieldMapping']
