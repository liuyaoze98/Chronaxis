"""把同次旧CAN逐帧输出接成预算信号批，保留原始帧与真实观测证明。

adapter构造/describe只检查声明并创建新工作目录，不读BLF/DBC、不启动进程。
独立CANObservationRead首次next才启动CAN读取进程，先复制同次READY并核实际非空DBC单位，
再逐原yield读取；显式all每帧调用一次原parse，仅retain_raw_frames时将全部原帧写入
RawFrameStore。所有原帧计读取数，时间按source/selected/none分别采集，
本层收到的signals是运行实际需要的定义；requested只解码这些字段和消息指标所需ID，
只传输所需值；auto跳过无用途字段与时间，full/source保原完整检查。显式all保留原全解码检查。
当前原帧的匹配别名按全部列样本总和batch_rows拆批；其他报文
不更新此信号，匹配定位但原dict缺key则None→MISSING，不延用旧值或猜DECODE_ERROR。

时间仅原浮点秒convert_time(...,'s')加一次offset。当前ns-1才作为非EOF watermark，
所以同刻后继不会被提前承诺；末次真实EOF交付独立空批，下一次StopIteration前须
确认CAN读取进程退出、raw writer封口、validator结束和本次输入关闭成功，才开放CANObservation。
runtime_metadata保原READY冻结键形状，None/空unit原样表示未核实，不能假verified。
take_raw_store只在完成后一次移交原store；未移交则本read.close负责，不关已移交store。
显式capture_message_updates=True时，同一record在raw追加后另存完整decoded仓，
不在别名拆批处重复捕获。消息仓保同次READY.profile/read_identity和原量化事实，
真EOF才封口；take_message_store同样先安装接收父，再撤本子责任。默认关闭时
不创建消息目录或额外预约，原PULL/parse、字段投影与批次协议保持。

来源/请求/同次元数据、当前原记录、装箱与validator动态去重状态分别先付费。
未返回read及CAN读取进程/raw构造责任均真实安装后再推进，持续清理失败保最高恢复owner；
close可重试且不抵销借款。完成read脱离adapter活登记，事实可活到自身close。
全部只用新分析层和已有pack_decoded两后端，不修改旧链、重复读DBC或声明RSS上限。
batch_read默认自动选择：requested由can_batch_reader接有限批，all保原逐条读取；
显式bool仍覆盖自动选择。未保存raw由公开元数据None/None/0明确表达。
直接累计且没有普通样本请求时，[home]另核两段真实输入字节的SHA256：全部原时间、
所需记录的长度与JSON；selected/none的全时间SHA为None。只借用已严格解包的原包，不重编码或保存副本；真实EOF及
进程关闭后才开放指纹。它不是普通信号样本摘要，read关闭后由接收方自付保留费用。
"""

# 数值归一化复用既有pack；外层只处理实际来源身份、原行进度和资源责任。
from dataclasses import dataclass
import hashlib
from pathlib import Path
from uuid import uuid4
from ..core.binding import SignalDefinition
from ..core.validation import require_identifier, require_text
from ..legacy.process_read import LegacyCANProcessRead
from ..legacy.raw_store import RawFrameStore
from ..legacy.message_store import DecodedMessageStore, MAX_DECODED_MESSAGE_ROW_BYTES
from ..legacy.records import LegacyCANRequest, field_to_dict
from ..legacy.batch_wire import HEADER
from ..legacy.batch_worker import REQUESTED_VALUES_POLICY
from ..results.budget import ResourceBudget
from ..results.errors import ResultClosedError
from ..results.spool import _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from ..sources.can_spec import LegacyCANSpec, CANSourceRef, can_field_from_key
from ..sources.descriptions import describe_fields, source_timebase_identity
from ..sources.models import (ReadRequest, SignalBatch, SourceDescription, SourceCapabilities, freeze_metadata)
from ..sources.packing import pack_decoded
from ..sources.protocol import BatchValidator, SourceClosedError, SourceReadError
from ..timebase.conversion import checked_add_ns, convert_time, require_int64_ns
from .history import _metadata_bytes, _pending_bytes


@dataclass(frozen=True)
class CANObservation:
    """保存本read实际全部yield的完成事实，不接受请求范围作为原行首末。"""

    source: str  # 当前来源名。
    session_id: str  # 原会话。
    request: ReadRequest  # 创建本read的原对象，不按值重建。
    read_identity: str  # 每个read独立UUID。
    first_ns: int | None  # 全部原yield经一次映射的首端，全空为None。
    last_ns: int | None  # 全部原yield经一次映射的末端，全空为None。
    row_count: int  # 包含未知ID/空投影的原yield数，不是样本数。
    source_eof: bool  # 仅真实完整完成为True。
    time_scope: str = 'source'  # source为全来源；selected仅目标；none未采集。
    retained_record_count: int = 0  # 本次实际保留记录数，不等于贡献数。
    full_check_count: int = 0  # 按需策略下非原生输入的完整检查回退数。

    def __post_init__(self):
        """核完成事实结构。参数: 无。返回: None。异常: 类型/会话/端点或EOF矛盾。
        """
        require_identifier(self.source, 'can_observation.source')
        require_identifier(self.session_id, 'can_observation.session_id')
        require_text(self.read_identity, 'can_observation.read_identity')
        if (not isinstance(self.request, ReadRequest) or self.request.session_id != self.session_id
                or type(self.row_count) is not int or self.row_count < 0 or self.source_eof is not True):
            raise ValueError('CAN观测需原请求、非负原行数及完整EOF')
        if self.time_scope not in ('none', 'selected', 'source'):
            raise ValueError('CAN观测时间范围非法')
        if (type(self.retained_record_count) is not int or not 0 <= self.retained_record_count <= self.row_count
                or type(self.full_check_count) is not int or not 0 <= self.full_check_count <= self.row_count):
            raise ValueError('CAN观测保留/完整回退计数非法')
        if self.time_scope == 'none':
            if self.first_ns is not None or self.last_ns is not None:
                raise ValueError('未采集时间不能声明首末')
            return
        if self.row_count == 0 or self.time_scope == 'selected' and not self.retained_record_count:
            if self.first_ns is not None or self.last_ns is not None:
                raise ValueError('空CAN输入没有可猜测首末')
        else:
            require_int64_ns(self.first_ns)
            require_int64_ns(self.last_ns)
            if self.first_ns > self.last_ns:
                raise ValueError('CAN观测时间不能回退')


