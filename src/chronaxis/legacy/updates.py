"""表示旧路径一次实际求值所见的更新，并校验单来源的求值顺序。

输入是调用方已经取得的时间、原帧身份、SourceRef、原求值序号和完整值字典；
输出是冻结的LegacyDecodedUpdate及只保存最后事实的LegacyUpdateOrder。
无需时间的固定周期消息累计显式使用LegacyUntimedUpdate，其time_ns只能
为None；同一顺序器不能混用有时间和无时间更新，不补造0时间。
模型保留原字段全文、None和非有限浮点，不推断类型、单位、缩放、TTL、缓存
或有效性。QualityFlag.NONE只表示没有记录质量原因，不证明值的新鲜度。

本模块只依赖标准库和共享核心模型，不读取日志、不调用旧解码器，也不提供
旧求值点的采集接口。调用方构造这些对象不能证明真实旧生产者已经暴露求值
过程；真实求值证据仍须由后续来源契约提供。值字典由调用方提供，本层复制
并冻结它，不宣称该复制已有执行预算或IPC大小界限。
"""

# 只复用类型、时间及标量校验；原字段不经过表达式别名或CAN线协议转换。
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..core.models import SourceRef
from ..core.types import QualityFlag
from ..core.validation import require_identifier, require_scalar
from ..timebase.conversion import require_int64_ns


def _require_nonnegative_int(value: int, field: str) -> int:
    """校验原生非负整数身份，不把布尔或数值子类转成合法序号。

    参数:
        value: 原生int，表示通道、帧ID、来源序号或求值序号。
        field: 错误消息使用的字段名称。
    返回:
        int: 输入的原整数；不重编号，也不设置额外的序号上限。
    异常:
        TypeError: 输入不是精确的原生int，包括bool和整数子类。
        ValueError: 输入为负数。
    """
    # 身份整数的协议比共享时间的Integral协议严格，不能隐式接受数组标量。
    if type(value) is not int:
        raise TypeError(f"{field}必须为原生非布尔整数")
    if value < 0:
        raise ValueError(f"{field}必须非负")
    return value


