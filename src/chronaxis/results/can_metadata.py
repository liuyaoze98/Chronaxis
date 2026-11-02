"""冻结同次CAN读取、原始暂存和DBC单位核对的结构化运行事实。

CANUnitCheck只保存原声明与同次公开DBC单位的比较；CANSourceMetadata保存会话、
profile、声明路径、实际read身份/进程、原帧数、映射首末、封口暂存SHA与累计费用、
依赖/vendor版本证据及单位检查。CANFrameFormatNotice明确记录已授权的单向DBC声明
差异，真实帧不转换。输入均为有限明确字段，输出冻结模型，不塞JSON
字符串或伪造DBC内容哈希。缺DBC单位仍保None/空原值并记declared，不提升为verified。
本模块仅校类型、内部一致性与唯一性，无路径访问、DBC解析、进程、预算或I/O副作用；
构造成功不能证明来源已读完、进程已退出、暂存已核验或物理单位已测量。
"""

# 只登记三类有限冻结模型；运行侧提供真实证据，声明侧不重新读取来源。
from dataclasses import dataclass
from ..core.validation import require_identifier, require_text
from ..legacy.records import PROFILE_ID, LegacyCANField
from ..timebase.conversion import require_int64_ns


def _integer(value, name, minimum=0):
    """校验非负原生整数，拒绝bool和外部整数替代。

    参数: value为候选值；name为字段名；minimum为含端点下限。返回: None。
    异常: TypeError为非原生int，ValueError为小于下限。
    """
    if type(value) is not int:
        raise TypeError(name + '需要原生int')
    if value < minimum:
        raise ValueError(name + '低于允许下限')


def _sha256(value, name):
    """校验64位hex摘要原文，不把路径、版本或随机身份冒充内容SHA。

    参数: value为候选摘要；name定位字段。返回: None，保大小写原值。
    异常: TypeError/ValueError为类型、长度或非hex字符；不读取文件证明实际内容。
    """
    if type(value) is not str:
        raise TypeError(name + '需要str')
    if len(value) != 64 or any(char not in '0123456789abcdefABCDEF' for char in value):
        raise ValueError(name + '需要64位hex SHA256')


def _pairs(value, name, hashes=False):
    """检查版本或vendor摘要的冻结键值对，不能重复键或接受可变字典。

    参数: value为tuple[tuple[str,str],...]；name定位字段；hashes指值是否需要SHA。
    返回: None。异常: TypeError/ValueError为结构、空文本、重复键或非法SHA。
    """
    if type(value) is not tuple:
        raise TypeError(name + '需要tuple')
    keys = set()
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2 or any(type(item) is not str for item in pair):
            raise TypeError(name + '需要原生文本二元tuple')
        require_text(pair[0], name + '.key')
        require_text(pair[1], name + '.value')
        if pair[0] in keys:
            raise ValueError(name + '键重复')
        keys.add(pair[0])
        if hashes:
            _sha256(pair[1], name + '.sha256')


@dataclass(frozen=True)
class CANUnitCheck:
    """保原声明单位及同次DBC单位；verified只表示非空原文本完全相同。"""

    alias: str  # 同一运行signal_bindings中的简单别名，不是DBC信号名称。
    input_unit: str  # 原解码输入单位，不是额外线性转换后的输出单位。
    dbc_unit: str | None  # 同次公开signal.unit原值，None/空字符串均原样保留。
    status: str  # verified或declared；不表示物理测量已验。

    def __post_init__(self):
        """校验单位比较事实，不去空格、换算或重复施加DBC缩放。

        参数: 无。返回: None。异常: TypeError/ValueError为字段类型或状态与原单位冲突。
        """
        require_identifier(self.alias, 'can_unit.alias')
        require_text(self.input_unit, 'can_unit.input_unit')
        if self.dbc_unit is not None and type(self.dbc_unit) is not str:
            raise TypeError('can_unit.dbc_unit需要str或None')
        if type(self.status) is not str or self.status not in ('verified', 'declared'):
            raise ValueError('CAN单位状态仅verified/declared')
        missing = self.dbc_unit is None or self.dbc_unit == ''
        if self.status == 'verified' and (missing or self.dbc_unit != self.input_unit):
            raise ValueError('verified需要非空DBC单位与原input_unit完全相同')
        if self.status == 'declared' and not missing:
            raise ValueError('declared仅用于DBC单位None或空字符串')


