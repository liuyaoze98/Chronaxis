"""保存原始片段索引并复制已生成的BLF，不重新调用旧读写或解码路径。

输入是实际Segment范围、已关闭的BLF文件及其明确摘要，输出是连续编号的有界
JSONL索引和发布目录内的逐文件副本。exported保留正长actual，即使文件含零帧；
empty_range保留已知零长度actual；no_observation仅用于actual为None，不造空文件。
append核实际BLF字节/SHA后写索引；seal真正关闭writer才开放独立reader。reader只有
完整EOF、流SHA/数量与真实关闭均成功后才verified_eof，提前关闭不能证明完整。

所有新增RAM与索引spool先预约，原BLF由旧writer封装预约，本模块不重复计算。
copy_to只逐条读索引、有限块复制和核现成BLF；发布副本不计入分析暂存配额。
输出失败只清本次复制资源，保sealed输入与其他reader，恢复后可向新目录重试；
原索引或原BLF内容损坏仍使输入仓failed，不把坏输入当作可发布结果。
所有真实FD、未返回reader和费用槽由本store可达，关闭失败可重试，保原异常/取消
及最高raw_export_store_cleanup_owner；文件与累计spool保留，不凭共享余额补账。
本模块只依赖标准库、冻结模型和有界JSON，不导入CAN库，不声称整进程RSS受限。
"""

# 固定模型与有界编码不触及原日志/DBC；资源交易复用新结果层已经验证的协议。
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from re import fullmatch
from ..core.models import Interval
from ..core.validation import require_identifier
from ..legacy.records import MAX_WIRE_BYTES, encode_packet, decode_packet
from ..timebase.conversion import INT64_MAX, require_int64_ns
from .budget import ResourceBudget
from .errors import ResultClosedError, ResultFormatError
from .spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram


_FIELDS = ('index', 'source', 'session_id', 'segment_id', 'window_id', 'requested',
           'actual', 'frame_count', 'file_name', 'sha256', 'byte_count', 'status', 'device_label')
_ROW_COST = 65536 + 64 * MAX_WIRE_BYTES
_CHUNK_BYTES = 65536
_IO_COST = 8 * _CHUNK_BYTES
_MAX_INDEX = 999999999999


def _integer(value, name, maximum=INT64_MAX):
    """校验非负原生整数，不把bool或浮点作为数量。

    参数: value候选；name错误位置；maximum含端点上限。返回: 原int。
    异常: TypeError/ValueError为类型或范围错误；不截断、不转换。
    """
    if type(value) is not int:
        raise TypeError(name + '需要原生int')
    if not 0 <= value <= maximum:
        raise ValueError(name + '超出允许范围')
    return value


def _text(value, name, *, identifier=False):
    """检查有界安全原文本，保留大小写、Unicode和合法ID标点。

    参数: value原文本；name位置；identifier要求来源/会话简单名。返回: 原str。
    异常: TypeError/ValueError为非原生str、空白、控制字符、过长或名称非法。
    """
    if type(value) is not str:
        raise TypeError(name + '需要原生str')
    if not value.strip() or len(value) > MAX_WIRE_BYTES or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(name + '为空、含控制字符或超过有界文本能力')
    if identifier:
        require_identifier(value, name)
    return value


def _interval(value, name):
    """要求冻结Interval及原生int64端点，不重建或改变原范围。

    参数: value范围；name位置。返回: 原Interval。
    异常: TypeError/ValueError/OverflowError为类型、顺序或整数范围非法。
    """
    if type(value) is not Interval:
        raise TypeError(name + '需要Interval')
    for endpoint in (value.start_ns, value.end_ns):
        if type(endpoint) is not int:
            raise TypeError(name + '端点需要原生int64')
        require_int64_ns(endpoint, name)
    require_int64_ns(value.end_ns - value.start_ns, name + '.duration')
    if value.end_ns < value.start_ns:
        raise ValueError(name + '不能反向')
    return value


def _packet(record):
    """把固定模型转为固定JSON树，不复制文件内容或任意元数据。

    参数: record为RawExportRecord。返回: 仅13字段dict。
    异常: 内部模型属性错误传播；调用者另核整包64KiB上限。
    """
    result = {name: getattr(record, name) for name in _FIELDS}
    for name in ('requested', 'actual'):
        interval = result[name]
        result[name] = None if interval is None else dict(start_ns=interval.start_ns, end_ns=interval.end_ns)
    return result


