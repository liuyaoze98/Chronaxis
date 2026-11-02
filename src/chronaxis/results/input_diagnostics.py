"""保存明确请求的输入检查范围；摘要只覆盖实际交给分析层的记录。

一份来源说明关联必要路径、所需别名、检查范围及可选摘要，不复制输入文件。
本模型不读取数据；EOF和摘要由同次运行提供，不能当成全文件内容证明。
"""
from dataclasses import dataclass
from ..core.validation import require_identifier,require_text


@dataclass(frozen=True)
class InputDiagnostic:
    """一个实际来源的有限诊断；记录数与摘要均指同一所需记录流。"""
    source: str
    source_type: str
    paths: tuple[str,...]
    aliases: tuple[str,...]
    bindings: tuple[tuple[str,str],...]
    input_check: str
    time_scope: str
    record_count: int
    source_eof: bool
    sha256: str | None = None
    digest_scope: str = 'required-decoded-records-v1'

    def __post_init__(self):
        """核有限范围声明。参数: 无。返回: None。异常: 类型/值错误。"""
        require_identifier(self.source,'diagnostic.source')
        if self.source_type not in ('can_blf','can_asc','asc_or_blf','raw_can_csv','memory','signal_csv'):
            raise ValueError('诊断来源类型无效')
        for values in (self.paths,self.aliases):
            if type(values) is not tuple:raise TypeError('诊断路径/别名需要tuple')
            for value in values:require_text(value,'diagnostic.locator')
        if type(self.bindings) is not tuple or any(type(pair) is not tuple or len(pair)!=2
                or pair[0] not in self.aliases or type(pair[1]) is not str or not pair[1] for pair in self.bindings):
            raise ValueError('诊断绑定需要别名及实际原字段')
        if self.input_check not in ('auto','full') or self.time_scope not in ('none','selected','source'):
            raise ValueError('诊断检查范围无效')
        if type(self.record_count) is not int or self.record_count<0 or self.source_eof is not True:
            raise ValueError('诊断需要真实EOF与非负记录数')
        if self.sha256 is not None and (type(self.sha256) is not str or len(self.sha256)!=64
                or any(c not in '0123456789abcdef' for c in self.sha256)):
            raise ValueError('诊断摘要必须是SHA256或None')
        if self.digest_scope!='required-decoded-records-v1':
            raise ValueError('不能把所需记录流摘要声明为全文件证明')

    def to_dict(self):
        """输出一份来源/绑定范围，未请求摘要时不写空摘要栏。参数: 无。返回: dict。异常: 无。"""
        result={name:getattr(self,name) for name in ('source','source_type','paths','bindings','input_check','time_scope','record_count','source_eof')}
        result['record_scope']=self.digest_scope
        if self.sha256 is not None:result['sha256']=self.sha256
        return result