@dataclass(frozen=True)
class CANFrameFormatNotice:
    """保存DBC声明FD但选中实际经典CAN的有限提示，不证明任意原帧均匹配。

    alias关联本次实际信号声明，其余字段完整保存原定位和同次DBC帧型。
    仅单向差异合法；真实帧仍由读取层原通道/ID/标准/FD校验，不改变原帧。
    """

    alias: str  # 同次实际signal_bindings简单别名。
    channel: int  # 原定位通道，不冒称DBC能证明物理通道。
    signal: str  # 同次DBC核对的原信号名称，保全文。
    frame_id: int  # 与原显式定位一致的数值报文ID。
    is_extended: bool  # 原标准/扩展定位；本兼容不放宽该项。
    dbc_is_fd: bool  # 同次DBC声明，唯一允许值为原生True。
    requested_is_fd: bool  # 显式或自动识别得到经典CAN，唯一允许False；不改写原帧。
    code: str = 'dbc_fd_classic_selector'  # 稳定机器码，不接受其他自由兼容政策。

    def __post_init__(self):
        """核固定提示及原定位类型，不访问DBC或把声明当实际帧转换。

        参数: 无。返回: None。异常: TypeError/ValueError为非法类型、方向或固定code。
        """
        require_identifier(self.alias, 'can_frame_format.alias')
        LegacyCANField(self.channel, self.signal, self.frame_id,
                       self.is_extended, self.requested_is_fd)
        if type(self.dbc_is_fd) is not bool or type(self.is_extended) is not bool:
            raise TypeError('DBC帧型提示需要原生bool')
        if self.dbc_is_fd is not True or self.requested_is_fd is not False:
            raise ValueError('仅兼容DBC FD声明与显式经典CAN定位')
        if type(self.code) is not str or self.code != 'dbc_fd_classic_selector':
            raise ValueError('CAN帧型提示code非法')