@dataclass(frozen=True)
class RawExportRecord:
    """保存一个原片段导出事实；构造校声明，不据此宣称文件已读取或写出。"""

    index: int  # 从0连续；对应唯一12位文件名，非业务排序键。
    source: str  # 同一store的CAN来源安全名。
    session_id: str  # 原会话安全名。
    segment_id: str  # 实际Segment的原ID。
    window_id: str  # 产生原片段的窗口ID。
    requested: Interval  # 保留完整原请求范围。
    actual: Interval | None  # 原实际交集；已知点与无观测严格区分。
    frame_count: int  # 原writer成功交付的帧数；正长范围可为0。
    file_name: str | None  # exported固定为raw_segments/12位.blf。
    sha256: str | None  # 实际输出BLF字节SHA，不是原输入SHA。
    byte_count: int  # 实际输出文件字节数。
    status: str  # exported/empty_range/no_observation。
    device_label: str  # 本条产生设备标签，与store严格一致。

    def __post_init__(self):
        """检查数量、身份、范围和文件状态的闭合关系，整条记录有界。

        参数: 无，读取冻结字段。返回: None。
        异常: TypeError/ValueError/OverflowError为非法事实；不打开、stat或创建文件。
        """
        _integer(self.index, 'raw_export.index', _MAX_INDEX)
        _integer(self.frame_count, 'raw_export.frame_count')
        _integer(self.byte_count, 'raw_export.byte_count')
        for name in ('source', 'session_id', 'segment_id', 'window_id', 'device_label'):
            _text(getattr(self, name), name, identifier=name in ('source', 'session_id'))
        _interval(self.requested, 'raw_export.requested')
        if self.actual is not None:
            _interval(self.actual, 'raw_export.actual')
            if self.actual.start_ns < self.requested.start_ns or self.actual.end_ns > self.requested.end_ns:
                raise ValueError('raw_export.actual必须落在原requested内')
        if type(self.status) is not str or self.status not in ('exported', 'empty_range', 'no_observation'):
            raise ValueError('原始导出状态非法')
        if self.status == 'exported':
            if self.actual is None or self.actual.start_ns == self.actual.end_ns:
                raise ValueError('exported需正长实际范围')
            if type(self.file_name) is not str or self.file_name != f'raw_segments/{self.index:012d}.blf':
                raise ValueError('原始导出文件名必须对应当前连续索引')
            if type(self.sha256) is not str or fullmatch(r'[0-9a-fA-F]{64}', self.sha256) is None:
                raise ValueError('原始导出SHA需64位十六进制')
        else:
            expected = self.actual is None if self.status == 'no_observation' else self.actual is not None and self.actual.start_ns == self.actual.end_ns
            if not expected or self.file_name is not None or self.sha256 is not None or self.frame_count or self.byte_count:
                raise ValueError('无观测/零范围必须保原actual且不得带文件、SHA或帧字节数')
        # 在模型边界按现有wire能力校整包，避免多个单独合法长文本拼成无界行。
        if len(encode_packet(_packet(self))) + 1 > MAX_WIRE_BYTES:
            raise ValueError('原始导出索引行超过64KiB')


def _decode(payload):
    """严格还原一条固定索引，不接受多键、重复JSON键或浮点端点。

    参数: payload为不含换行的有限bytes。返回: RawExportRecord。
    异常: ResultFormatError保留底层结构/类型/时间校验原因；取消原样传播。
    """
    try:
        value = decode_packet(payload)
        if set(value) != set(_FIELDS):
            raise ValueError('原始导出索引字段缺失或多余')
        for name in ('requested', 'actual'):
            interval = value[name]
            if interval is None and name == 'actual':
                continue
            if type(interval) is not dict or set(interval) != {'start_ns', 'end_ns'}:
                raise ValueError('索引范围必须精确含start_ns/end_ns')
            if type(interval['start_ns']) is not int or type(interval['end_ns']) is not int:
                raise TypeError('索引范围端点必须为原生int')
            value[name] = Interval(interval['start_ns'], interval['end_ns'])
        return RawExportRecord(**value)
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise ResultFormatError('原始导出索引行非法: ' + str(exc)) from exc