@dataclass(frozen=True)
class LegacyDecodedUpdate:
    """冻结一次求值的原值快照，区分原帧序号与求值序号。

    time_ns按共享int64纳秒协议规范化；sequence定位原帧，evaluation_index
    定位求值点，同一帧可以有多次求值。四个原帧标志必须显式传入，不能由ID
    或载荷猜测。source_ref保留原对象并核对source，不补造旧缓存或求值证据。
    values只接收精确dict或MappingProxyType，复制后冻结；键与原生不可变
    标量保持原样，空字典合法，非有限浮点不会被替换或自动附加质量原因。
    """

    time_ns: int  # 调用方已取得的时间；仅按共享时间协议规范为Python整数。
    source: str  # 与SourceRef.source_name一致的来源标识。
    channel: int  # 原生非负通道编号，不从其他帧信息推断。
    frame_id: int  # 标准帧或扩展帧范围内的原CAN ID。
    is_extended: bool  # 原扩展帧标志，决定ID的合法上限。
    is_fd: bool  # 原CAN FD标志，不由数据长度推断。
    is_remote: bool  # 原远程帧标志，必须由调用方明确提供。
    is_error: bool  # 原错误帧标志，不由质量位推断。
    source_ref: SourceRef  # 原来源引用；允许已有SourceRef子类。
    sequence: int  # 原帧序号；不要求连续，也不等同于求值序号。
    evaluation_index: int  # 旧求值顺序；跨帧及同帧均独立递增。
    values: Mapping[str, int | float | bool | str | None]  # 原字段和值的独立冻结副本。
    quality: QualityFlag = QualityFlag.NONE  # 只保留明确记录的原因位。

    def __post_init__(self) -> None:
        """校验显式身份并建立不受调用方字典后续修改影响的快照。

        参数:
            无额外参数；读取构造时传入的全部字段。
        返回:
            None: 成功后time_ns已规范，values为新MappingProxyType。
        异常:
            TypeError: 身份、标志、来源引用、质量位、字典或标量类型不符。
            ValueError: 来源不匹配、负身份、ID越界或值字典含空键。
            TimeOverflowError: time_ns超出共享int64纳秒范围。
            MemoryError: 复制原值快照所需的分配失败；不返回部分模型。
        """
        # 时间沿已有协议允许Integral并精确规范；其余身份须为原生整数。
        time_ns = require_int64_ns(self.time_ns)
        # 无时间子类复用同一身份/数值校验，原入口仍在此严格要求真实时间。
        self._freeze_fields()
        object.__setattr__(self, "time_ns", time_ns)

    def _freeze_fields(self) -> None:
        """校验并冻结有时间与无时间更新共有的身份、质量和原值。

        参数:
            无额外参数；读取当前模型中除time_ns外的全部字段。
        返回:
            None: values被独立复制并冻结，其他身份及质量保持原值。
        异常:
            TypeError: 身份、标志、来源引用、质量或原值类型不合法。
            ValueError: 来源不匹配、负身份、ID越界或值字典含空键。
            MemoryError: 复制失败，调用方不能得到部分构造的模型。
        副作用:
            仅在当前待构造模型上安装冻结字典，不访问或伪造时间。
        """
        # 两种更新的区别仅为时间需求，不放宽原帧身份或原值契约。
        require_identifier(self.source, "legacy_update.source")
        _require_nonnegative_int(self.channel, "channel")
        _require_nonnegative_int(self.frame_id, "frame_id")
        _require_nonnegative_int(self.sequence, "sequence")
        _require_nonnegative_int(self.evaluation_index, "evaluation_index")

        # 四个标志各自来自原帧，不用Python真值转换补齐缺失或整数标志。
        for field in ("is_extended", "is_fd", "is_remote", "is_error"):
            if type(getattr(self, field)) is not bool:
                raise TypeError(f"{field}必须为原生bool")
        maximum_id = 0x1FFFFFFF if self.is_extended else 0x7FF
        if self.frame_id > maximum_id:
            raise ValueError("frame_id超出对应标准帧或扩展帧范围")

        # 引用只核对已有类型和来源身份，不把手工引用当作真实旧求值的证明。
        if not isinstance(self.source_ref, SourceRef):
            raise TypeError("source_ref必须为SourceRef")
        if self.source_ref.source_name != self.source:
            raise ValueError("source_ref.source_name必须与source一致")
        if not isinstance(self.quality, QualityFlag):
            raise TypeError("quality必须为QualityFlag")

        # 边遍历边校验并复制，避免先校验后再遍历时混入未经检查的新值。
        if type(self.values) not in (dict, MappingProxyType):
            raise TypeError("values仅接受精确dict或MappingProxyType")
        copied = {}
        for key, value in self.values.items():
            if type(key) is not str:
                raise TypeError("values的键必须为原生str")
            if not key:
                raise ValueError("values的键不能为空")
            require_scalar(value)
            copied[key] = value

        # 值均为不可变原生标量，单层独立复制已足够；不深拷贝或改写数值。
        frozen_values = MappingProxyType(copied)
        object.__setattr__(self, "values", frozen_values)


@dataclass(frozen=True)
class LegacyUntimedUpdate(LegacyDecodedUpdate):
    """保存无需时间的固定周期消息求值，复用原更新的完整身份和原值合同。

    time_ns只能显式为None，表示未采集时间；不代表0时刻或无观测数据。
    sequence与evaluation_index保留实际原序及求值序，其他字段与父类一致。
    本模型仍是LegacyDecodedUpdate，可交由相同逐消息数值核求值；调用方
    必须确保没有时间消费者，并且不从本模型构造带时间的贡献或观测范围。
    """

    time_ns: None  # 显式未采集；必填，禁止借默认0或其他占位满足时间模型。

    def __post_init__(self) -> None:
        """拒绝任何实数或占位时间，仅执行父类的共有字段校验。

        参数:
            无额外参数；读取构造字段，time_ns必须为None。
        返回:
            None: 原值冻结，身份和质量检查与LegacyDecodedUpdate完全相同。
        异常:
            TypeError: time_ns不是None，或共有字段类型不合法。
            ValueError或MemoryError: 共有身份越界、来源冲突或复制失败。
        副作用:
            仅冻结当前模型，不构造虚假时间或修改调用方值字典。
        """
        # 调用方不能把带真实时间的输入误报为未采集时间。
        if self.time_ns is not None:
            raise TypeError("LegacyUntimedUpdate.time_ns必须为None")
        self._freeze_fields()


