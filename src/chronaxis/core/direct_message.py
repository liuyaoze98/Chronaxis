"""保存直接消息累计的版本化扫描证据，不声称消息历史曾写入磁盘。

输入由执行层在同次真实扫描、EOF和读取资源关闭后提取；本模块仅校有限结构，
不读CAN/DBC、不重算信号、不认证手造对象。旧signal_stream_sha256明确对应全部
声明信号的规范HistorySample/HistoryProgress流，既非原文件SHA，也非消息仓SHA。
新输入证据单独保存全部原时间及实际保留计算记录的传输内容摘要；不生成普通
信号样本，不以零样本数或旧摘要字段冒充整套信号检查，也不覆盖未传输的帧载荷。
全原帧观测、投影和指标ID选择分别保留，避免把信号样本数误作原帧数。结果解码时
重新执行严格校验；身份由全部字段及独立版本生成，不借用MessageBindings身份。
"""

from dataclasses import dataclass, field

from .message_binding import _hash_parts
from .validation import require_identifier, require_text
from ..timebase.conversion import require_int64_ns


def _text(value, name, *, identifier=False):
    """检查原生非空文本。参数: 原值、字段名及名称开关。返回: None。异常: 原类型/文本错误。"""
    if type(value) is not str:
        raise TypeError(name + '需要原生str')
    (require_identifier if identifier else require_text)(value, name)


def _sha(value, name):
    """检查规范SHA文本，不把标签冒充摘要。参数: 原值及字段名。返回: None。异常: 类型/格式错误。"""
    _text(value, name)
    if len(value) != 64 or any(char not in '0123456789abcdef' for char in value):
        raise ValueError(name + '需要64位小写SHA-256')