def _write_all(handle, payload):
    """完整写有限bytes，短写继续，零写或非法返回立即失败。

    参数: handle真实无缓冲FD；payload有限bytes。返回: None。
    异常: 原write/取消或OSError；费用由调用方先预约，不在此重复计算。
    """
    view = memoryview(payload)
    while view:
        written = handle.write(view)
        if type(written) is not int or not 0 < written <= len(view):
            raise OSError('原始导出文件写入未正确推进')
        view = view[written:]


class RawExportStore:
    """拥有索引、活reader与当前复制FD；状态与真实closed事实分别记录。

    building只可append/seal；sealed可独立回读或重复copy。构建或输入完整性失败
    转failed；普通复制输出失败仅恢复本次资源。关闭中只允许重试close，不丢槽。
    """

    format = 'blf'

    def __init__(self, budget, work_dir, source, session_id, device_label='pending'):
        """先付固定费用，再在全新根独占创建目录和索引writer。

        参数: budget为借用ResourceBudget；work_dir为全新str/Path；source/session_id
            为安全名；device_label为有界原标签，默认pending。
        返回: building仓。异常: 原声明/路径/预算/IO/取消；持续清理失败附最高恢复owner。
        """
        if not isinstance(budget, ResourceBudget) or not isinstance(work_dir, (str, Path)):
            raise TypeError('原始导出仓需ResourceBudget及显式新目录')
        _text(source, 'raw_exports.source', identifier=True)
        _text(session_id, 'raw_exports.session_id', identifier=True)
        _text(device_label, 'raw_exports.device_label')
        if sum(len(part) for part in Path(work_dir).parts) > MAX_WIRE_BYTES:
            raise ValueError('原始导出工作路径超过有界能力')
        self.budget = self._budget = budget
        self.source, self.session_id, self.device_label = source, session_id, device_label
        self.path = self.inventory_path = self._raw_path = None
        self._writer = self._pending_reader = self._copy_reader = None
        self._input_fd = self._output_fd = self._inventory_fd = None
        self._readers = self._digest = self._payload = self._chunk = None
        self._fixed_cost = self._append_cost = self._io_cost = self._copy_cost = self._held_cost = 0
        self._spool_bytes = self.inventory_bytes = self.record_count = self.file_count = 0
        self.sha256 = None
        self.state, self._closed, self._closing = 'building', False, False
        try:
            # 路径/来源标签及活reader登记均有固定费用，首笔后取消也可从完整槽恢复。
            requested = Path(work_dir)
            _reserve_owned_ram(self, 65536 + 32 * (len(str(requested)) + len(source) + len(session_id) + len(device_label)), '_fixed_cost')
            resolved = requested.resolve()
            resolved.mkdir(parents=True, exist_ok=False)
            self.path, self._raw_path = resolved, resolved / 'raw_segments'
            self._raw_path.mkdir(exist_ok=False)
            self.inventory_path = resolved / 'raw_segments.jsonl'
            self._readers, self._digest = set(), sha256()
            self._writer = self.inventory_path.open('xb', buffering=0)
        except BaseException as exc:
            self._fail(exc)
            raise

    @property
    def closed(self):
        """读取真实关闭事实。参数: 无。返回: bool。异常: 无，FD或费用未清不为True。"""
        return self._closed

    @property
    def spool_bytes(self):
        """读取仅本索引新增的累计配额。参数: 无。返回: int。异常: 无，不含BLF或发布副本。"""
        return self._spool_bytes

    def _require(self, state):
        """检查活状态，半关闭或失败前缀不能继续使用。

        参数: state为building/sealed。返回: None。异常: ResultClosedError/RuntimeError。
        """
        if self._closed or self._closing:
            raise ResultClosedError('原始导出仓已关闭或正在清理')
        if self.state != state:
            raise RuntimeError('原始导出仓状态不允许操作: ' + self.state)

    def _fail(self, exc):
        """保原主错/取消、failed状态和最高恢复owner，清理副错只记note。

        参数: exc为实际主异常。返回: None。异常: 清理错误不替代原exc。
        """
        self.state = 'failed'
        exc.raw_export_store_cleanup_owner = self
        _cleanup_owner(self, exc, 'raw_export_store_cleanup_owner', '原始导出仓')

    def next_path(self):
        """计算当前记录对应BLF路径，不创建文件、不跳过无观测索引。

        参数: 无。返回: 根/raw_segments/{record_count:012d}.blf。
        异常: 状态错误或索引超过12位能力；原writer由调用方独立持有和关闭。
        """
        self._require('building')
        _integer(self.record_count, 'raw_exports.record_count', _MAX_INDEX)
        return self._raw_path / f'{self.record_count:012d}.blf'

    def _relation(self, record, index):
        """核本仓归属和连续索引，不从文件名猜来源。

        参数: record为冻结记录；index为当前预期号。返回: None。异常: TypeError/ValueError。
        """
        if type(record) is not RawExportRecord:
            raise TypeError('原始导出仓仅接受RawExportRecord')
        if (record.index != index or record.source != self.source or record.session_id != self.session_id
                or record.device_label != self.device_label):
            raise ValueError('原始导出记录索引/来源/会话/设备不属于本仓')

    def _close_fd(self, slot):
        """真实FD关闭后才撤槽，关闭后抛错也依据actual.closed处理。

        参数: slot为本owner固定FD槽。返回: None。异常: 原close/取消，持续失败可重试。
        """
        handle = getattr(self, slot)
        if handle is not None:
            try:
                handle.close()
            finally:
                if handle.closed:
                    setattr(self, slot, None)

    def _file(self, record, destination=None):
        """有限块核实际BLF；可同时复制到独占目标，不调用任何CAN读写器。

        参数: record为exported记录；destination为None或新文件Path。返回: None。
        异常: 原预算/IO/取消或ResultFormatError；所有当前FD仍从本store可达。
        """
        if self._input_fd is not None or self._output_fd is not None or self._io_cost:
            raise ResultClosedError('原始导出仓有未完成文件资源待清理')
        _reserve_owned_ram(self, _IO_COST, '_io_cost')
        try:
            self._input_fd = (self.path / record.file_name).open('rb', buffering=0)
        except FileNotFoundError as exc:
            # 索引已指明存在的原件消失是输入失效；不能当成本次发布目录错误重试。
            self._fail(exc)
            raise
        if destination is not None:
            self._output_fd = destination.open('xb', buffering=0)
        digest, count = sha256(), 0
        # 原件和副本同时只持一个块；超过声明字节立即拒绝，不扫无界额外后缀。
        while True:
            self._chunk = self._input_fd.read(_CHUNK_BYTES)
            if not self._chunk:
                break
            count += len(self._chunk)
            if count > record.byte_count:
                exc = ResultFormatError('原始BLF字节数超过索引')
                self._fail(exc)
                raise exc
            digest.update(self._chunk)
            if self._output_fd is not None:
                _write_all(self._output_fd, self._chunk)
        if count != record.byte_count or digest.hexdigest() != record.sha256.lower():
            exc = ResultFormatError('原始BLF字节数或SHA与索引不符')
            self._fail(exc)
            raise exc
        if self._output_fd is not None:
            self._output_fd.flush()
        self._close_fd('_output_fd')
        self._close_fd('_input_fd')
        # 发布字节也以真实文件回读核验，不能只凭write返回长度宣称副本正确。
        if destination is not None:
            self._check_copy(destination, record.byte_count, record.sha256)
        self._chunk = None
        _release_owned_ram(self, self._io_cost, '_io_cost')

    def _check_copy(self, path, expected_bytes, expected_sha):
        """在已预约IO空间内回读真实发布文件，BLF与索引使用同一有界验证。

        参数: path为本次新目标Path；expected_bytes/SHA为已封口原事实。返回: None。
        异常: 原打开/read/close/取消或ResultFormatError；当前真实FD留在本owner槽。
        """
        if self._input_fd is not None or not self._io_cost:
            raise ResultClosedError('发布文件回读需空输入槽和已预约IO空间')
        self._input_fd = path.open('rb', buffering=0)
        digest, count = sha256(), 0
        while True:
            self._chunk = self._input_fd.read(_CHUNK_BYTES)
            if not self._chunk:
                break
            count += len(self._chunk)
            if count > expected_bytes:
                raise ResultFormatError('发布文件字节数超过封口事实')
            digest.update(self._chunk)
        if count != expected_bytes or digest.hexdigest() != expected_sha.lower():
            raise ResultFormatError('发布文件字节数或SHA与封口事实不符')
        self._close_fd('_input_fd')
        self._chunk = None

    def append(self, record):
        """预付索引RAM/累计spool，核实际文件后完整写一行再推进计数。

        参数: record为本仓当前索引的RawExportRecord。返回: None。
        异常: 原归属/预算/文件/编码/取消；开始后的失败poison，原BLF费用不重复预约。
        """
        self._require('building')
        try:
            self._relation(record, self.record_count)
            _reserve_owned_ram(self, _ROW_COST, '_append_cost')
            self._payload = encode_packet(_packet(record)) + b'\n'
            before = self._budget.spool_bytes
            try:
                self._budget.reserve_spool(len(self._payload))
            finally:
                if self._budget.spool_bytes == before + len(self._payload):
                    self._spool_bytes += len(self._payload)
            if record.status == 'exported':
                self._file(record)
            _write_all(self._writer, self._payload)
            self._digest.update(self._payload)
            self.inventory_bytes += len(self._payload)
            self.record_count += 1
            self.file_count += int(record.status == 'exported')
            self._payload = None
            _release_owned_ram(self, self._append_cost, '_append_cost')
        except BaseException as exc:
            self._fail(exc)
            raise

    def seal(self):
        """真实关闭索引writer并固定流SHA；零记录亦可封口。

        参数: 无。返回: None。异常: 原flush/close/取消，失败不能冒充sealed。
        """
        self._require('building')
        try:
            self._writer.flush()
            self._close_fd('_writer')
            self.sha256, self.state = self._digest.hexdigest(), 'sealed'
        except BaseException as exc:
            self._fail(exc)
            raise

    def iter_records(self):
        """创建有限独立索引reader，未返回构造始终在本父pending槽可达。

        参数: 无。返回: 逐条RawExportRecord迭代器。异常: 原预算/打开/登记/取消及状态错误。
        """
        self._require('sealed')
        if self._pending_reader is not None:
            raise ResultClosedError('原始导出仓有未返回reader待清理')
        try:
            reader = _RawExportReader(self)
            self._pending_reader = None
            return reader
        except BaseException as exc:
            self._fail(exc)
            raise

    def copy_to(self, destination):
        """向新发布根独占创建原始目录与索引，逐条核验复制现成BLF。

        参数: destination为Path；根可已有普通结果表，raw_segments及索引必须均不存在。
        返回: 目标raw_segments.jsonl Path。异常: 原路径/预算/IO/取消或完整性错误；
            输出失败保本次FD责任及部分文件，不覆盖已有工件或关闭sealed输入；
            入口先恢复上次复制，持续关闭失败时不得覆盖旧槽或创建下个目标。
        """
        self._require('sealed')
        self.recover_copy()
        if not isinstance(destination, Path):
            raise TypeError('原始导出发布根需要Path')
        if sum(len(part) for part in destination.parts) > MAX_WIRE_BYTES:
            raise ValueError('原始导出发布路径超过有界能力')
        target = destination.resolve()
        raw_path, inventory = target / 'raw_segments', target / 'raw_segments.jsonl'
        if raw_path.exists() or inventory.exists():
            raise FileExistsError('原始导出发布目录或索引已存在')
        try:
            _reserve_owned_ram(self, _ROW_COST + 32 * len(str(target)), '_copy_cost')
            target.mkdir(parents=True, exist_ok=True)
            raw_path.mkdir(exist_ok=False)
            self._inventory_fd = inventory.open('xb', buffering=0)
            # 本次临时reader先装独立copy槽；其预约/关闭取消不破坏其他已封口输入。
            self._copy_reader = _RawExportReader(self, copy=True)
            digest, count, files = sha256(), 0, 0
            # reader只交付当前一行；不累计文件路径或导出记录列表。
            for record in self._copy_reader:
                if record.status == 'exported':
                    self._file(record, target / record.file_name)
                    files += 1
                self._payload = encode_packet(_packet(record)) + b'\n'
                _write_all(self._inventory_fd, self._payload)
                digest.update(self._payload)
                self._payload = None
                count += 1
            if (not self._copy_reader.verified_eof or count != self.record_count
                    or files != self.file_count or digest.hexdigest() != self.sha256):
                exc = ResultFormatError('原始导出复制索引未完整匹配封口事实')
                self._fail(exc)
                raise exc
            self._copy_reader = None
            self._inventory_fd.flush()
            self._close_fd('_inventory_fd')
            _reserve_owned_ram(self, _IO_COST, '_io_cost')
            self._check_copy(inventory, self.inventory_bytes, self.sha256)
            _release_owned_ram(self, self._io_cost, '_io_cost')
            _release_owned_ram(self, self._copy_cost, '_copy_cost')
            return inventory
        except BaseException as exc:
            # 输入reader或原BLF摘要错误可已poison父；输出故障只收回本次复制责任。
            exc.raw_export_store_cleanup_owner = self
            for attempt in range(2):
                try:
                    self._close_copy_resources()
                    break
                except BaseException as cleanup:
                    exc.add_note(f'原始导出复制清理第{attempt + 1}次失败: {type(cleanup).__name__}')
            raise

    def recover_copy(self):
        """仅恢复上次输出复制的真实责任，保sealed固定输入及其他独立reader。

        参数: 无。返回: None；copy_to入口会自动调用，调用方也可显式恢复。
        异常: 原FD/reader/费用关闭错误或状态错误；持续失败保最高store与原槽，
            不把整个输入仓置关闭中，不覆盖上次复制尚未释放的资源。
        """
        self._require('sealed')
        self._close_copy_resources()

    def _close_copy_resources(self):
        """关闭本次copy子reader和FD，完全释放后再清当前缓冲与复制费用。

        参数: 无。返回: None；不操作固定费、原索引writer或其他独立reader。
        异常: 首个真实关闭/抵销错误，副错记note；最高store保存未完成实际槽。
        """
        failure = None
        if self._copy_reader is not None:
            try:
                self._copy_reader.close()
            except BaseException as exc:
                failure = exc
            finally:
                if self._copy_reader.closed:
                    self._copy_reader = None
        for slot in ('_input_fd', '_output_fd', '_inventory_fd'):
            try:
                self._close_fd(slot)
            except BaseException as exc:
                if failure is None:
                    failure = exc
                else:
                    failure.add_note('原始导出本次复制FD关闭附加失败: ' + type(exc).__name__)
        if self._copy_reader is None and all(getattr(self, slot) is None for slot in ('_input_fd', '_output_fd', '_inventory_fd')):
            self._payload = self._chunk = None
            for slot in ('_io_cost', '_copy_cost'):
                try:
                    _release_owned_ram(self, getattr(self, slot), slot)
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                    else:
                        failure.add_note('原始导出本次复制费用抵销附加失败: ' + type(exc).__name__)
        if failure is not None:
            failure.raw_export_store_cleanup_owner = self
            raise failure

    def close(self):
        """关闭全部自有FD/reader并抵销自有RAM，文件与累计spool保留。

        参数: 无。返回: None，完成后幂等。异常: 首个真实关闭/抵销错误，副错记note；
            持续故障保原槽/最高owner，不能从借用账本总额倒推或多扣费用。
        """
        if self._closed:
            return
        self._closing = True
        if self.state == 'building':
            self.state = 'failed'
        failure = None
        # pending与活登记可短暂指向同一真实子；先pending，成功后从登记中解除。
        readers = []
        for reader in (self._pending_reader, self._copy_reader, *tuple(self._readers or ())):
            if reader is not None and reader not in readers:
                readers.append(reader)
        for reader in readers:
            try:
                reader.close()
            except BaseException as exc:
                if failure is None:
                    failure = exc
                else:
                    failure.add_note('原始导出reader关闭附加失败: ' + type(exc).__name__)
        if self._copy_reader is not None and self._copy_reader.closed:
            self._copy_reader = None
        for slot in ('_writer', '_input_fd', '_output_fd', '_inventory_fd'):
            try:
                self._close_fd(slot)
            except BaseException as exc:
                if failure is None:
                    failure = exc
                else:
                    failure.add_note('原始导出FD关闭附加失败: ' + type(exc).__name__)
        if (self._pending_reader is None and not self._readers and self._copy_reader is None
                and all(getattr(self, slot) is None for slot in ('_writer', '_input_fd', '_output_fd', '_inventory_fd'))):
            self._payload = self._chunk = None
            for slot in ('_append_cost', '_io_cost', '_copy_cost', '_fixed_cost'):
                try:
                    _release_owned_ram(self, getattr(self, slot), slot)
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                    else:
                        failure.add_note('原始导出费用抵销附加失败: ' + type(exc).__name__)
            if self._held_cost == 0:
                self._closed = True
        if failure is not None:
            failure.raw_export_store_cleanup_owner = self
            raise failure


