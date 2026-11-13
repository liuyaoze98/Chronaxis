"""按需解码新ASC/CSV原帧，并接到既有数值归一化核心。

CANTextDecodeRead消费显式CANTextSpec与本次需要的SignalDefinition，逐个交付
DecodedCANRecord；未知ID、未选中和非数据帧仍保原记录，仅所需帧调用cantools。
DBC沿用decode_choices=False/allow_truncated=True参数，但新入口先严格核已选帧长度；
已定义报文解码失败直接定位，不冒充未知ID。pack_text_records输出既有SignalSeries。
完整读取核对全部原帧时间；按需ASC仅核所需通道/ID的连续顺序，并同次统计来源范围。
文件不重读；DBC加载和临时对象先付预算。
解析文件逐个关闭，失败/取消保原错误及必要恢复owner；纯BLF串行复用显式解码政策。
"""

from dataclasses import dataclass
from decimal import Decimal
from hashlib import file_digest
from pathlib import Path

from ..dbc_loading import load_dbc_file

from ..core.binding import SignalDefinition
from ..core.validation import require_identifier
from ..execution.history import _metadata_bytes
from ..legacy.records import field_to_dict
from ..legacy.decode_policy import check_decode_length, decode_serial_frame
from ..legacy.worker import _field_metadata
from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import ResultClosedError
from .asc import ASCSpec, ASCRead
from .blf import BLFSpec, BLFRead, _UntimedBLFRecord
from .raw_csv import CANCSVRead
from .raw_can import RawCANRecord, CANTextError
from .can_spec import can_field_from_key
from .models import freeze_metadata
from .packing import pack_decoded
from .text_can_ref import CANTextSourceRef
from .text_can_spec import CANTextSpec


@dataclass(frozen=True)
class DecodedCANRecord:
    """保留一条原帧及本次所需原信号值；非decoded记录的values必须为空。"""

    source: str  # 当前来源名称。
    input_index: int  # 原输入列表位置。
    sequence: int  # 全部文件连续的原帧序号，不仅是参与计算的序号。
    raw: RawCANRecord | _UntimedBLFRecord  # 保留原帧；无时间需求的BLF记录明确不提供时间。
    values: tuple[tuple[str, int | float | bool | None], ...]  # 规范CAN字段键到DBC物理值。
    status: str  # decoded/unknown/unselected/non_data；不把错误记成unknown。
    frame_values: tuple[tuple[str,int | float | bool | None],...] = ()  # 显式重建所需原物理字段。
    frame_layout: tuple[tuple[str,int],...] = ()  # 当次复用选择器的原始码值。

    def __post_init__(self):
        """核记录冻结结构。参数: 无。返回: None。异常: 来源、位置、状态或值结构非法。
        """
        self._validate(None)

    @classmethod
    def _from_bound_values(cls, source, input_index, sequence, raw, values, status,
                           frame_values, frame_layout, known_fields):
        """用本次绑定已经解析的字段名建立内部记录，其余检查与公开构造相同。

        参数: 前八项与记录字段相同；known_fields为当前读取器从已验证绑定取得的字段键集合。
        返回: 新的冻结DecodedCANRecord，不持有额外的绑定副本。
        异常: 字段不在当前绑定中、值类型或记录结构不合法时拒绝。
        外部构造仍调用完整字段解析；此入口只供同次解码结果复用绑定检查。
        """
        record = object.__new__(cls)
        # 仅安装当前固定模型的八项字段，不按输入提供的属性名恢复对象。
        for name, value in zip(('source', 'input_index', 'sequence', 'raw', 'values',
                                'status', 'frame_values', 'frame_layout'),
                               (source, input_index, sequence, raw, values, status,
                                frame_values, frame_layout)):
            object.__setattr__(record, name, value)
        record._validate(known_fields)
        return record

    def _validate(self, known_fields):
        """检查固定记录，内部已绑定键只核成员关系。

        参数: known_fields为本次已解析字段集合，None表示公开入口需要完整解析。
        返回: None。异常: 非法结构、未知字段、重复键或无值状态携带数据。
        """
        # 该模型不开放任意对象值，也不在外部构造时接受重复字段覆盖。
        require_identifier(self.source,'decoded_can.source')
        if (type(self.raw) not in (RawCANRecord,_UntimedBLFRecord) or type(self.input_index) is not int or self.input_index < 0
                or type(self.sequence) is not int or self.sequence < 0 or type(self.values) is not tuple
                or self.status not in ('decoded','unknown','unselected','non_data')):
            raise ValueError('解码CAN记录结构或状态非法')
        keys = set()
        for pair in self.values:
            if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) not in (int,float,bool,type(None)):
                raise TypeError('解码值需要规范字段键及原生数值/None')
            if known_fields is None:
                can_field_from_key(pair[0])
            elif pair[0] not in known_fields:
                raise ValueError('解码CAN字段不属于当前绑定')
            if pair[0] in keys:
                raise ValueError('解码CAN字段重复')
            keys.add(pair[0])
        if self.status != 'decoded' and self.values:
            raise ValueError('未解码原帧不能携带信号值')
        for pairs,kinds in ((self.frame_values,(int,float,bool,type(None))),(self.frame_layout,(int,))):
            if type(pairs) is not tuple or len(pairs)>4096 or any(type(p) is not tuple or len(p)!=2 or type(p[0]) is not str
                    or not p[0] or type(p[1]) not in kinds for p in pairs) or len({p[0] for p in pairs})!=len(pairs):
                raise ValueError('重建物理值或布局结构非法')
        if self.status!='decoded' and (self.frame_values or self.frame_layout):
            raise ValueError('未解码原帧不能伪造重建值')