class LegacyUpdateOrder:
    """校验同一会话和来源的逐次求值，不累计原值或维护旧信号缓存。

    session_id和source固定；last_time_ns、last_sequence、
    last_evaluation_index初始为None，count初始为0。时间和原帧序号不回退，
    求值序号严格递增且允许间隙。首个更新固定是否带时间，之后禁止混用；
    无时间模式的last_time_ns始终为None，仅按原序和求值序前进。
    同一原帧序号还须保留完全相同的时间、
    通道、ID和四个标志；值、质量及section引用可不同。最后事实保存在一个
    当前状态tuple中，全部检查和新状态分配完成后才一次替换；拒绝不改状态。
    """

    def __init__(self, session_id: str, source: str) -> None:
        """建立一个来源的空顺序状态，不接收或消费任何更新。

        参数:
            session_id: 沿共享模型规则校验的会话标识。
            source: 沿共享模型规则校验的来源标识。
        返回:
            None: 创建只读身份及初始空状态。
        异常:
            TypeError: 会话或来源不是文本。
            ValueError: 会话或来源不是合法的共享简单标识符。
        """
        # 身份只在构造时安装，公开属性不提供可绕过来源检查的赋值入口。
        self._session_id = require_identifier(session_id, "session_id")
        self._source = require_identifier(source, "source")
        self._state = (None, None, None, 0, None)

    @property
    def session_id(self) -> str:
        """返回固定会话标识；参数: 无；返回: 原str；异常: 无。"""
        return self._session_id

    @property
    def source(self) -> str:
        """返回固定来源标识；参数: 无；返回: 原str；异常: 无。"""
        return self._source

    @property
    def last_time_ns(self) -> int | None:
        """读取最后接受时间；参数: 无；返回: int或初始None；异常: 无。"""
        return self._state[0]

    @property
    def last_sequence(self) -> int | None:
        """读取最后原帧序号；参数: 无；返回: int或初始None；异常: 无。"""
        return self._state[1]

    @property
    def last_evaluation_index(self) -> int | None:
        """读取最后求值序号；参数: 无；返回: int或初始None；异常: 无。"""
        return self._state[2]

    @property
    def count(self) -> int:
        """读取已接受次数；参数: 无；返回: 非负int；异常: 无。"""
        return self._state[3]

    def accept(self, update: LegacyDecodedUpdate) -> None:
        """接受一个完整更新，仅在全部身份及顺序检查成功后提交最后事实。

        参数:
            update: 已构造的LegacyDecodedUpdate或LegacyUntimedUpdate；
                同帧可携带不同值快照，同一顺序器禁止混用时间模式。
        返回:
            None: 接受成功，count加一，最后事实切换到本次更新。
        异常:
            TypeError: update不是LegacyDecodedUpdate。
            ValueError: 会话、来源不符，时间模式混用，时间或原帧序号回退，求值序号不递增，
                或同一原帧序号的时间、通道、ID、四个标志出现冲突。
            MemoryError: 新状态分配失败；旧状态仍保持不变。
        """
        # 只接受已验证的更新模型；序号关系不从其他帧对象或原值中猜测。
        if not isinstance(update, LegacyDecodedUpdate):
            raise TypeError("update必须为LegacyDecodedUpdate")
        if update.source != self._source or update.source_ref.session_id != self._session_id:
            raise ValueError("update必须属于本会话和来源")

        # 当前帧身份不含值、质量或section引用，允许同帧多次真实求值。
        frame = (
            update.time_ns, update.channel, update.frame_id,
            update.is_extended, update.is_fd, update.is_remote, update.is_error,
        )
        last_time, last_sequence, last_evaluation, count, last_frame = self._state
        # count区分空状态和已接受无时间更新；保持原五元状态便于原子复制。
        if count and (last_time is None) != (update.time_ns is None):
            raise ValueError("同一顺序器不能混用有时间和无时间更新")
        if last_time is not None and update.time_ns < last_time:
            raise ValueError("time_ns不能回退")
        if last_sequence is not None and update.sequence < last_sequence:
            raise ValueError("sequence不能回退")
        if last_evaluation is not None and update.evaluation_index <= last_evaluation:
            raise ValueError("evaluation_index必须严格递增")
        if update.sequence == last_sequence and frame != last_frame:
            raise ValueError("同一sequence的原帧身份必须一致")

        # 先完成计数和tuple分配，再以单一写入提交；拒绝路径不接触已有状态。
        next_state = (
            update.time_ns, update.sequence, update.evaluation_index, count + 1, frame,
        )
        self._state = next_state