@dataclass(frozen=True)
class CANSourceMetadata:
    """保存一条真实read的有限事实；内部模型校验不认证实际读取或资源释放。"""

    source: str  # 同计划安全来源名。
    session_id: str  # 同次分析会话，运行清单另核会话归属。
    legacy_profile: str  # 固定sclicer-functions-v1。
    path: str  # 原单BLF路径文本，不在元数据模型中resolve。
    dbc_path: str  # 同次原load_file路径，不是DBC内容哈希。
    channel: int  # 明确单通道，非负原生int。
    read_identity: str  # 同次实际read身份，不与随机运行ID或物理行号混淆。
    worker_pid: int  # 实际子进程正整数PID，不能用bool表示。
    frame_count: int  # 原yield总数，不是投影信号样本数。
    first_ns: int | None  # 原帧映射后首坐标；空来源为None。
    last_ns: int | None  # 原帧映射后末坐标；不伪造请求domain的终点。
    raw_store_path: str | None  # 本次封口原始帧暂存路径；计划不需原帧导出时为None。
    raw_store_sha256: str | None  # 仅实际保存原帧时给整流SHA，不冒充原BLF或DBC的SHA。
    raw_spool_bytes: int  # 本raw_store累计预留字节，不是RSS或已归还磁盘。
    dependency_versions: tuple[tuple[str, str], ...]  # 同次READY版本事实，键唯一。
    vendor_sha256: tuple[tuple[str, str], ...]  # 同次三原模块证据，键唯一、值为SHA。
    unit_checks: tuple[CANUnitCheck, ...]  # 每别名单位事实，不能重复别名。
    frame_format_notices: tuple[CANFrameFormatNotice, ...] = ()  # 无差异保空，不新增旧序列化键或费用。
    decode_scope: str = 'all'  # 默认不新增旧清单键；requested由同次READY认证。
    decode_frame_ids: tuple[int, ...] = ()  # requested实际固定ID集合，覆盖本次所需字段和触发报文。
    decoded_values_policy: str = 'all_values-v1'  # 旧全字段默认不加清单键；按需只传实际所需字段。
    input_check: str = 'full'  # 旧记录默认完整检查，新策略由实际READY确认。
    time_scope: str = 'source'  # none/selected/source，首末范围不可混称。
    check_policy_version: str | None = None  # 仅新按需策略给版本。
    retained_record_count: int | None = None  # 实际保留原记录数。
    full_check_count: int = 0  # 非原生输入完整检查回退数。
    selected_first_ns: int | None = None  # 仅selected提供目标首时间。
    selected_last_ns: int | None = None  # 目标末时间，不是文件末时间。

    def __post_init__(self):
        """核标识、计数/首末、摘要及冻结子记录，不访问原输入或暂存。

        参数: 无。返回: None。异常: TypeError/ValueError为类型、范围或内部事实冲突，
            OverflowError为非空首末超int64；不把声明校验写成实际EOF/哈希验证成功。
        """
        require_identifier(self.source, 'can_source.source')
        require_identifier(self.session_id, 'can_source.session_id')
        for name in ('path', 'dbc_path', 'read_identity'):
            require_text(getattr(self, name), 'can_source.' + name)
        if type(self.legacy_profile) is not str or self.legacy_profile != PROFILE_ID:
            raise ValueError('CAN清单仅支持sclicer-functions-v1')
        _integer(self.channel, 'can_source.channel')
        _integer(self.worker_pid, 'can_source.worker_pid', 1)
        _integer(self.frame_count, 'can_source.frame_count')
        _integer(self.raw_spool_bytes, 'can_source.raw_spool_bytes')
        # 明确记录实际解码范围；bool与int相等不能被tuple比较误当成同一策略。
        if type(self.decode_scope) is not str or self.decode_scope not in ('all', 'requested'):
            raise ValueError('CAN解码方式仅all/requested')
        if (type(self.decode_frame_ids) is not tuple or len(self.decode_frame_ids) > 4096
                or any(type(value) is not int or not 0 <= value <= 0x1fffffff for value in self.decode_frame_ids)):
            raise TypeError('CAN固定解码集合需至多4096个29位原生整数的tuple')
        if (any(left >= right for left, right in zip(self.decode_frame_ids, self.decode_frame_ids[1:]))
                or self.decode_scope == 'all' and self.decode_frame_ids):
            raise ValueError('CAN固定解码ID需严格递增，all不另设固定集合')
        # 原requested历史可以保全字段；新字段投影必须明确声明，不能冒称all。
        if (type(self.decoded_values_policy) is not str
                or self.decoded_values_policy not in ('all_values-v1', 'requested_fields-v1')):
            raise ValueError('CAN解码字段策略仅all_values-v1/requested_fields-v1')
        if self.decode_scope == 'all' and self.decoded_values_policy != 'all_values-v1':
            raise ValueError('all解码方式必须保留all_values-v1字段策略')
        # 空来源不制造零长实际观测；非空真实单点可first==last，保int64原坐标。
        if self.input_check not in ('auto', 'full') or self.time_scope not in ('none', 'selected', 'source'):
            raise ValueError('CAN实际检查/时间范围非法')
        if self.input_check == 'full' and self.time_scope != 'source':
            raise ValueError('完整检查必须提供全来源时间范围')
        if self.input_check == 'auto' and self.check_policy_version != 'demand-check-v1':
            raise ValueError('按需检查需要明确策略版本')
        if self.retained_record_count is not None:
            _integer(self.retained_record_count, 'can_source.retained_record_count')
            if self.retained_record_count > self.frame_count:
                raise ValueError('保留记录数超过原读取数')
        _integer(self.full_check_count, 'can_source.full_check_count')
        if self.full_check_count > self.frame_count:
            raise ValueError('完整回退数超过原读取数')
        if self.time_scope != 'selected' and (self.selected_first_ns is not None or self.selected_last_ns is not None):
            raise ValueError('只有目标时间模式能声明目标首末')
        if self.time_scope != 'source':
            if self.first_ns is not None or self.last_ns is not None:
                raise ValueError('未采集全部时间不能声明全来源首末')
            if self.time_scope == 'selected':
                if not self.retained_record_count:
                    # 没有目标记录（或没有已核实的目标计数）不能制造目标时间范围。
                    if self.selected_first_ns is not None or self.selected_last_ns is not None:
                        raise ValueError('没有目标记录不能声明目标首末时间')
                else:
                    require_int64_ns(self.selected_first_ns)
                    require_int64_ns(self.selected_last_ns)
                    if self.selected_first_ns > self.selected_last_ns:
                        raise ValueError('目标时间首末回退')
        elif self.frame_count == 0:
            if self.first_ns is not None or self.last_ns is not None:
                raise ValueError('空CAN来源首末必须None')
        else:
            if type(self.first_ns) is not int or type(self.last_ns) is not int:
                raise TypeError('非空CAN首末需要原生int64')
            require_int64_ns(self.first_ns, 'can_source.first_ns')
            require_int64_ns(self.last_ns, 'can_source.last_ns')
            if self.first_ns > self.last_ns:
                raise ValueError('CAN首坐标不能晚于末坐标')
        # 不保存原帧是计划明确选择的事实；不能填假路径或空文件SHA冒充已保存。
        # 三项必须同时表示未保存，实际保留的仓仍严格检查原路径和摘要。
        if self.raw_store_path is None:
            if self.raw_store_sha256 is not None or self.raw_spool_bytes != 0:
                raise ValueError('未保存原帧时路径/SHA必须为None且原帧暂存费用为0')
        else:
            require_text(self.raw_store_path, 'can_source.raw_store_path')
            _sha256(self.raw_store_sha256, 'can_source.raw_store_sha256')
        _pairs(self.dependency_versions, 'can_source.dependency_versions')
        _pairs(self.vendor_sha256, 'can_source.vendor_sha256', hashes=True)
        if type(self.unit_checks) is not tuple or any(type(item) is not CANUnitCheck for item in self.unit_checks):
            raise TypeError('CAN单位清单需要CANUnitCheck tuple')
        if len({item.alias for item in self.unit_checks}) != len(self.unit_checks):
            raise ValueError('CAN单位清单别名重复')
        if (type(self.frame_format_notices) is not tuple
                or any(type(item) is not CANFrameFormatNotice for item in self.frame_format_notices)):
            raise TypeError('CAN帧型提示需要冻结CANFrameFormatNotice tuple')
        aliases = {item.alias for item in self.unit_checks}
        if (len({item.alias for item in self.frame_format_notices}) != len(self.frame_format_notices)
                or any(item.alias not in aliases or item.channel != self.channel for item in self.frame_format_notices)):
            raise ValueError('CAN帧型提示不能重复、跨来源通道或引用未知别名')