class CANTextDecodeRead:
    """拥有单次DBC和逐文件解析器；EOF后保有限元数据到显式close。"""

    def __init__(self, spec, budget, signals, *, check_cancel=None, database_context=None, classify_unselected=True, cycle_fields=(), metadata_fields=(), integrity=True, trace=True, retain_source_time=True, selected_ids=None, time_frame_ids=None, emit_frame_ids=None, blf_time_scope='source',legacy_blf_decode=False,serial_blf_policy=None,post_decode_frame_ids=None):
        """只核声明并预约固定费用。参数: spec来源、budget账本、signals所需定义tuple、check_cancel取消回调；classify_unselected保旧逐帧分类，消息消费者无需区分无关ID是否在DBC中；cycle_fields只请求初始化周期，metadata_fields只请求候选，两者不加入解码投影。

        time_frame_ids仅在无需完整顺序/原帧导出时传入：选中通道/ID之间必须有序，
        其他帧仍用于同次来源最早/最晚时间统计，不交付给计算或作为单调性前点。
        selected_ids仅供不需要全来源观测或原帧导出的纯消息计算使用：原始CSV先按ID跳过
        无关行；None保留全部行。count保原始行计数，retained_count只数实际交付的记录。
        legacy_blf_decode默认False；纯can_blf转接保留legacy长度政策和DecodeError缺值行为。
        serial_blf_policy仅纯BLF串行设置requested/all：唯一ID沿原数据库入口的普通异常
        缺值处理，多定义ID按实际帧型直接解码；all还核完整值。并行和文本政策保持独立。
        post_decode_frame_ids仅串行all且无原帧导出时传入有限ID集合：每帧完成解码和
        完整值检查后再跳过无消费者的帧。None交付全部帧；计数只数实际交付。
        纯BLF串行沿用按ID检查时间和交付，通道由后续绑定筛选；其他来源按通道及ID。

        返回: 未开始读取的owner。异常: 声明/预算错误；持续清理失败附text_can_cleanup_owner。
        """
        # 构造不访问DBC/输入；只接受显式同来源、同通道且唯一的别名定义。
        if (type(spec) is not CANTextSpec or not isinstance(budget,ResourceBudget)
                or type(signals) is not tuple or len(signals) > 4096
                or any(type(item) is not SignalDefinition or item.source != spec.name for item in signals)
                or check_cancel is not None and not callable(check_cancel)):
            raise TypeError('文本CAN读取需要静态声明、预算及所需信号定义')
        if type(classify_unselected) is not bool:
            raise TypeError('classify_unselected需要bool')
        if type(legacy_blf_decode) is not bool or (legacy_blf_decode and
                (spec.decode_policy!='legacy' or any(type(item) is not BLFSpec for item in spec.inputs))):
            raise ValueError('legacy_blf_decode仅用于明确的纯BLF legacy转接')
        self._legacy_blf_decode=legacy_blf_decode
        if serial_blf_policy not in (None,'requested','all') or (serial_blf_policy is not None and any(type(item) is not BLFSpec for item in spec.inputs)):
            raise ValueError('纯BLF串行政策需要requested/all及全部BLF输入')
        self._serial_blf_policy=serial_blf_policy
        if post_decode_frame_ids is not None and serial_blf_policy!='all':
            raise ValueError('解码后投影仅用于纯BLF串行all政策')
        self._post_decode_frame_ids=None if post_decode_frame_ids is None else frozenset(post_decode_frame_ids)
        self._duplicate_ids=frozenset()
        if len({item.name for item in signals}) != len(signals):
            raise ValueError('文本CAN别名不能重复')
        from ..legacy.dbc_cycles import require_cycle_fields
        require_cycle_fields(cycle_fields,spec.channel)
        require_cycle_fields(metadata_fields,spec.channel)
        self._metadata_fields = metadata_fields
        self._selected_ids = selected_ids
        # 并行传输只发送实际消费者需要的帧；时间检查和来源范围仍在筛选前完成。
        self._emit_frame_ids = None if emit_frame_ids is None else frozenset(emit_frame_ids)
        self._blf_time_scope=blf_time_scope
        self.first_order_time = None
        if time_frame_ids is not None and (type(time_frame_ids) is not tuple or len(time_frame_ids)>4096
                or any(type(value) is not int or not 0 <= value <= 0x1fffffff for value in time_frame_ids)):
            raise ValueError('参与时间检查的CAN ID需要有限合法整数tuple')
        if time_frame_ids is not None and spec.input_check == 'full':
            raise ValueError('完整输入检查不能限制时间顺序检查范围')
        self._time_frame_ids = None if time_frame_ids is None else frozenset(time_frame_ids)
        self._last_selected_time = None
        parsed = tuple((item,can_field_from_key(item.field)) for item in signals)
        if any(field.channel != spec.channel for _,field in parsed):
            raise ValueError('文本CAN字段通道与来源声明不一致')
        # 所有资源槽先安装，任何后续预算/读取错误均可由同一个owner关闭。
        self.spec,self._budget,self.signals,self._fields = spec,budget,signals,parsed
        self._cycle_fields = cycle_fields
        if type(integrity) is not bool: raise TypeError("integrity需要bool")
        self._integrity=integrity
        self._trace=trace
        self._retain_source_time=retain_source_time
        self._check_cancel = check_cancel
        self._classify_unselected = classify_unselected
        self._binding_resolver = None
        self._database_context=database_context
        self._extra_fields=() if database_context is None else database_context.extra_fields
        self._frame_values=self._frame_layout=()
        self._known_field_keys = None
        self._held_cost = self._fixed_cost = self._dbc_cost = self._metadata_cost = 0
        self._db = self._raw = self._metadata = None
        self._input_index = 0
        self._completed_count = 0
        self.count = self.decode_calls = self.retained_count = 0
        self.full_check_count = 0
        self.first_ns = self.last_ns = None
        self._closed = self._exhausted = self._failed = self._closing = False
        try:
            # 固定费用包含所需字段、路径和DBC元数据；不保存随原帧数增长的列表。
            cost = 131072 + _metadata_bytes((signals,self._extra_fields,selected_ids,time_frame_ids))*16
            if cycle_fields or metadata_fields:
                cost += 16384 + _metadata_bytes((cycle_fields,metadata_fields))*32
            if database_context is not None:
                database_context.require_open()
                if database_context.path!=spec.dbc_path or database_context._budget is not budget:
                    raise ValueError('共用DBC上下文必须匹配当前文件和共享预算')
            cost += sum(1024+len(str(item.path).encode('utf-8'))*16 for item in spec.inputs)
            _reserve_owned_ram(self,cost,'_fixed_cost')
        except BaseException as error:
            _cleanup_owner(self,error,'text_can_cleanup_owner','文本CAN构造')
            raise

    @property
    def closed(self):
        """返回真实资源关闭事实。参数: 无。返回: bool。异常: 无。
        """
        return self._closed

    @property
    def exhausted(self):
        """区别真实全文件EOF与提前close。参数: 无。返回: bool。异常: 无。
        """
        return self._exhausted

    @property
    def metadata(self):
        """取得本次实际DBC事实。参数: 无。返回: 冻结Mapping。异常: 未启动或已关闭时ResultClosedError。
        """
        if self._metadata is None:
            raise ResultClosedError('文本CAN尚无可用的同次DBC元数据')
        return self._metadata

    def prepare_metadata(self):
        """只初始化一次DBC，供计算在首帧前取得周期。

        参数: 无。返回: 同次冻结元数据。异常: 失败/关闭拒绝，启动错误交实际owner清理。
        不打开原始文件，不改变EOF状态。
        """
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('文本CAN读取已关闭或失败')
        try:
            if self._metadata is None:
                self._start()
            return self.metadata
        except BaseException as error:
            self._failed = True
            _cleanup_owner(self, error, 'text_can_cleanup_owner', '文本CAN初始化')
            raise

    def _start(self):
        """一次加载并核所需定位/单位。参数: 无。返回: None。异常: 原DBC/I/O/预算或单位不符。
        """
        # 只有首次next进入此处；为库的DBC对象图和哈希缓冲预约保守费用，不声称RSS硬上限。
        from ..can_dependencies import import_can_dependency
        cantools = import_can_dependency('cantools')
        if self._database_context is None:
            size = self.spec.dbc_path.stat().st_size
            _reserve_owned_ram(self,1048576+size*64,'_dbc_cost')
            before_stat=self.spec.dbc_path.stat()
            before=None
            if self._integrity:
                with self.spec.dbc_path.open('rb') as stream:
                    before = file_digest(stream,'sha256').hexdigest()
            self._db = load_dbc_file(str(self.spec.dbc_path), cantools)
        else:
            # 新文本读取和新输出共用同一已付费DBC；借用结束不能替父owner释放费用。
            self._database_context.require_open()
            self._db=self._database_context.database
            before=self._database_context.sha256
        fields = tuple(dict.fromkeys((*[field for _,field in self._fields],*self._extra_fields)))
        # 仅缓存已冻结声明的规范键；范围固定，避免每条消息重建相同JSON字段键。
        self._field_keys={field:field.key for field in fields}
        # 与字段字典共用已预付的声明空间；只保存引用，不复制每帧字段或扩大声明范围。
        self._known_field_keys = frozenset(self._field_keys.values())
        from ..legacy.binding import FrameBindingResolver
        self._binding_resolver = FrameBindingResolver(self._db, fields)
        if self._serial_blf_policy is not None:
            from collections import Counter
            self._duplicate_ids=frozenset(key for key,count in Counter(message.frame_id for message in self._db.messages).items() if count>1)
        if self._cycle_fields or self._metadata_fields:
            fields=tuple(dict.fromkeys((*fields,*self._cycle_fields,*self._metadata_fields)))
            facts=_field_metadata(self._db,fields,cycle_fields=self._cycle_fields)
        else:
            facts = _field_metadata(self._db,fields)
        # 已知非空DBC单位与input_unit逐字核对；缺单位不伪装成已认证单位。
        for definition,field in self._fields:
            unit = next(item['unit'] for item in facts if item['locator']==field_to_dict(field))
            if unit not in (None,'') and unit != definition.input_unit:
                raise ValueError('DBC非空单位与input_unit不同: '+definition.name)
        if self._database_context is None:
            after=None
            if self._integrity:
                with self.spec.dbc_path.open('rb') as stream:
                    after = file_digest(stream,'sha256').hexdigest()
            after_stat=self.spec.dbc_path.stat()
            changed=(before_stat.st_size,before_stat.st_mtime_ns,before_stat.st_ino)!=(after_stat.st_size,after_stat.st_mtime_ns,after_stat.st_ino)
            if changed or before != after:
                raise ValueError('加载期间DBC内容发生变化')
        # EOF后仍保留单位/定位等事实；与DBC对象图分开付费，不能随DBC释放而漏账。
        _reserve_owned_ram(self,4096+_metadata_bytes(freeze_metadata(facts))*16
            +len(str(self.spec.dbc_path).encode('utf-8'))*16,'_metadata_cost')
        self._metadata = freeze_metadata({'profile':'can-text-v1','dbc_path':str(self.spec.dbc_path),
            'dbc_sha256':before,'fields':facts,'decode_choices':False,'allow_truncated':True,
            'selected_length_check':'legacy' if self._legacy_blf_decode else 'partial' if self.spec.decode_policy=='partial' else 'exact',
            'decode_scope':self._serial_blf_policy or 'requested','cantools_version':cantools.__version__,
            'record_check_scope':'selected_ids' if ((self._selected_ids is not None and self.spec.source_type=='raw_can_csv') or (self._serial_blf_policy is not None and self._emit_frame_ids is not None and self.spec.input_check=='auto')) else 'source',
            'time_order_check_scope':'none' if self._blf_time_scope=='none' else 'selected_ids' if self._time_frame_ids is not None else 'source'})

    def _decode(self, raw):
        """给本条原帧分类并按需解码。参数: raw为本次实际RawCANRecord。返回: (values,status)。

        异常: 所选政策的长度检查或非DBC解码错误。文本legacy遇DecodeError停止；
        strict/partial及明确的纯BLF legacy转接将其记为本条无值，缺失信号不沿用前值。
        """
        frame = raw.frame
        self._frame_values=self._frame_layout=()
        # 普通文本政策不从远程/错误帧生成信号；纯BLF legacy沿旧政策尝试解码。
        if (frame.is_remote_frame or frame.is_error_frame) and not self._legacy_blf_decode:
            return (),'non_data'
        selected = self._binding_resolver.fields_for(frame)
        decode_all = self._serial_blf_policy == 'all'
        if not selected and not decode_all:
            if not self._classify_unselected:
                return (),'unselected'
            return (), 'unselected' if any(message.frame_id == frame.arbitration_id for message in self._db.messages) else 'unknown'
        message = self._binding_resolver.message_for(frame, selected) if selected else None
        if message is not None:
            try:
                check_decode_length(frame,message.length,
                    'strict' if self.spec.decode_policy == 'legacy' and not self._legacy_blf_decode else self.spec.decode_policy)
            except ValueError as error:
                raise CANTextError(raw.path,raw.line_number,str(error)) from error
        from cantools.database.errors import DecodeError
        self.decode_calls += 1
        if self._serial_blf_policy is not None:
            try:
                values=decode_serial_frame(self._db,frame,message,self._duplicate_ids)
            except (ValueError,KeyError) as error:
                raise CANTextError(raw.path,raw.line_number,'已定义DBC报文解码失败: '+str(error)) from error
        else:
            try:
                values = message.decode(frame.data, decode_choices=False, allow_truncated=True)
            except DecodeError as error:
                if self.spec.decode_policy == 'legacy' and not self._legacy_blf_decode:
                    raise CANTextError(raw.path,raw.line_number,'已定义DBC报文解码失败: '+str(error)) from error
                values = {}
            except (ValueError,KeyError) as error:
                raise CANTextError(raw.path,raw.line_number,'已定义DBC报文解码失败: '+str(error)) from error
        if decode_all:
            # 显式完整诊断保留旧全部值与64KiB限制；正常requested不构造这份副本。
            from ..legacy.records import LegacyDecodedFrame
            LegacyDecodedFrame(self._completed_count+raw.sequence,frame,values)
        if message is not None and self._database_context is not None and any(rule.matches(frame) for rule in self._database_context.rules):
            from ..legacy.binding import field_matches
            names={field.signal for field in self._extra_fields if field_matches(field, frame)}
            self._frame_values=tuple((name,value) for name,value in values.items() if name in names)
            self._frame_layout=tuple((signal.name,int(signal.conversion.numeric_scaled_to_raw(values[signal.name])))
                for signal in message.signals if signal.is_multiplexer and signal.name in values)
        # 同一原字段可有多个分析别名；只交付一次物理值，额外转换由pack_decoded按别名执行。
        return tuple((self._field_keys[field],values.get(field.signal)) for field in dict.fromkeys(selected)),'decoded'

    def __iter__(self):
        """迭代同次读取。参数: 无。返回: self。异常: 无。
        """
        return self

    def _time_selected(self, frame):
        """判断此帧是否属于所需通道与ID；不解码、不改时间。

        参数: frame为已解析原帧。返回: bool；None选择全部帧。异常: 无。
        纯BLF串行按ID沿用旧时间范围，其他来源同时匹配通道；同ID帧型交绑定解析器核对。
        """
        return self._time_frame_ids is None or ((self._serial_blf_policy is not None
            or frame.channel == self.spec.channel) and frame.arbitration_id in self._time_frame_ids)

    def __next__(self):
        """逐条交付原帧和所需解码值。参数: 无。返回: DecodedCANRecord。异常: EOF/定位数据错/原I/O、预算、取消。
        """
        if self._closed or self._exhausted:
            raise StopIteration
        if self._closing or self._failed:
            raise ResultClosedError('文本CAN读取已失败或正在关闭')
        try:
            if self._check_cancel is not None:
                self._check_cancel()
            if self._database_context is not None:
                self._database_context.require_open()
            if self._db is None:
                self._start()
            while self._input_index < len(self.spec.inputs):
                if self._raw is None:
                    # 实际parser owner在创建成功后安装；失败的未返回owner也必须接管清理。
                    item = self.spec.inputs[self._input_index]
                    factory = ASCRead if type(item) is ASCSpec else BLFRead if type(item) is BLFSpec else CANCSVRead
                    try:
                        self._raw = factory(item,self._budget,check_cancel=self._check_cancel,
                            retain_original=self._trace,retain_source_time=self._retain_source_time or self._trace,
                            **({'flag_resolver':self._binding_resolver.missing_flags,
                                'selected_ids':self._selected_ids} if factory is CANCSVRead else
                               {'time_selector':self._time_selected if self._time_frame_ids is not None else None,
                                'previous_exact_time':self._last_selected_time} if factory is ASCRead else
                               {'emit_frame_ids':self._emit_frame_ids,'channel':None if self._serial_blf_policy is not None else self.spec.channel,
                                'binary_time':self._serial_blf_policy is not None,
                                'previous_order_ns':int(self._last_selected_time.scaleb(9)) if self._serial_blf_policy is not None and self._last_selected_time is not None else None,
                                'projection_only':self.spec.input_check=='auto',
                                'time_scope':self._blf_time_scope,
                                'time_check_all':self._time_frame_ids is None} if self._emit_frame_ids is not None else {'binary_time':True} if factory is BLFRead and self._serial_blf_policy is not None else {}))
                    except BaseException as error:
                        self._raw = (getattr(error,'asc_read_cleanup_owner',None)
                            or getattr(error,'raw_csv_cleanup_owner',None) or getattr(error,'blf_read_cleanup_owner',None))
                        raise
                try:
                    raw = next(self._raw)
                except StopIteration:
                    # 单文件真实EOF才换下一文件；不重排输入、不从头回退另一个parser。
                    self.count = self._completed_count + self._raw.count
                    self._completed_count = self.count
                    # full及all是主动全检；这里只累计auto实际发生的非原生回退。
                    if isinstance(self._raw, BLFRead) and self.spec.input_check == 'auto' and self._serial_blf_policy != 'all':
                        self.full_check_count += self._raw.full_check_count
                    self._blf_observation()
                    if isinstance(self._raw, ASCRead):
                        # full模式的最后元数据时刻也延续；按需模式只保所需帧，空文件不清零。
                        self._last_selected_time = self._raw.last_exact_time
                        first=self._raw.first_exact_time
                        if first is not None and (self.first_order_time is None or first<self.first_order_time):
                            self.first_order_time=first
                    self._raw.close()
                    self._raw = None
                    self._input_index += 1
                    continue
                # 来源范围与时序输入不是一回事：范围取同次读到的极值，不要求无关帧有序。
                if raw.time_ns is not None:
                    self.first_ns = raw.time_ns if self.first_ns is None else min(self.first_ns,raw.time_ns)
                    self.last_ns = raw.time_ns if self.last_ns is None else max(self.last_ns,raw.time_ns)
                self.count = self._completed_count + self._raw.count
                self._blf_observation()
                if not self._time_selected(raw.frame):
                    continue
                # ASC只借当前比较点，避免跨文件舍入为同一ns后漏掉精确回退。
                # 其他格式沿用其原有整数ns精度；不在每条记录中保存双份时间。
                current_time = (self._raw.last_exact_time if isinstance(self._raw, ASCRead)
                                else None if raw.time_ns is None else Decimal(f'{raw.time_ns}e-9'))
                if current_time is not None and self._last_selected_time is not None and current_time < self._last_selected_time:
                    raise CANTextError(raw.path,raw.line_number,'连续文件时间回退，需显式对齐起点')
                self._last_selected_time = current_time
                if self.first_order_time is None:
                    self.first_order_time = current_time
                if self._emit_frame_ids is not None and ((self._serial_blf_policy is None
                        and raw.frame.channel != self.spec.channel) or raw.frame.arbitration_id not in self._emit_frame_ids):
                    continue
                values,status = self._decode(raw)
                if self._post_decode_frame_ids is not None and raw.frame.arbitration_id not in self._post_decode_frame_ids:
                    continue
                result = DecodedCANRecord._from_bound_values(
                    self.spec.name, self._input_index, self._completed_count + raw.sequence,
                    raw, values, status, self._frame_values, self._frame_layout,
                    self._known_field_keys)
                # 来源范围已在筛选前统计；原序号和count包含跳过行，retained_count仅数交付。
                self.retained_count += 1
                return result
            # EOF后释放大DBC图，有限事实保留到显式close，供父层先接收并付费。
            self._db = self._binding_resolver = None
            _release_owned_ram(self,self._dbc_cost,'_dbc_cost')
            self._exhausted = True
            raise StopIteration
        except StopIteration:
            raise
        except BaseException as error:
            self._failed = True
            _cleanup_owner(self,error,'text_can_cleanup_owner','文本CAN读取')
            raise

    def _blf_observation(self):
        """接收BLF投影前已核的范围和顺序事实。参数: 无。返回: None。异常: 无。

        文件尾部只有无关帧时也更新来源结束；这些事实不能当成已消费水位。
        """
        if isinstance(self._raw,BLFRead) and self._raw.first_ns is not None:
            self.first_ns=self._raw.first_ns if self.first_ns is None else min(self.first_ns,self._raw.first_ns)
            self.last_ns=self._raw.last_ns if self.last_ns is None else max(self.last_ns,self._raw.last_ns)
            if self._time_frame_ids is None:
                if self.first_order_time is None and self._raw.first_order_ns is not None:
                    self.first_order_time=Decimal(f'{self._raw.first_order_ns}e-9')
                if self._raw.last_order_ns is not None:
                    current=Decimal(f'{self._raw.last_order_ns}e-9')
                    # EOF或当前记录之后的全来源时间，不在当前记录检查之前前移比较点。
                    if self._raw.closed:
                        self._last_selected_time=current
    def close(self):
        """关闭自有解析器及DBC状态，可重试。参数: 无。返回: None。异常: 原关闭/预算错误。
        """
        if self._closed:
            return
        self._closing = True
        # 子文件真实关闭后才撤责任；持续失败仍由本owner保留引用。
        if self._raw is not None:
            self._raw.close()
            self._raw = None
        self._db = self._metadata = self._binding_resolver = None
        self._field_keys = self._known_field_keys = None
        self._time_frame_ids = None
        self._last_selected_time = None
        _release_owned_ram(self,self._dbc_cost,'_dbc_cost')
        _release_owned_ram(self,self._metadata_cost,'_metadata_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed = True

    def __enter__(self):
        """建立显式资源上下文。参数: 无。返回: self。异常: 无。
        """
        return self

    def __exit__(self, exception_type, error, traceback):
        """保原业务错误并收尾。参数: exception_type/error/traceback异常上下文。返回: False。异常: 正常退出时的关闭错误。
        """
        if error is None:
            self.close()
        else:
            _cleanup_owner(self,error,'text_can_cleanup_owner','文本CAN上下文')
        return False


def pack_text_records(definition, records, session_id, backend):
    """把有限已解码原帧交给现有数值核心，不再次解码或重复DBC缩放。

    参数: definition为SignalDefinition；records为有限DecodedCANRecord tuple；session_id会话；backend为reference/numpy。
    返回: SignalSeries，保精确纳秒、同刻原序号和CANTextSourceRef；调用方负责批次数组的长期预算。
    异常: 来源/声明/记录类型不符，或既有pack_decoded类型、数值转换错误。
    """
    if type(definition) is not SignalDefinition or type(records) is not tuple or any(type(item) is not DecodedCANRecord for item in records):
        raise TypeError('文本CAN归一化需要定义及有限解码记录tuple')
    require_identifier(session_id,'text_can.session_id')
    samples,refs = [],[]
    for record in records:
        if record.source != definition.source:
            raise ValueError('文本CAN记录与信号来源不一致')
        # 未选中帧无该字段，不制造更新；匹配报文实际缺值则None更新，覆盖旧值。
        values = dict(record.values)
        if definition.field not in values:
            continue
        raw = record.raw
        samples.append((raw.time_ns,record.sequence,values[definition.field]))
        refs.append(CANTextSourceRef(session_id,record.source,definition.field,str(raw.path),
            raw.parser_version,raw.line_number,record.input_index,raw.sequence,record.sequence,
            raw.raw_time,raw.time_quantized))
    return pack_decoded(definition,tuple(samples),tuple(refs),backend)