class BudgetedLegacyCANSourceAdapter:
    """拥有静态来源描述和活read登记，完成read与已移交store由新父负责。"""

    def __init__(self, budget, spec, session_id, signals, *, backend='numpy', work_dir,
                 capture_message_updates=False, batch_read=None, retain_raw_frames=True,
                 input_check='full', time_scope='source',
                 message_frame_ids=None,extra_fields=(), message_consumer=None, cycle_fields=(), metadata_fields=(), message_keys=(),
                 input_fingerprints=True, history_integrity=True, frame_observer=None):
        """先付声明费用，建立显式新工作根但不访问原输入。

        参数: budget为共享ResourceBudget；spec为LegacyCANSpec；session_id为会话；
            signals为SignalDefinition tuple；backend为numpy/reference；work_dir必须全新；
            capture_message_updates为严格bool，默认False，仅显式开启才存同次decoded仓；
            batch_read默认None自动选择：requested为True，all为False；显式bool保持选择，
            requested不能显式False；retain_raw_frames决定是否保存原帧；
            message_frame_ids为需要完整逐消息记录的ID，None保留所有实际返回记录。
            extra_fields只为显式报文重建传递连续量/复用选择器，不生成普通信号别名。
            message_keys为没有数值依赖也须触发的完整报文定位；
            message_consumer可选同步接收共同消息模型；只传signals所需值，保留对象须由消费者另付费用。
            cycle_fields独立请求初始化周期；metadata_fields仅请求字段候选，两者不添加解码值或普通样本。
            frame_observer仅显式导出时接收原帧身份，不保存额外载荷或扫描文件。
            input_fingerprints仅控制可选输入摘要，默认保持旧调用；必要值检查始终执行。
            input_check/time_scope为计划固定的检查和时间范围；低层默认full/source保旧入口。
            spec.decode_scope=requested使用批协议，将实际需要的字段及指标ID固定为解码集合；
            其他帧仍读取并检查原字段/时间，但不再生成或检查其解码值。
        返回: 静态adapter。异常: 原配置/目录/预算/取消；持续清理失败附can_source_cleanup_owner。
        """
        if batch_read is None and type(spec) is LegacyCANSpec:
            batch_read = (spec.decode_scope == 'requested' or len(spec.input_paths) > 1
                          or spec.decode_policy != 'legacy' or bool(cycle_fields) or bool(metadata_fields))
        if (not isinstance(budget, ResourceBudget) or type(spec) is not LegacyCANSpec
                or type(signals) is not tuple or any(type(item) is not SignalDefinition for item in signals)
                or backend not in ('numpy', 'reference') or not isinstance(work_dir, (str, Path))
                or any(type(value) is not bool for value in (capture_message_updates, batch_read, retain_raw_frames, input_fingerprints, history_integrity))
                or message_frame_ids is not None and (type(message_frame_ids) is not tuple
                    or any(type(value) is not int or not 0 <= value <= 0x1fffffff for value in message_frame_ids))):
            raise TypeError('CAN来源需预算、静态spec、定义tuple、后端及新工作目录')
        from ..sources.can_updates import require_message_keys
        require_message_keys(message_keys, channel=spec.channel)
        if message_keys and message_consumer is None:
            raise ValueError('消息触发定位必须有实际消费者')
        if message_keys:
            message_frame_ids = tuple(sorted(set(message_frame_ids or ()) | {key[1] for key in message_keys}))
        if message_consumer is not None and not callable(message_consumer):
            raise TypeError('message_consumer需要同步可调用对象')
        if not batch_read and (len(spec.input_paths) > 1 or spec.decode_policy != 'legacy' or cycle_fields or metadata_fields):
            raise ValueError('连续文件和新解码政策需要批次读取')
        from ..legacy.dbc_cycles import require_cycle_fields
        require_cycle_fields(cycle_fields,spec.channel)
        require_cycle_fields(metadata_fields,spec.channel)
        self._metadata_fields = metadata_fields
        self._cycle_fields = cycle_fields
        self._input_fingerprints_requested = input_fingerprints
        self._history_integrity=history_integrity
        require_identifier(session_id, 'can.session_id')
        from ..legacy.records import LegacyCANField
        if type(extra_fields) is not tuple or len(extra_fields)>4096 or any(type(f) is not LegacyCANField or f.channel!=spec.channel for f in extra_fields):
            raise ValueError('重建字段需要同通道有限LegacyCANField tuple')
        if any(item.source != spec.name for item in signals) or len({item.name for item in signals}) != len(signals):
            raise ValueError('CAN信号来源须匹配且别名唯一')
        self.budget = self._budget = budget
        self.spec, self.session_id, self.signals, self.backend = spec, session_id, signals, backend
        self._capture_message_updates = capture_message_updates
        if input_check not in ('auto', 'full') or time_scope not in ('none', 'selected', 'source'):
            raise ValueError('CAN检查范围或时间范围非法')
        if (input_check == 'full' or spec.decode_scope == 'all' or retain_raw_frames or capture_message_updates) and time_scope != 'source':
            raise ValueError('完整诊断/原帧/消息历史必须保全来源时间')
        self.input_check, self.time_scope = input_check, time_scope
        self._batch_read, self._retain_raw_frames = batch_read, retain_raw_frames
        self._message_frame_ids = message_frame_ids
        # 策略与固定集合只在创建时决定；all不构造集合或增加声明费用。
        self._decode_scope, self._decode_frame_ids = spec.decode_scope, ()
        # 当前消息消费者只接收共同update，不借用read内部的临时原帧槽。
        self._update_consumer = message_consumer
        if frame_observer is not None and not callable(frame_observer):
            raise TypeError('frame_observer需要可调用对象')
        self._frame_observer = frame_observer
        self._update_projection = None
        self.work_dir = self._description = self._definitions = self._fields = None
        self._requests = self._uninstalled_request = None
        self._fixed_cost = self._held_cost = 0
        self.closed = self._closing = False
        try:
            # 仅计静态有限树；解析field JSON/复制描述/创建登记前已覆盖所需空间。
            cost = 65536 + 32 * _metadata_bytes((spec.name, str(spec.path) if len(spec.input_paths)==1 else tuple(str(p) for p in spec.input_paths), str(spec.dbc_path),
                spec.channel, spec.timebase, spec.unit, spec.offset_ns, session_id, signals, str(work_dir)))
            if cycle_fields or metadata_fields:
                cost += 16384 + _metadata_bytes((cycle_fields,metadata_fields))*32
            _reserve_owned_ram(self, cost, '_fixed_cost')
            if extra_fields:
                _reserve_owned_ram(self,65536+64*_metadata_bytes(extra_fields),'_fixed_cost')
            if self._decode_scope == 'requested':
                if not batch_read:
                    raise ValueError('requested来源需要批次读取，batch_read不能为False')
                # 每输入ID覆盖tuple/set/排序及十进制诊断文本；每别名另覆盖scope定位副本。
                # 先付保守上界再解析和创建集合，不按去重后的较小数额追补。
                _reserve_owned_ram(self, 8192 + 256 * (len(signals) + len(message_frame_ids or ()))
                    + 512 * len(signals), '_fixed_cost')
            if message_keys:
                _reserve_owned_ram(self, 8192 + 2048 * len(message_keys), '_fixed_cost')
            parsed = tuple((item, can_field_from_key(item.field)) for item in signals)
            if any(field.channel != spec.channel for _, field in parsed):
                raise ValueError('CAN字段通道必须等于单声明通道')
            self._definitions = parsed
            if message_consumer is not None:
                from ..sources.can_updates import CANUpdateProjection
                self._update_projection = CANUpdateProjection(spec.name, session_id, tuple(field for _, field in parsed), message_keys=message_keys,clock_fields=metadata_fields)
            # 同一定位多别名只在声明元数据去重；默认全解码保持，requested固定集合
            # 由下一分支建立。这里不建立DBC缓存，也不共享目标帧的解码调用。
            self._fields = tuple(dict.fromkeys((*[field for _,field in parsed],*extra_fields)))
            if self._decode_scope == 'requested':
                self._decode_frame_ids = tuple(sorted({field.frame_id for field in self._fields}
                    | set(message_frame_ids or ())))
                if len(self._decode_frame_ids) > 4096:
                    raise ValueError('requested最多声明4096个不同报文ID')
            self._requests = set()
            path = Path(work_dir).resolve()
            if any(part.casefold() == 'refprojects' for part in path.parts):
                raise ValueError('CAN工作目录禁止RefProjects')
            path.mkdir(parents=True, exist_ok=False)
            self.work_dir = path
            locator = {'path': str(spec.path), 'dbc_path': str(spec.dbc_path), 'channel': spec.channel,
                'legacy_profile': spec.legacy_profile, 'time_unit': spec.unit, 'offset_ns': spec.offset_ns,
                'source_timebase_sha256': source_timebase_identity(spec.timebase, spec.offset_ns)}
            if len(spec.input_paths) > 1:
                locator.pop('path')
                locator['paths'] = tuple(str(p) for p in spec.input_paths)
            if spec.decode_policy != 'legacy':
                locator['decode_policy'] = spec.decode_policy
            diagnostics = (('原yield序号/完整原帧/原时间/同次DBC元数据' if retain_raw_frames else
                '全部原yield观测/所需原序号与原时间/同次DBC元数据；未保存原帧副本'),)
            if input_check == 'auto' and time_scope != 'source':
                diagnostics = (('原yield计数/所需原序号与值；未采集时间' if time_scope == 'none' else
                    '原yield计数/所需原序号、值与时间；未采集非目标帧时间') + '/同次DBC元数据；未保存原帧副本',)
            if self._decode_scope == 'requested':
                locator['decode_scope'] = 'requested'
                # 即使没有signal字段，来源级描述也必须绑定完整固定集合而非PULL子投影。
                diagnostics += ('decode_scope=requested;decode_frame_ids='
                    + ','.join(str(value) for value in self._decode_frame_ids),)
            if input_check == 'auto':
                locator.update(input_check=input_check, time_scope=time_scope, check_policy_version='demand-check-v1')
                diagnostics += ('按需检查：time_scope=' + time_scope + '；原生非目标帧仅保留本次要求的ID/时间处理；非原生输入完整检查回退',)
            self._description = SourceDescription(spec.name, describe_fields(spec.name, signals, locator),
                spec.timebase.timebase_id, None, None, SourceCapabilities(True, True, True, False,
                    diagnostics,
                    (('同格式原序BLF/单声明通道；原空dict不能区分解码失败原因' if len(spec.input_paths)>1
                      else '仅单BLF/单声明通道；原空dict不能区分解码失败原因'),
                     '缺DBC单位保持未核实；原始片段仅BLF且由run阶段写出；旧进程RSS未测')),
                legacy_profile=spec.legacy_profile, metadata_status='declared')
        except BaseException as exc:
            _cleanup_owner(self, exc, 'can_source_cleanup_owner', 'CAN来源构造')
            raise

    @property
    def capture_message_updates(self):
        """读取原配置的消息捕获开关，不启动来源或开放完成证明。

        参数: 无。返回: 原生bool，关闭adapter后仍可核原开关。
        异常: 无；只读属性不允许调用方改写活read的捕获来源。
        """
        return self._capture_message_updates

    @property
    def batch_read(self):
        """读取本adapter冻结的批协议选择。参数: 无。返回: bool。异常: 无。"""
        return self._batch_read

    @property
    def retain_raw_frames(self):
        """读取原始帧保存选择。参数: 无。返回: bool。异常: 无，不随关闭改变。"""
        return self._retain_raw_frames

    @property
    def message_frame_ids(self):
        """读取实际消息保留ID。参数: 无。返回: tuple或None。异常: 无。"""
        return self._message_frame_ids

    @property
    def decode_scope(self):
        """读取创建时的解码方式。参数: 无。返回: all/requested。异常: 无。"""
        return self._decode_scope

    @property
    def decode_frame_ids(self):
        """借用已付费的固定解码集合。参数: 无。返回: tuple，close后为空。异常: 无。"""
        return self._decode_frame_ids

    def _ensure_open(self):
        """拒绝关闭中/已关闭。参数: 无。返回: None。异常: SourceClosedError。
        """
        if self.closed or self._closing:
            raise SourceClosedError('CAN来源已关闭或正在清理')

    def describe(self):
        """返回已付费静态描述，不读BLF/DBC或spawn。参数: 无。返回: SourceDescription。
        异常: SourceClosedError为关闭中/已关闭。
        """
        self._ensure_open()
        return self._description

    def iter_batches(self, request):
        """创建独立观测read，首次next才实际输入。参数: request为原ReadRequest。
        返回: CANObservationRead。异常: 原配置/预约/登记错误，持续失败保最高真实owner。
        """
        self._ensure_open()
        if self._uninstalled_request is not None:
            raise SourceClosedError('CAN来源有未返回read待清理')
        try:
            if self.batch_read:
                from .can_batch_reader import CANBatchObservationRead
                read = CANBatchObservationRead(self, request)
            else:
                read = CANObservationRead(self, request)
            self._requests.add(read)
            self._uninstalled_request = None
            return read
        except BaseException as exc:
            read = self._uninstalled_request
            if read is not None:
                read._failed = True
                _cleanup_owner(read, exc, 'can_observation_read_cleanup_owner', 'CAN请求登记')
                if not read.closed:
                    exc.can_source_cleanup_owner = self
            raise

    def iter_batches_with_observation(self, request):
        """使用同一独立read合同。参数: request为原请求。返回: CANObservationRead。
        异常: 与iter_batches相同；不复用adapter全局最后事实或request值map。
        """
        return self.iter_batches(request)

    def close(self):
        """关闭本来源活read及费用，不关闭已完成脱登记read或其新父raw store。

        参数: 无。返回: None，可重试。异常: 首个实际关闭/抵销错误，最高can_source_cleanup_owner。
        """
        if self.closed:
            return
        self._closing = True
        failure = None
        for read in (() if self._uninstalled_request is None else (self._uninstalled_request,)) + tuple(self._requests or ()):
            try:
                read.close()
            except BaseException as exc:
                if failure is None:
                    failure = exc
                else:
                    failure.add_note('CAN其他read关闭附加失败: ' + type(exc).__name__)
        if self._uninstalled_request is None and not self._requests:
            self._description = self._definitions = self._fields = None
            self._decode_frame_ids = ()
            self._update_projection = self._update_consumer = None
            self._frame_observer = None
            self.spec, self.signals = None, ()
            try:
                _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
            except BaseException as exc:
                if failure is None:
                    failure = exc
            if self._held_cost == 0:
                self.closed = True
        if failure is not None:
            failure.can_source_cleanup_owner = self
            raise failure


