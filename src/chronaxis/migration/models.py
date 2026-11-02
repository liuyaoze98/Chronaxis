"""保存旧配置导入的冻结报告，不把静态转换当作数据运行证明。

输入为导入器已经定位的配置事实；输出为固定类型结果和可供CLI写出的原生
JSON字典。原INI字节单独保留，字段和问题保持原顺序。本模块不读写文件、
执行表达式或导入任何旧配置对象，失败结果不能携带部分成功计划。
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..planning import AnalysisPlan


@dataclass(frozen=True)
class LegacyImportIssue:
    """定位一个错误或明确迁移差异；行列以1开始，非文本位置可为None。"""

    code: str
    origin: str
    path: str
    message: str
    line: int | None = None
    column: int | None = None
    level: str = 'error'

    def to_dict(self) -> dict:
        """转换固定问题字段；参数: 无；返回: JSON对象；异常: 无。"""
        return {name: getattr(self, name) for name in
                ('code', 'origin', 'path', 'message', 'line', 'column', 'level')}


@dataclass(frozen=True)
class LegacyFieldMapping:
    """保一项原INI字段、文本定位及处理去向，不因替代I/O丢弃原值。"""

    origin: str
    path: str
    value: str
    line: int
    column: int
    target: str | None
    status: str
    message: str

    def to_dict(self) -> dict:
        """转换固定字段事实；参数: 无；返回: JSON对象；异常: 无。"""
        return {name: getattr(self, name) for name in
                ('origin', 'path', 'value', 'line', 'column', 'target', 'status', 'message')}


@dataclass(frozen=True)
class LegacyImportReport:
    """区分整份成功与失败，SHA只证明配置身份，不证明来源数据已读。"""

    status: str
    mode: str
    source_name: str
    source_sha256: str
    mapping_identity: str | None
    device_label: str
    fields: tuple[LegacyFieldMapping, ...]
    issues: tuple[LegacyImportIssue, ...]
    plan_identity: str | None

    def to_dict(self) -> dict:
        """生成独立JSON报告；参数: 无；返回: dict；异常: 无。

        流程: 仅展开固定报告对象，原INI和AnalysisPlan不会被反射序列化。
        """
        return {'status': self.status, 'mode': self.mode, 'source_name': self.source_name,
                'source_sha256': self.source_sha256, 'mapping_identity': self.mapping_identity,
                'device_label': self.device_label, 'fields': [item.to_dict() for item in self.fields],
                'issues': [item.to_dict() for item in self.issues], 'plan_identity': self.plan_identity}


@dataclass(frozen=True)
class LegacyImportResult:
    """返回完整计划或None，同时保留同一个不可变原INI字节对象。"""

    plan: 'AnalysisPlan | None'
    report: LegacyImportReport
    original_ini: bytes