@dataclass(frozen=True)
class DirectMessageEvidence:
    """冻结一次已完成扫描的有限事实；构造成功本身不证明实际读取发生。"""

    source: str  # 原计划中的CAN来源名。
    session_id: str  # 同次请求的会话身份。
    decoder_profile: str  # 同次READY确认的旧解码profile。
    read_identity: str  # 实际read的UUID，不用于稳定输入身份。
    input_identity: str  # 原来源声明的输入身份，不冒充原文件内容SHA。
    source_contract_sha256: str  # 来源配置、时基、偏移和输入声明的规范摘要。
    description_sha256: str  # 原adapter描述的规范摘要。
    request_sha256: str  # 本次全部别名、请求范围及批上限的规范摘要。
    signal_stream_sha256: str  # 已校验信号样本/进度流摘要；不存在对应消息历史文件。
    projected_aliases: tuple[str, ...]  # 原请求的完整别名顺序，允许空投影。
    progress_count: int  # 实际验证的进度记录数，含最终EOF记录。
    sample_count: int  # 已校验信号样本数，多信号时不同于原帧数。
    observed_frame_count: int  # 全部原yield数，包括不匹配指标或没有信号的帧。
    first_time_ns: int | None  # 全原帧首个映射时间，空源为None。
    last_time_ns: int | None  # 全原帧最后映射时间，不补采样周期。
    observed_start_ns: int | None  # 来源实际观测范围起点，可保声明的更早起点。
    observed_end_ns: int | None  # 真实EOF确认的观测终点。
    calculation_frame_ids: tuple[int, ...]  # 指标请求的去重原ID，非全部读取帧集合。
    source_eof: bool  # 必须True；工厂还需核实际进程结束和read关闭。
    evidence_kind: str = 'can-direct-scan-v1'  # 与消息仓证据完全独立的固定版本。
    identity: str = field(init=False)  # 全字段版本化SHA，含本次read UUID。

    def __post_init__(self):
        """核扫描范围、真实EOF标志和固定选择域，再计算独立身份。

        参数: 全部构造字段。返回: None，时间规范为原生int，identity为全字段SHA。
        异常: TypeError/ValueError为结构矛盾；时间越界、编码及取消错误原样传播。
        执行工厂还须核同scan/read/request及预算归属；此模型不开放假历史字段。
        """
        for name in ('source', 'session_id'):
            _text(getattr(self, name), 'direct.' + name, identifier=True)
        for name in ('decoder_profile', 'read_identity', 'input_identity'):
            _text(getattr(self, name), 'direct.' + name)
        if type(self.evidence_kind) is not str or self.evidence_kind != 'can-direct-scan-v1':
            raise ValueError('直接消息证据只支持can-direct-scan-v1')
        for name in ('source_contract_sha256', 'description_sha256', 'request_sha256', 'signal_stream_sha256'):
            _sha(getattr(self, name), 'direct.' + name)
        if type(self.projected_aliases) is not tuple:
            raise TypeError('直接扫描投影需要tuple')
        for alias in self.projected_aliases:
            _text(alias, 'direct.projected_alias', identifier=True)
        if len(set(self.projected_aliases)) != len(self.projected_aliases):
            raise ValueError('直接扫描投影不能重复')
        for name in ('progress_count', 'sample_count', 'observed_frame_count'):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError('direct.' + name + '需要非负原生int')
        if not self.progress_count or self.source_eof is not True:
            raise ValueError('直接扫描证据需要完整EOF及至少一次进度记录')
        if not self.projected_aliases and self.sample_count:
            raise ValueError('空投影不能有信号样本')
        for name in ('first_time_ns', 'last_time_ns', 'observed_start_ns', 'observed_end_ns'):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_int64_ns(value, 'direct.' + name))
        if self.observed_frame_count == 0:
            if self.first_time_ns is not None or self.last_time_ns is not None or self.sample_count:
                raise ValueError('全空扫描不能有原帧首末或信号样本')
        elif (self.first_time_ns is None or self.last_time_ns is None
                or self.observed_start_ns is None or self.observed_end_ns is None
                or not self.observed_start_ns <= self.first_time_ns <= self.last_time_ns <= self.observed_end_ns):
            raise ValueError('非空直接扫描需有序首末及包含原帧的观测范围')
        if (self.observed_start_ns is not None and self.observed_end_ns is not None
                and self.observed_start_ns > self.observed_end_ns):
            raise ValueError('直接扫描观测范围不能回退')
        if type(self.calculation_frame_ids) is not tuple or not self.calculation_frame_ids:
            raise TypeError('直接累计指标帧ID需要非空tuple')
        previous = -1
        for frame_id in self.calculation_frame_ids:
            if type(frame_id) is not int or not 0 <= frame_id <= 0x1fffffff or frame_id <= previous:
                raise ValueError('直接累计帧ID须为严格递增且范围合法的原生int')
            previous = frame_id
        parts = None
        try:
            # 用长度前缀hash编码每字段；嵌套tuple先明确数量，不以文本拼接猜边界。
            parts = (self.evidence_kind, self.source, self.session_id, self.decoder_profile,
                self.read_identity, self.input_identity, self.source_contract_sha256,
                self.description_sha256, self.request_sha256, self.signal_stream_sha256,
                str(len(self.projected_aliases)), *self.projected_aliases,
                str(self.progress_count), str(self.sample_count), str(self.observed_frame_count),
                *(str(value) if value is not None else 'none' for value in
                    (self.first_time_ns, self.last_time_ns, self.observed_start_ns, self.observed_end_ns)),
                str(len(self.calculation_frame_ids)), *(str(value) for value in self.calculation_frame_ids), 'true')
            object.__setattr__(self, 'identity', _hash_parts(parts))
        finally:
            parts = None