class CANObservationRead:
    """拥有同次CAN读取进程进程、原帧/可选消息仓及当前帧；事实活到自身close，移交仓归新父。"""

    def __init__(self, owner, request):
        """先安装未返回槽并预付固定树，不实际打开来源。

        参数: owner为预算CAN来源，request为同会话原ReadRequest。返回: 独立read。
        异常: 原请求/预算/取消；构造未返回资源由本read最高恢复owner负责。
        """
        if not isinstance(owner, BudgetedLegacyCANSourceAdapter) or not isinstance(request, ReadRequest):
            raise TypeError('CAN read需要实际来源及ReadRequest')
        owner._ensure_open()
        if request.session_id != owner.session_id or any(name not in {item.name for item in owner.signals} for name in request.signal_names):
            raise ValueError('CAN请求会话或投影不匹配')
        self._owner, self._budget, self._request, self._spec = owner, owner.budget, request, owner.spec
        self._process = self._raw_store = self._message_store = self._record = self._current = self._validator = None
        self._capture_message_updates = owner.capture_message_updates
        self._message_store_taken = False
        self._selected = self._runtime_metadata = self._observation = self._identity = self._work_path = None
        self._binding_projection = None
        self._sample_pack_costs = ()
        self._fixed_cost = self._metadata_cost = self._record_cost = self._pack_cost = 0
        self._pending_cost = self._validation_cost = self._held_cost = self._update_cost = 0
        self._first_ns = self._last_ns = self._conversion = self._mapped = None
        self._row_count = self._alias_index = 0
        self._retained_record_count = self._full_check_count = 0
        self._started = self._eof_delivered = self._finished = self._taken = False
        self._closed = self._closing = self._failed = False
        # 只有requested直接累计且无普通样本时需要输入字节证明；all保原费用和扫描证据。
        self._input_fingerprints_enabled = (owner._input_fingerprints_requested and owner.decode_scope == 'requested'
            and owner._update_consumer is not None and not request.signal_names)
        self._input_timestamp_sha = self._input_records_sha = self._input_fingerprints = None
        self._input_frame_count = self._input_retained_count = 0
        owner._uninstalled_request = self
        try:
            cost = 65536 + 16 * _metadata_bytes((request, owner._description, owner._definitions))
            # 默认费用保持；开启时先覆盖本层新子路径及固定责任槽，仓本身另按原公式付款。
            if self._capture_message_updates:
                cost += 4096 + 32 * len(str(owner.work_dir))
            if self._input_fingerprints_enabled:
                cost += 8192  # 两个SHA状态、计数、memoryview与最终64字符摘要独立先付费。
            _reserve_owned_ram(self, cost, '_fixed_cost')
            if self._input_fingerprints_enabled:
                if not owner.batch_read:
                    raise ValueError('CAN真实输入指纹需要批次读取')
                self._input_timestamp_sha = hashlib.sha256()
                self._input_records_sha = hashlib.sha256()
            self._identity = uuid4().hex
            self._work_path = owner.work_dir / self._identity
            self._selected = tuple(pair for pair in owner._definitions if pair[0].name in request.signal_names)
            self._validator = BatchValidator(owner._description, request)
        except BaseException as exc:
            self._failed = True
            _cleanup_owner(self, exc, 'can_observation_read_cleanup_owner', 'CAN read构造')
            raise

    @property
    def capture_message_updates(self):
        """读取创建本read时的原捕获开关，不因adapter关闭而失去来源。

        参数: 无。返回: 原生bool快照。异常: 无；该标志本身不证明已经完成输入。
        """
        return self._capture_message_updates

    @property
    def identity(self):
        """读取本次独立UUID。参数: 无。返回: str。异常: 无，不按request值复用。"""
        return self._identity

    @property
    def request(self):
        """读取创建时原请求。参数: 无。返回: 原ReadRequest。异常: 关闭时ResultClosedError。"""
        self._require_open()
        return self._request

    @property
    def closed(self):
        """读取真实关闭事实。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def failed(self):
        """读取失败标记。参数: 无。返回: bool。异常: 无，不代表已清理。"""
        return self._failed

    @property
    def finished(self):
        """读取真实完整StopIteration事实。参数: 无。返回: bool。异常: 无。"""
        return self._finished

    @property
    def exhausted(self):
        """提供完成别名。参数: 无。返回: bool。异常: 无，EOF批交付仍为False。"""
        return self._finished

    def _require_open(self):
        """拒绝已关闭/失败/半关闭。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('CAN read已关闭、失败或正在清理')

    @property
    def observation(self):
        """仅完整完成后借读事实。参数: 无。返回: CANObservation。异常: ResultClosedError。"""
        self._require_open()
        if not self._finished:
            raise ResultClosedError('CAN read尚未真正完整耗尽')
        return self._observation

    @property
    def observed_bounds(self):
        """读取已经看到的首末时间供在线规则定界，不表示输入已完整结束。

        参数: 无。返回: 两个必要整数或None；none时间范围不补造坐标。异常: 读取器已关闭/失败。
        """
        self._require_open()
        return self._first_ns,self._last_ns

    @property
    def input_fingerprints(self):
        """借读实际输入的两段字节指纹，不把它解释成普通信号样本摘要。

        参数: 无。返回: (时间SHA256,记录SHA256,全原帧数,保留记录数)的tuple。
        异常: ResultClosedError为未启用、未完成、失败或已关闭；不返回半成品hash。
        指纹只活到本read关闭，接收方要继续保留须在自己的预算下复制/持有。
        """
        self._require_open()
        if not self._finished or self._input_fingerprints is None:
            raise ResultClosedError('CAN真实输入指纹尚未完成或没有启用')
        return self._input_fingerprints

    def _observe_validated_packet(self, process, payload, batch):
        """在严格批解包后借用原字节，按原顺序增量计算时间和所需记录指纹。

        参数: process必须是本read的实际子进程read；payload/batch为其刚核完的借用包。
        返回: None。异常: SourceReadError为归属/原序不符；原hash/取消错误保持且标记失败。
        时间区是头后每原帧8字节，记录区保每条长度及原JSON；不包含随分批改变的包头。
        任一更新中断后本read永久失败，不能重试同一批或发布部分指纹。
        """
        view = time_view = record_view = None
        try:
            self._require_open()
            if (not self._input_fingerprints_enabled or self._input_timestamp_sha is None
                    or self._input_records_sha is None or self._input_fingerprints is not None
                    or process is not self._process or payload is not process._pending_reply
                    or batch.start_sequence != self._input_frame_count):
                raise SourceReadError('CAN输入指纹须来自同次已核批且按全原帧序号连续')
            view = memoryview(payload)
            from ..legacy.batch_wire import record_payload_offset, FILE_HEADER
            end = record_payload_offset(batch) + (FILE_HEADER.size if len(self._spec.input_paths)>1 else 0)
            record_view = view[end:]
            if self._owner.time_scope == 'source':
                # 全来源模式才生成全部原时间SHA；新头长度由记录区与帧数确定。
                time_view = view[end - 8 * batch.frame_count:end]
                self._input_timestamp_sha.update(time_view)
            self._input_records_sha.update(record_view)
            self._input_frame_count += batch.frame_count
            self._input_retained_count += len(batch.records)
        except BaseException as exc:
            self._failed = True
            exc.can_observation_read_cleanup_owner = self
            raise
        finally:
            # 即使调用方保存错误栈，也不由本层的视图继续保活整包；不复制任何原数据。
            for borrowed in (time_view, record_view, view):
                if borrowed is not None:
                    borrowed.release()
            process = payload = batch = borrowed = view = time_view = record_view = None

    @property
    def runtime_metadata(self):
        """借读同次READY原冻结映射，None/空unit仍未核实。

        参数: 无。返回: 保operation/version/profile等原键的映射。异常: 未READY/关闭ResultClosedError。
        """
        self._require_open()
        if self._runtime_metadata is None:
            raise ResultClosedError('CAN read尚未取得同次READY')
        return self._runtime_metadata

    def prepare_metadata(self):
        """初始化同次DBC并返回周期/单位事实，不读取首帧。

        参数: 无。返回: 同一冻结READY。异常: 原启动错误，沿本read清理链处理。
        重复调用复用同次初始化；不把初始化成功当作输入EOF。
        """
        self._require_open()
        try:
            if self._runtime_metadata is None:
                self._start()
            return self._runtime_metadata
        except BaseException as exc:
            self._fail(exc)
            raise

    def _adopt(self, exc):
        """接管未返回的实际CAN读取进程/raw/消息仓子owner。参数: exc为原错误。返回: None。异常: 无预期异常。"""
        if self._process is None:
            self._process = getattr(exc, 'can_process_read_cleanup_owner', None)
        if self._raw_store is None and not self._taken:
            self._raw_store = getattr(exc, 'raw_frame_store_cleanup_owner', None)
        # 消息仓构造可能已经取得真实FD/费用却未返回；只接尚未移交的本层子责任。
        if self._capture_message_updates and self._message_store is None and not self._message_store_taken:
            self._message_store = getattr(exc, 'decoded_message_store_cleanup_owner', None)

    def _fail(self, exc):
        """保原错/取消并关闭同一最高read。参数: exc。返回: None。异常: 清理副错只note。"""
        self._failed = True
        self._adopt(exc)
        exc.can_observation_read_cleanup_owner = self
        _cleanup_owner(self, exc, 'can_observation_read_cleanup_owner', 'CAN观测read')

    def _start(self):
        """原start仅INIT，复制同次READY并核全部声明单位后才允许第一PULL。

        参数: 无。返回: None。异常: 原CAN读取进程/单位/预算/原始暂存错误；上层保真实子槽。
        """
        request = LegacyCANRequest(self._spec.path, self._spec.dbc_path, self._owner._fields)
        if self._owner.batch_read:
            from ..legacy.batch_read import LegacyCANBatchRead
            ids = None if (self._owner.retain_raw_frames or self._capture_message_updates
                and self._owner.message_frame_ids is None) else tuple(sorted(
                {field.frame_id for _, field in self._owner._definitions}
                | set(self._owner.message_frame_ids or ())))
            # 传输预付不能吃光下一步装箱/验证/磁盘编码需要的空间；这里只留余量，
            # 费用仍由实际消费owner在使用前逐笔入账，_record_cost已在PULL前支付。
            # 同一次read的定位/路径/定义不可变；算一次每别名装箱费，后续样本
            # 仍逐笔预付同一金额，不为相同的元数据反复遍历整个定义树。
            self._sample_pack_costs = tuple(32768 + 32 * _metadata_bytes((definition, field,
                max((str(p) for p in self._spec.input_paths),key=_metadata_bytes), self._spec.legacy_profile, self._request.session_id,
                self._spec.name)) for definition, field in self._selected)
            per_sample = 2 * max(self._sample_pack_costs, default=32768)
            scratch = (65536 + 64 * MAX_DECODED_MESSAGE_ROW_BYTES
                if self._capture_message_updates or self._owner.retain_raw_frames else 0)
            sample_bound = self._request.batch_rows if self._selected else 0
            headroom = 131072 + sample_bound * per_sample + scratch
            # 当前批交给分析层前，只在上述消费空间之外预付并授权下一批。
            # 当前处理失败/取消可能多读至多一批；预算不足时批read自动同步回退。
            source_options = {'cycle_fields':self._owner._cycle_fields} if self._owner._cycle_fields else {}
            if self._owner._metadata_fields:
                source_options['metadata_fields'] = self._owner._metadata_fields
            if len(self._spec.input_paths) > 1:
                source_options['input_paths'] = self._spec.input_paths
            if self._spec.decode_policy != 'legacy':
                source_options['decode_policy'] = self._spec.decode_policy
            if self._owner.decode_scope == 'requested':
                self._process = LegacyCANBatchRead(request, self._budget, frame_ids=ids,
                    consumer_headroom_bytes=headroom, prefetch=True, decode_scope='requested',
                    input_check=self._owner.input_check, time_scope=self._owner.time_scope,
                    decode_frame_ids=self._owner.decode_frame_ids, **source_options)
            else:
                # 旧调用连新增默认关键字也不传，保原构造与故障注入入口。
                self._process = LegacyCANBatchRead(request, self._budget, frame_ids=ids,
                    consumer_headroom_bytes=headroom, prefetch=True, **source_options)
        else:
            self._process = LegacyCANProcessRead(request, self._budget)
        if self._input_fingerprints_enabled:
            self._process._validated_packet_consumer = self._observe_validated_packet
        self._process.start()
        ready = self._process.metadata
        _reserve_owned_ram(self, 4096 + 16 * _metadata_bytes(ready), '_metadata_cost')
        self._runtime_metadata = freeze_metadata(ready)
        from ..sources.can_updates import CANUpdateProjection
        projection = self._owner._update_projection or CANUpdateProjection(self._spec.name,
            self._request.session_id, tuple(field for _, field in self._owner._definitions))
        self._binding_projection = projection.for_read(ready['fields'])
        if len(self._spec.input_paths)>1 or self._spec.decode_policy != 'legacy' or self._owner._cycle_fields or self._owner._metadata_fields:
            if (ready.get('version') != 5
                    or ready.get('input_paths') != tuple(str(p) for p in self._spec.input_paths)
                    or ready.get('decode_policy') != self._spec.decode_policy):
                raise SourceReadError('同次CAN READY与连续文件/解码政策不符')
            ready = dict(ready,version=ready['base_version'])
        # 同次READY先与实际adapter交叉核；版本/集合不能从缺项猜成默认成功。
        if self._owner.decode_scope == 'requested':
            fixed = ready.get('decode_frame_ids')
            expected_version = 4 if self._owner.input_check == 'auto' else 3
            if (type(ready.get('version')) is not int or ready['version'] != expected_version
                    or type(ready.get('decode_scope')) is not str or ready['decode_scope'] != 'requested'
                    or type(fixed) is not tuple or any(type(value) is not int for value in fixed)
                    or fixed != self._owner.decode_frame_ids
                    or type(ready.get('decoded_values_policy')) is not str
                    or ready['decoded_values_policy'] != REQUESTED_VALUES_POLICY):
                raise SourceReadError('同次CAN READY与来源固定requested策略不符')
            if expected_version == 4 and (ready.get('input_check') != self._owner.input_check or ready.get('time_scope') != self._owner.time_scope):
                raise SourceReadError('同次CAN READY检查/时间范围与来源不同')
        elif (type(ready.get('version')) is not int or ready['version'] != 1
                or 'decode_scope' in ready or 'decode_frame_ids' in ready
                or 'decoded_values_policy' in ready):
            raise SourceReadError('全解码来源必须保原v1 READY且不带按需策略')
        for definition, field in self._owner._definitions:
            unit = next(item['unit'] for item in ready['fields'] if item['locator'] == field_to_dict(field))
            if unit not in (None, '') and unit != definition.input_unit:
                raise SourceReadError('同次DBC非空单位不等于声明input_unit: ' + definition.name)
        if self._owner.retain_raw_frames:
            self._raw_store = RawFrameStore(self._budget, self._work_path, self._spec.name, integrity=self._owner._history_integrity)
        # 原raw目录保持不变；可选子目录只在READY/单位核对完成后、首PULL之前创建。
        if self._capture_message_updates:
            self._message_store = DecodedMessageStore(self._budget, self._work_path / 'messages',
                self._spec.name, self._request.session_id, decoder_profile=self._runtime_metadata['profile'],
                read_identity=self._identity, sparse_sequences=self._owner.batch_read, integrity=self._owner._history_integrity)
        self._started = True

    def _accept(self, batch):
        """先预约validator候选及同刻去重集合，再原子接收并留下实际保留费用。

        参数: batch为有限SignalBatch。返回: 原batch。异常: 原协议/预算/取消，由上层poison。
        """
        _reserve_owned_ram(self, 4096 + 2 * _pending_bytes(self._validator)
            + 1024 * batch.sample_count, '_validation_cost')
        self._validator.accept(batch)
        retained = _pending_bytes(self._validator)
        _release_owned_ram(self, self._pending_cost, '_pending_cost')
        self._validation_cost -= retained
        self._pending_cost += retained
        _release_owned_ram(self, self._validation_cost, '_validation_cost')
        self._current = batch
        return batch

    def _release_current(self):
        """下一步前停止持有原batch再归还其装箱空间。参数: 无。返回: None。异常: 原抵销/取消。"""
        self._current = None
        _release_owned_ram(self, self._pack_cost, '_pack_cost')

    def _new_record(self):
        """原帧进入前先付本层记录/引用空间；全部yield先暂存再作分析层列选择。

        参数: 无。返回: True有新原帧，False为CAN读取进程真实EOF。异常: 原输入/时间/暂存错误。
        """
        self._record = None
        _release_owned_ram(self, self._record_cost, '_record_cost')
        _reserve_owned_ram(self, 4259840, '_record_cost')
        record = conversion = None
        try:
            try:
                record = next(self._process)
            except StopIteration:
                _release_owned_ram(self, self._record_cost, '_record_cost')
                if not self._process.finished:
                    raise SourceReadError('CAN进程没有完整EOF')
                if self._raw_store is not None:
                    self._raw_store.seal()
                # 两仓仅在同一次真实CAN读取进程 EOF后封口；任一失败都不能开放finished或移交。
                if self._capture_message_updates:
                    self._message_store.seal()
                return False
            conversion = convert_time(record.frame.timestamp, 's')
            mapped = checked_add_ns(conversion.time_ns, self._spec.offset_ns)
            if self._last_ns is not None and mapped < self._last_ns:
                raise SourceReadError('CAN原yield时间回退，禁止重排')
            if self._raw_store is not None:
                self._raw_store.append(record, mapped)
            # 同一个原decode对象恰追加一次，位于列选择之前，不因空投影或拆别名改变次数。
            if self._capture_message_updates:
                self._message_store.append(record, mapped, time_quantized=conversion.quantized)
            self._binding_projection.fields_for(record.frame)
            if self._owner._frame_observer is not None:
                self._owner._frame_observer(record.frame)
            if self._first_ns is None:
                self._first_ns = mapped
            self._last_ns, self._row_count = mapped, self._row_count + 1
            self._record, self._conversion, self._mapped, self._alias_index = record, conversion, mapped, 0
            self._deliver_message(record, mapped)
            return True
        finally:
            # 原异常可被保留；只断本函数临时大record/转换，不清原输入或其他模块TB。
            record = conversion = None

    def _deliver_message(self, record, time_ns):
        """仅有明确消费者时构造共同消息，默认读取不增加逐帧对象。

        参数: record为同次原解码帧；time_ns为已检查的时间或未采集None。
        返回: None。异常: 投影、预算或消费者错误由read统一标记失败并清理。
        """
        if self._owner._update_consumer is not None:
            from .message_delivery import deliver_message
            deliver_message(self, self._binding_projection, self._owner._update_consumer,
                            record.frame, record.sequence, record.values, time_ns)

    def _batch(self):
        """为当前原帧最多batch_rows个匹配别名装箱，缺key产生明确MISSING更新。

        参数: 无。返回: 已校验SignalBatch。异常: 原refs/归一化/预约/协议错误。
        """
        _reserve_owned_ram(self, 65536, '_pack_cost')
        columns = {}
        while self._alias_index < len(self._selected):
            definition, field = self._selected[self._alias_index]
            self._alias_index += 1
            if field not in self._binding_projection.fields_for(self._record.frame):
                continue
            # 完整定位/定义及单样本数组均先付；不按原数值相同而合并独立别名。
            _reserve_owned_ram(self, 16384 + 32 * _metadata_bytes((definition, field, str(self._spec.path),
                self._spec.legacy_profile, self._request.session_id, self._spec.name)), '_pack_cost')
            ref = CANSourceRef(self._request.session_id, self._spec.name, definition.field,
                str(self._spec.path), self._spec.legacy_profile, field.channel, field.signal,
                field.frame_id, self._record.frame.is_extended_id, self._record.frame.is_fd, self._record.sequence,
                self._record.frame.timestamp, self._conversion.quantized)
            value = self._record.values.get(field.signal)
            columns[definition.name] = pack_decoded(definition,
                ((self._mapped, self._record.sequence, value),), (ref,), self._owner.backend)
            if len(columns) == self._request.batch_rows:
                break
        watermark = None if self._mapped == -(1 << 63) else self._mapped - 1
        return self._accept(SignalBatch(self._spec.name, self._request.session_id, columns,
            watermark, False, None))

    def __iter__(self):
        """保持本次原序位置。参数: 无。返回: self。异常: 无，不启动读取。"""
        return self

    def __next__(self):
        """逐次交付当前原帧分片或独立空EOF批，真正下一次耗尽才开放完成事实。

        参数: 无。返回: SignalBatch。异常: 真StopIteration/原来源/预算/取消，最高read可恢复。
        """
        if self._finished:
            raise StopIteration
        self._require_open()
        try:
            self._release_current()
            if not self._started:
                self._start()
            if self._eof_delivered:
                self._finish()
            elif self._record is not None and self._alias_index < len(self._selected):
                return self._batch()
            elif self._new_record():
                return self._batch()
            else:
                _reserve_owned_ram(self, 65536, '_pack_cost')
                batch = SignalBatch(self._spec.name, self._request.session_id, {}, self._last_ns,
                    True, self._last_ns)
                self._accept(batch)
                self._eof_delivered = True
                return batch
        except BaseException as exc:
            self._fail(exc)
            raise
        raise StopIteration

    def _close_child(self, slot):
        """真实子owner完成关闭后才清槽。参数: slot为实际子槽。返回: None。异常: 原close错误。"""
        child = getattr(self, slot)
        if child is not None:
            try:
                child.close()
            finally:
                if child.closed:
                    setattr(self, slot, None)

    def _finish(self):
        """确认本read全部完成条件后开放事实，并解除adapter活登记。

        参数: 无。返回: None。异常: 原关闭/协议/登记错误，不能伪造完成。
        """
        if (not self._validator.ended or not self._process.finished
                or self._owner.retain_raw_frames and (self._raw_store is None
                    or self._raw_store.state != 'sealed' or self._raw_store.closed)):
            raise SourceReadError('CAN输入尚未满足真实完成条件')
        if self._capture_message_updates:
            # 完成事实必须同时属于本read的原消息仓，不能只凭原帧仓已封口推断。
            store = self._message_store
            if (store is None or store.closed or store.state != 'sealed'
                    or (store.count != self._row_count if not store.sparse_sequences else
                        store.count > self._row_count or store._last_sequence >= self._row_count)
                    or store.source_name != self._spec.name or store.session_id != self._request.session_id
                    or store.read_identity != self._identity
                    or store.decoder_profile != self._runtime_metadata['profile']):
                raise SourceReadError('同次CAN消息仓尚未满足原对象及完整封口事实')
        self._close_child('_process')
        self._record = None
        _release_owned_ram(self, self._record_cost, '_record_cost')
        if self._input_fingerprints_enabled:
            if (self._input_frame_count != self._row_count
                    or self._input_timestamp_sha is None or self._input_records_sha is None):
                raise SourceReadError('CAN真实输入指纹的原帧数与完成观测不符')
            self._input_fingerprints = (self._input_timestamp_sha.hexdigest() if self._owner.time_scope == 'source' else None,
                self._input_records_sha.hexdigest(), self._input_frame_count, self._input_retained_count)
            self._input_timestamp_sha = self._input_records_sha = None
        self._observation = CANObservation(self._spec.name, self._request.session_id, self._request,
            self._identity, self._first_ns, self._last_ns, self._row_count, True,
            self._owner.time_scope, self._retained_record_count, self._full_check_count)
        self._owner._requests.discard(self)
        self._finished = True

    def take_raw_store(self, receiver, slot='_raw_store'):
        """仅完成后一次移交真实sealed store，本read后续不再关闭新父资源。

        参数: receiver为同一_budget的可信内部owner；slot为其已初始化为None的实际接收槽。
        返回: 原RawFrameStore，先装父槽再撤本子槽。异常: 状态/预算/槽错误或原安装取消；
            安装后取消仍由接收父实际槽可达，不在返回边界丢失真实费用。
        """
        self._require_open()
        if not self._finished or self._taken or self._raw_store is None:
            raise ResultClosedError('原始store未完成或已移交')
        result = self._raw_store
        if (getattr(receiver, '_budget', None) is not self._budget or type(slot) is not str
                or not slot.startswith('_') or getattr(receiver, slot) is not None):
            raise ValueError('原始store移交须同账本且接收实际槽为空')
        try:
            # 父赋值先发生；即使setter在真实安装后取消，也至少有最高父实际责任。
            setattr(receiver, slot, result)
        except BaseException as exc:
            exc.can_observation_read_cleanup_owner = self
            raise
        finally:
            if getattr(receiver, slot) is result:
                self._raw_store, self._taken = None, True
        return result

    def take_message_store(self, receiver, slot='_message_store'):
        """完成后一次移交同次消息仓，父实际安装成功才解除本read责任。

        参数: receiver为同一_budget的可信owner；slot为其已存在且为空的实际槽。
        返回: 原DecodedMessageStore对象，不重建文件或复制decoded记录。
        异常: ResultClosedError为未开启、未完成或已移交；ValueError为预算/槽不符；
            父安装前后取消保原异常和can_observation_read_cleanup_owner。
        """
        self._require_open()
        if (not self._finished or not self._capture_message_updates or self._message_store_taken
                or self._message_store is None):
            raise ResultClosedError('消息store未开启、未完成或已移交')
        store = self._message_store
        if (getattr(receiver, '_budget', None) is not self._budget or type(slot) is not str
                or not slot.startswith('_') or not hasattr(receiver, slot) or getattr(receiver, slot) is not None):
            raise ValueError('消息store移交须同账本且接收实际槽为空')
        try:
            # setter可能在实际安装后取消；finally按真实父槽判断，不能先清子再return。
            setattr(receiver, slot, store)
        except BaseException as exc:
            exc.can_observation_read_cleanup_owner = self
            raise
        finally:
            if getattr(receiver, slot, None) is store:
                self._message_store, self._message_store_taken = None, True
        return store

    def close(self):
        """只关闭仍自有的输入/raw/消息store和所有实际费用，可持续重试。

        参数: 无。返回: None。异常: 首个子关闭/费用取消；can_observation_read_cleanup_owner保本对象。
        """
        if self._closed:
            return
        self._closing = True
        failure = None
        for slot in ('_process', '_raw_store', '_message_store'):
            try:
                self._close_child(slot)
            except BaseException as exc:
                if failure is None:
                    failure = exc
                else:
                    failure.add_note('CAN其他子资源关闭附加失败: ' + type(exc).__name__)
        if self._process is None and self._raw_store is None and self._message_store is None:
            self._record = self._current = self._runtime_metadata = self._observation = None
            self._validator = self._selected = None
            self._binding_projection = None
            self._sample_pack_costs = ()
            self._input_timestamp_sha = self._input_records_sha = self._input_fingerprints = None
            for slot in ('_update_cost', '_pack_cost', '_record_cost', '_validation_cost', '_pending_cost', '_metadata_cost', '_fixed_cost'):
                try:
                    _release_owned_ram(self, getattr(self, slot), slot)
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                    else:
                        failure.add_note('CAN费用抵销附加失败: ' + type(exc).__name__)
            if self._held_cost == 0:
                try:
                    self._owner._requests.discard(self)
                    if self._owner._uninstalled_request is self:
                        self._owner._uninstalled_request = None
                    self._closed = True
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                    else:
                        failure.add_note('CAN解除read登记附加失败: ' + type(exc).__name__)
        if failure is not None:
            failure.can_observation_read_cleanup_owner = self
            raise failure