class _RawExportReader:
    """拥有单个索引位置/摘要和固定读槽；完整EOF与成功关闭才verified_eof。

    copy模式只把临时资源错误交本次复制恢复，输入格式/摘要破坏仍poison父仓。
    """

    def __init__(self, owner, *, copy=False):
        """先装父pending槽，再付费打开/登记真实reader。

        参数: owner为活sealed仓；copy为内部临时复制模式，直接先装父_copy_reader槽。
        返回: 独立reader。异常: 原预算/打开/登记/取消；真实父槽始终保未返回self。
        """
        self.owner, self._budget = owner, owner.budget
        self._copy = copy
        self.handle = self._digest = None
        self._fixed_cost = self._held_cost = self._count = self._files = self._bytes = 0
        self.closed = self._closing = self.verified_eof = False
        if copy:
            owner._copy_reader = self
        else:
            owner._pending_reader = self
        # 仅索引reader允许8192字节有限预读；buffer/对象另付16384，原行限及真EOF不变。
        # BLF分块复制与写端不改，同一handle始终拥有buffer及真实raw FD。
        _reserve_owned_ram(self, _ROW_COST + 16384, '_fixed_cost')
        self._digest = sha256()
        try:
            self.handle = owner.inventory_path.open('rb', buffering=8192)
        except FileNotFoundError as exc:
            # 普通工厂原已有_fail；copy专用工厂也须把源索引消失归为输入完整性失效。
            if copy:
                owner._fail(exc)
            raise
        owner._readers.add(self)

    def __iter__(self):
        """保持独立原位置。参数: 无。返回: self。异常: 无，不重新开文件。"""
        return self

    def __next__(self):
        """逐行校索引归属/序号，真实EOF核完整SHA、条数、文件数与字节数后关闭。

        参数: 无。返回: RawExportRecord。异常: 真实StopIteration或原格式/关闭/取消；
            输入损坏poison父；copy临时资源失败交本次恢复，原异常/取消对象保持。
        """
        if self.closed:
            raise StopIteration
        self.owner._require('sealed')
        if self._closing:
            raise ResultClosedError('原始导出reader正在清理')
        try:
            payload = self.handle.readline(MAX_WIRE_BYTES + 1)
            if payload:
                if len(payload) > MAX_WIRE_BYTES or not payload.endswith(b'\n'):
                    raise ResultFormatError('原始导出索引行超限或缺完整换行')
                if self._count >= self.owner.record_count:
                    raise ResultFormatError('原始导出索引出现额外后缀')
                record = _decode(payload[:-1])
                try:
                    self.owner._relation(record, self._count)
                except (TypeError, ValueError) as exc:
                    raise ResultFormatError('原始导出索引归属或序号非法') from exc
                self._digest.update(payload)
                self._count += 1
                self._files += int(record.status == 'exported')
                self._bytes += len(payload)
                return record
            if (self._count != self.owner.record_count or self._files != self.owner.file_count
                    or self._bytes != self.owner.inventory_bytes or self._digest.hexdigest() != self.owner.sha256):
                raise ResultFormatError('原始导出索引EOF数量或SHA不匹配')
            self.close()
        except BaseException as exc:
            if not self._copy or isinstance(exc, ResultFormatError):
                self.owner._fail(exc)
            else:
                exc.raw_export_store_cleanup_owner = self.owner
            raise
        self.verified_eof = True
        raise StopIteration

    def close(self):
        """真实关FD、抵销本笔费用并解除父登记后才closed，可持续重试。

        参数: 无。返回: None。异常: 原close/预算/取消；最高store仍持本实例。
        """
        if self.closed:
            return
        self._closing = True
        try:
            if self.handle is not None and not self.handle.closed:
                self.handle.close()
            _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
            self.owner._readers.discard(self)
            if self.owner._pending_reader is self:
                self.owner._pending_reader = None
            self.closed = True
        except BaseException as exc:
            exc.raw_export_store_cleanup_owner = self.owner
            raise
