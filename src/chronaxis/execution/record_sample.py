"""记录流只保一份逻辑值；枚举单独保必要整数码，公共来源定义共享引用。"""
from dataclasses import dataclass
from ..core.models import SourceRef,SignalSample
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D

@dataclass(frozen=True,slots=True)
class RecordSample:
    """一次规范更新；没有批次副本、原文或普通值的第二份物理表示。"""
    name: str
    time_ns: int
    sequence: int
    value: ScalarValue
    unit: str
    source_ref: SourceRef
    enum_code: int | None = None

    def __post_init__(self):
        """检查必要样本及枚举码含义。参数: 字段。返回: None。异常: 类型/值矛盾。"""
        if type(self.value) is not ScalarValue or type(self.unit) is not str:
            raise TypeError('记录样本需要规范值和单位')
        SignalSample(self.name,self.time_ns,self.value.value,self.value.valid,self.value.quality,self.source_ref,self.sequence)
        if self.value.dtype is D.ENUM:
            if type(self.enum_code) is not int:
                raise TypeError('枚举需要保留整数码')
            if self.value.valid and (not 0<=self.enum_code<len(self.value.labels) or self.value.labels[self.enum_code]!=self.value.value):
                raise ValueError('枚举码与标签不符')
        elif self.enum_code is not None:
            raise ValueError('普通值不保存第二份物理码')

    @property
    def array_value(self):
        """按需取得数组值；无效值只返回类型占位。参数: 无。返回: 标量。异常: 无。"""
        if self.value.dtype is D.ENUM:return self.enum_code
        if self.value.valid:return self.value.value
        return False if self.value.dtype is D.BOOL else 0. if self.value.dtype is D.FLOAT64 else 0

    @property
    def original_present(self):
        """本样本不保存原文。参数: 无。返回: False。异常: 无。"""
        return False

    @property
    def original_value(self):
        """本样本无额外原值。参数: 无。返回: None。异常: 无。"""
        return None


def _record_from_validated_fields(name, time_ns, sequence, value, unit, source_ref, enum_code=None):
    """把已校验列或解码归一化结果包装为当前运行记录，不再创建校验样本。

    参数: 已核别名/单位/来源、原生时间及序号、ScalarValue和已核枚举码。
    返回: 冻结RecordSample。异常: 分配错误；本函数不接外部未校验输入。
    调用方必须完成列布局/时间/枚举域验证，公开RecordSample构造保持原检查。
    """
    result = object.__new__(RecordSample)
    # 只安装原模型字段；不存在用户可启用的跳过校验选项。
    object.__setattr__(result, 'name', name)
    object.__setattr__(result, 'time_ns', time_ns)
    object.__setattr__(result, 'sequence', sequence)
    object.__setattr__(result, 'value', value)
    object.__setattr__(result, 'unit', unit)
    object.__setattr__(result, 'source_ref', source_ref)
    object.__setattr__(result, 'enum_code', enum_code)
    return result