@dataclass(frozen=True)
class DirectMessageInputEvidence:
    """冻结按实际需求完成读取的输入事实，与旧普通信号扫描证据分开。

    原时间摘要按原序连接每帧大端float64字节，保留正负零；记录摘要连接每条
    已严格解包记录的四字节长度及JSON字节，两者均不包含批头，故不依赖分批。
    它们不是BLF文件SHA，也不证明未保留帧的载荷；实际投影范围由请求、描述、
    所需别名和指标ID共同标识。构造仅检查有限结构，完成工厂仍须核同次读取、
    全部时间映射、EOF与资源成功关闭，并先预约模型和身份计算的内存。
    """

    source: str  # 计划中的CAN来源名称。
    session_id: str  # 同次读取和累计所属的会话身份。
    decoder_profile: str  # 实际READY确认的旧解码profile。
    read_identity: str  # 同次真实read UUID，不用于跨运行稳定输入身份。
    input_identity: str  # 原来源输入声明身份，不冒充BLF内容SHA。
    source_contract_sha256: str  # 来源配置、时基、偏移与输入声明的规范摘要。
    description_sha256: str  # 实际来源描述，包含解码策略和字段选择范围。
    request_sha256: str  # 实际请求字段、范围、批上限等的规范摘要。
    original_timestamps_sha256: str  # 全部原帧时间字节流SHA，包含未保留帧的时间。
    retained_records_sha256: str  # 保留记录长度及JSON字节流SHA，仅覆盖实际投影内容。
    required_aliases: tuple[str, ...]  # 本次实际计算所需别名顺序，常量指标允许为空。
    observed_frame_count: int  # 全部原yield数量，不限于目标ID或有效计算。
    retained_record_count: int  # 严格解包的实际保留记录数，不等同求值或贡献数。
    first_time_ns: int | None  # 全原帧首个映射时间；空输入为None。
    last_time_ns: int | None  # 全原帧最后映射时间，不补采样周期。
    observed_start_ns: int | None  # 实际观测范围起点，可包括声明的更早起点。
    observed_end_ns: int | None  # 真实EOF确认的观测终点。
    calculation_frame_ids: tuple[int, ...]  # 指标请求的去重原ID，严格递增。
    source_eof: bool  # 只能为True；工厂另核真实EOF和成功关闭。
    evidence_kind: str = 'can-direct-input-v2'  # 与旧信号流及消息历史证据不同的版本。
    identity: str = field(init=False)  # 全部字段及版本的SHA，包含本次read UUID。

    def __post_init__(self):
        """核实际选择、两路内容摘要及完整读取范围，计算独立版本身份。

        参数: 全部构造字段；计数为非负原生int，时间为可规范化的int64纳秒。
        返回: None；时间规范为原生int，identity写入全字段版本化SHA。
        异常: TypeError/ValueError为结构矛盾，时间溢出、编码或取消错误原样传播。
        无文件或进程操作；SHA文本合法不等于此构造器认证了实际输入内容。
        """
        # 输入身份与读取身份保持原含义，不把同名旧证据或自由标签当成新版本。
        for name in ('source', 'session_id'):
            _text(getattr(self, name), 'direct_input.' + name, identifier=True)
        for name in ('decoder_profile', 'read_identity', 'input_identity'):
            _text(getattr(self, name), 'direct_input.' + name)
        if type(self.evidence_kind) is not str or self.evidence_kind != 'can-direct-input-v2':
            raise ValueError('直接输入证据只支持can-direct-input-v2')
        for name in ('source_contract_sha256', 'description_sha256', 'request_sha256',
                'original_timestamps_sha256', 'retained_records_sha256'):
            _sha(getattr(self, name), 'direct_input.' + name)

        # 空别名不等于空记录：纯参数表达式仍按实际selector消息求值。
        if type(self.required_aliases) is not tuple:
            raise TypeError('直接输入所需别名需要tuple')
        for alias in self.required_aliases:
            _text(alias, 'direct_input.required_alias', identifier=True)
        if len(set(self.required_aliases)) != len(self.required_aliases):
            raise ValueError('直接输入所需别名不能重复')
        for name in ('observed_frame_count', 'retained_record_count'):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError('direct_input.' + name + '需要非负原生int')
        if self.retained_record_count > self.observed_frame_count:
            raise ValueError('保留计算记录数不能超过全部原帧数')
        if self.source_eof is not True:
            raise ValueError('直接输入证据需要真实完整EOF')

        # 两路都是原字节流SHA；零项的规范值已知，不能用任意摘要假装空输入。
        empty_sha256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
        if not self.observed_frame_count and self.original_timestamps_sha256 != empty_sha256:
            raise ValueError('无原帧时原时间摘要必须为空字节流SHA-256')
        if not self.retained_record_count and self.retained_records_sha256 != empty_sha256:
            raise ValueError('无保留记录时记录摘要必须为空字节流SHA-256')

        # 先规范时间再比较。空来源可保声明范围，但不伪造首末原帧时间。
        for name in ('first_time_ns', 'last_time_ns', 'observed_start_ns', 'observed_end_ns'):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_int64_ns(value, 'direct_input.' + name))
        if (self.observed_start_ns is None) != (self.observed_end_ns is None):
            raise ValueError('直接输入观测范围起终必须同时存在或同时为空')
        if not self.observed_frame_count:
            if self.first_time_ns is not None or self.last_time_ns is not None:
                raise ValueError('全空直接输入不能有原帧首末时间')
        elif (self.first_time_ns is None or self.last_time_ns is None
                or self.observed_start_ns is None or self.observed_end_ns is None
                or not self.observed_start_ns <= self.first_time_ns <= self.last_time_ns <= self.observed_end_ns):
            raise ValueError('非空直接输入需有序首末及包含原帧的观测范围')
        if (self.observed_start_ns is not None and self.observed_end_ns is not None
                and self.observed_start_ns > self.observed_end_ns):
            raise ValueError('直接输入观测范围不能回退')

        # ID只表示指标选择，不声称全部原帧ID集合或所有帧都产生了计算记录。
        if type(self.calculation_frame_ids) is not tuple or not self.calculation_frame_ids:
            raise TypeError('直接输入指标帧ID需要非空tuple')
        previous = -1
        for frame_id in self.calculation_frame_ids:
            if type(frame_id) is not int or not 0 <= frame_id <= 0x1fffffff or frame_id <= previous:
                raise ValueError('直接输入帧ID须为严格递增且范围合法的原生int')
            previous = frame_id
        parts = None
        try:
            # 字段与tuple均有明确边界；把两个摘要分别绑定，不能互换后保留身份。
            parts = (self.evidence_kind, self.source, self.session_id, self.decoder_profile,
                self.read_identity, self.input_identity, self.source_contract_sha256,
                self.description_sha256, self.request_sha256, self.original_timestamps_sha256,
                self.retained_records_sha256, str(len(self.required_aliases)), *self.required_aliases,
                str(self.observed_frame_count), str(self.retained_record_count),
                *(str(value) if value is not None else 'none' for value in
                    (self.first_time_ns, self.last_time_ns, self.observed_start_ns, self.observed_end_ns)),
                str(len(self.calculation_frame_ids)), *(str(value) for value in self.calculation_frame_ids), 'true')
            object.__setattr__(self, 'identity', _hash_parts(parts))
        finally:
            # 取消或编码失败不由本帧额外保留新身份tuple；外层负责模型费用恢复。
            parts = None


@dataclass(frozen=True)
class DemandMessageInputEvidence:
    """保存按需处理范围与实际输入，允许完全不采集时间。

    source模式的时间摘要连接每帧float64字节，其他模式为None。记录摘要连接每条
    已严格解包记录的四字节长度及JSON字节，两者均不包含批头，故不依赖分批。
    它们不是BLF文件SHA，也不证明未保留帧的载荷；实际投影范围由请求、描述、
    所需别名和指标ID共同标识。构造仅检查有限结构，完成工厂仍须核同次读取、
    声明范围内的时间检查、EOF与资源成功关闭，并先预约模型和身份计算的内存。
    """

    source: str  # 计划中的CAN来源名称。
    session_id: str  # 同次读取和累计所属的会话身份。
    decoder_profile: str  # 实际READY确认的旧解码profile。
    read_identity: str  # 同次真实read UUID，不用于跨运行稳定输入身份。
    input_identity: str  # 原来源输入声明身份，不冒充BLF内容SHA。
    source_contract_sha256: str  # 来源配置、时基、偏移与输入声明的规范摘要。
    description_sha256: str  # 实际来源描述，包含解码策略和字段选择范围。
    request_sha256: str  # 实际请求字段、范围、批上限等的规范摘要。
    original_timestamps_sha256: str | None  # 只有source模式提供全部原帧时间SHA。
    retained_records_sha256: str  # 保留记录长度及JSON字节流SHA，仅覆盖实际投影内容。
    required_aliases: tuple[str, ...]  # 本次实际计算所需别名顺序，常量指标允许为空。
    observed_frame_count: int  # 全部原yield数量，不限于目标ID或有效计算。
    retained_record_count: int  # 严格解包的实际保留记录数，不等同求值或贡献数。
    first_time_ns: int | None  # source为全来源首时间，selected为目标首时间，none未采集。
    last_time_ns: int | None  # 对应采集范围的末时间，不补采样周期。
    observed_start_ns: int | None  # 实际观测范围起点，可包括声明的更早起点。
    observed_end_ns: int | None  # 真实EOF确认的观测终点。
    calculation_frame_ids: tuple[int, ...]  # 指标请求的去重原ID，严格递增。
    source_eof: bool  # 只能为True；工厂另核真实EOF和成功关闭。
    time_scope: str  # none/selected/source，只描述实际采集范围。
    input_check: str  # auto/full，实际worker握手认证的检查策略。
    evidence_kind: str = 'can-demand-input-v1'  # 与旧信号流及消息历史证据不同的版本。
    identity: str = field(init=False)  # 全部字段及版本的SHA，包含本次read UUID。

    def __post_init__(self):
        """核实际选择、两路内容摘要及完整读取范围，计算独立版本身份。

        参数: 全部构造字段；计数为非负原生int，时间为可规范化的int64纳秒。
        返回: None；时间规范为原生int，identity写入全字段版本化SHA。
        异常: TypeError/ValueError为结构矛盾，时间溢出、编码或取消错误原样传播。
        无文件或进程操作；SHA文本合法不等于此构造器认证了实际输入内容。
        """
        # 输入身份与读取身份保持原含义，不把同名旧证据或自由标签当成新版本。
        for name in ('source', 'session_id'):
            _text(getattr(self, name), 'direct_input.' + name, identifier=True)
        for name in ('decoder_profile', 'read_identity', 'input_identity'):
            _text(getattr(self, name), 'direct_input.' + name)
        if type(self.evidence_kind) is not str or self.evidence_kind != 'can-demand-input-v1':
            raise ValueError('直接输入证据只支持can-demand-input-v1')
        for name in ('source_contract_sha256', 'description_sha256', 'request_sha256',
                'retained_records_sha256'):
            _sha(getattr(self, name), 'direct_input.' + name)

        # 不采集全原时间时使用None，禁止空SHA或目标时间SHA冒充全时间证据。
        if type(self.time_scope) is not str or self.time_scope not in ('none', 'selected', 'source'):
            raise ValueError('按需输入时间范围仅none/selected/source')
        if type(self.input_check) is not str or self.input_check not in ('auto', 'full'):
            raise ValueError('按需输入检查范围仅auto/full')
        if self.input_check == 'full' and self.time_scope != 'source':
            raise ValueError('完整检查必须覆盖整个来源时间')
        if self.time_scope == 'source':
            _sha(self.original_timestamps_sha256, 'demand.original_timestamps_sha256')
        elif self.original_timestamps_sha256 is not None:
            raise ValueError('未采集全部原时间时不能声明全时间摘要')

        # 空别名不等于空记录：纯参数表达式仍按实际selector消息求值。
        if type(self.required_aliases) is not tuple:
            raise TypeError('直接输入所需别名需要tuple')
        for alias in self.required_aliases:
            _text(alias, 'direct_input.required_alias', identifier=True)
        if len(set(self.required_aliases)) != len(self.required_aliases):
            raise ValueError('直接输入所需别名不能重复')
        for name in ('observed_frame_count', 'retained_record_count'):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError('direct_input.' + name + '需要非负原生int')
        if self.retained_record_count > self.observed_frame_count:
            raise ValueError('保留计算记录数不能超过全部原帧数')
        if self.source_eof is not True:
            raise ValueError('直接输入证据需要真实完整EOF')

        # 两路都是原字节流SHA；零项的规范值已知，不能用任意摘要假装空输入。
        empty_sha256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
        if self.time_scope == 'source' and not self.observed_frame_count and self.original_timestamps_sha256 != empty_sha256:
            raise ValueError('无原帧时原时间摘要必须为空字节流SHA-256')
        if not self.retained_record_count and self.retained_records_sha256 != empty_sha256:
            raise ValueError('无保留记录时记录摘要必须为空字节流SHA-256')

        # 先规范时间再比较。空来源可保声明范围，但不伪造首末原帧时间。
        for name in ('first_time_ns', 'last_time_ns', 'observed_start_ns', 'observed_end_ns'):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_int64_ns(value, 'direct_input.' + name))
        if (self.observed_start_ns is None) != (self.observed_end_ns is None):
            raise ValueError('直接输入观测范围起终必须同时存在或同时为空')
        if self.time_scope == 'none':
            if any(getattr(self, name) is not None for name in
                    ('first_time_ns', 'last_time_ns', 'observed_start_ns', 'observed_end_ns')):
                raise ValueError('无时间输入不能伪造首末或观测范围')
        elif self.time_scope == 'selected':
            if self.observed_start_ns is not None or self.observed_end_ns is not None:
                raise ValueError('目标记录范围不能冒充整个来源的观测范围')
            if self.retained_record_count:
                if self.first_time_ns is None or self.last_time_ns is None or self.first_time_ns > self.last_time_ns:
                    raise ValueError('非空目标时间需有序首末')
            elif self.first_time_ns is not None or self.last_time_ns is not None:
                raise ValueError('没有目标记录不能声明目标首末时间')
        elif not self.observed_frame_count:
            if self.first_time_ns is not None or self.last_time_ns is not None:
                raise ValueError('全空直接输入不能有原帧首末时间')
        elif (self.first_time_ns is None or self.last_time_ns is None
                or self.observed_start_ns is None or self.observed_end_ns is None
                or not self.observed_start_ns <= self.first_time_ns <= self.last_time_ns <= self.observed_end_ns):
            raise ValueError('全来源时间证明需包含全部原帧首末')

        # 空来源也不能以声明边界绕过有序范围检查。
        if (self.observed_start_ns is not None and self.observed_end_ns is not None
                and self.observed_start_ns > self.observed_end_ns):
            raise ValueError('按需输入观测范围不能回退')

        # ID只表示指标选择，不声称全部原帧ID集合或所有帧都产生了计算记录。
        if type(self.calculation_frame_ids) is not tuple or not self.calculation_frame_ids:
            raise TypeError('直接输入指标帧ID需要非空tuple')
        previous = -1
        for frame_id in self.calculation_frame_ids:
            if type(frame_id) is not int or not 0 <= frame_id <= 0x1fffffff or frame_id <= previous:
                raise ValueError('直接输入帧ID须为严格递增且范围合法的原生int')
            previous = frame_id
        parts = None
        try:
            # 字段与tuple均有明确边界；把两个摘要分别绑定，不能互换后保留身份。
            parts = (self.evidence_kind, self.source, self.session_id, self.decoder_profile,
                self.read_identity, self.input_identity, self.source_contract_sha256,
                self.description_sha256, self.request_sha256, self.time_scope, self.input_check,
                self.original_timestamps_sha256 or 'not_collected',
                self.retained_records_sha256, str(len(self.required_aliases)), *self.required_aliases,
                str(self.observed_frame_count), str(self.retained_record_count),
                *(str(value) if value is not None else 'none' for value in
                    (self.first_time_ns, self.last_time_ns, self.observed_start_ns, self.observed_end_ns)),
                str(len(self.calculation_frame_ids)), *(str(value) for value in self.calculation_frame_ids), 'true')
            object.__setattr__(self, 'identity', _hash_parts(parts))
        finally:
            # 取消或编码失败不由本帧额外保留新身份tuple；外层负责模型费用恢复。
            parts = None
