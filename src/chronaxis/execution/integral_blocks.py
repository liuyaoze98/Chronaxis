"""并行积分的冻结任务与有界二进制块；只恢复列出的数值模型。

面积以网络序float64传输，不求和、不转换单位。首尾同刻组保留定宽原值、
质量和序号；精确时间使用Decimal元组，避免十进制上下文影响文件顺序检查。
任务只包含声明、表达式文本及必要积分字段，不传可调用对象或任意Python对象。
"""
from dataclasses import dataclass
from decimal import Decimal
import struct

from .._control_models import extract, keys, native, pack_signal, restore_signal

# 单包含包头最多512KiB；预约8MiB覆盖同时存在的编码及展开对象，不代表进程RSS上限。
WIRE_LIMIT = 524288
BLOCK_RAM = 8 * 1048576
MAX_EVENTS = 128  # 单包最多128个边界或面积事件，避免以文件总长度扩大队列。
MODEL_LIMIT = BLOCK_RAM // 2  # 单包模型展开最多4MiB，剩余预约供编码和临时副本使用。
_HEAD = struct.Struct('!4sI')  # 网络序：4字节协议标志和4字节正文长度。
_U32 = struct.Struct('!I')  # 事件、列或字符数量使用无符号32位整数。
_F64 = struct.Struct('!d')  # 原面积按网络序float64传输，不在传输层换算或求和。
# 固定字段白名单限制重建范围；新增运行能力必须明确更新对应编解码。
_SPECS = ('calculation_id','operation','partial_policy','output_unit','scope',
          'minimum_coverage','config_version','ddof','q')
_BINDING = ('source','channel','frame_id','extended','fd','dbc_fd')
_FACTS = ('count','first_ns','last_ns','decode_calls','first_order_time','last_order_time','compatibility_fields')
_TASK = ('definitions','bindings','expressions','specs','binding','session_id','derived','domain','batch_intervals')


def _timebase(value):
    """展开固定时基。参数: value为TimebaseSpec。返回: dict。异常: 非法模型时AttributeError。"""
    return dict(timebase_id=value.timebase_id,time_type=value.time_type.value,origin=value.origin)


def _restore_timebase(value):
    """恢复固定时基。参数: value为原生dict。返回: TimebaseSpec。异常: 字段或枚举错误时ValueError，原构造错误继续传播。"""
    from ..core.models import TimebaseSpec
    from ..core.types import TimeType
    value=dict(keys(value,('timebase_id','time_type','origin')))
    value['time_type']=TimeType(value['time_type'])
    return TimebaseSpec(**value)


def _interval(value):
    """展开可空请求范围。参数: value为Interval或None。返回: list[int]或None，依次为起止纳秒。异常: 非法模型时AttributeError。"""
    return None if value is None else [value.start_ns,value.end_ns]


def _restore_interval(value):
    """恢复可空范围。参数: value为两元素list或None。返回: Interval或None。异常: 结构错误时ValueError，原时间类型或范围错误继续传播。"""
    from ..core.models import Interval
    if value is None:return None
    if type(value) is not list or len(value)!=2:raise ValueError('积分请求范围结构非法')
    return Interval(*value)


def pack_task(definitions, expressions, specs, binding, session_id, *, derived=(), domain=None, batch_intervals=64):
    """展开已验证数值任务，不读取文件。

    参数: definitions、expressions、specs为同序的SignalDefinition、StaticExpression和CalculationDefinition tuple；
        binding为SameFrameBinding，session_id为会话名；derived为原派生声明tuple，默认空；
        domain为Interval或None；batch_intervals为1至64的区间数上限，默认64。
    返回: dict，只含固定JSON原生值，不包含可调用对象。
    异常: 非支持绑定、声明不一致或块上限非法时ValueError；原模型展开错误继续传播。
    """
    from ..core.declarations import DeclarationBindings
    if not expressions or len(expressions)!=len(specs):raise ValueError('积分表达式与指标数量不符')
    bindings=expressions[0].bindings
    if (type(bindings) is not DeclarationBindings or bindings.extensions is not None
            or bindings.lookups or bindings.temporal_inputs
            or any(item.bindings!=bindings for item in expressions)):
        raise ValueError('并行积分需要共同的简单声明绑定')
    sources=[dict(name=item.name,timebase=_timebase(item.timebase),input_identity=item.input_identity,
                  offset_ns=item.offset_ns) for item in bindings.sources]
    sync=[dict(source=item.source,analysis_timebase=_timebase(item.analysis_timebase),evidence=item.evidence)
          for item in bindings.synchronization]
    declared=dict(session_id=bindings.session_id,timebase=_timebase(bindings.timebase),domain=_interval(bindings.domain),
                  sources=sources,signals=[pack_signal(item) for item in bindings.signals],
                  derived_names=list(bindings.derived_names),synchronization=sync,config_version=bindings.config_version,
                  identity=bindings.identity)
    task=native(dict(definitions=[pack_signal(item) for item in definitions],bindings=declared,
        expressions=[dict(text=item.text,unit=item.root.unit) for item in expressions],
        specs=[dict(**extract(item,_SPECS),window=_interval(item.window)) for item in specs],
        binding=extract(binding,_BINDING),session_id=session_id,
        derived=[extract(item,('name','expr','unit')) for item in derived],domain=_interval(domain),
        batch_intervals=batch_intervals))
    check_task(task)
    return task


def check_task(task):
    """核冻结任务外形及数量，拒绝额外指令。参数: 固定dict。返回: None。异常: ValueError。"""
    keys(task,_TASK)
    for name in ('definitions','expressions','specs','derived'):
        if type(task[name]) is not list or len(task[name])>4096:raise ValueError('积分任务列表非法：'+name)
    if not task['definitions'] or not task['expressions'] or len(task['specs'])!=len(task['expressions']):
        raise ValueError('积分任务为空或指标数量不符')
    if type(task['batch_intervals']) is not int or not 1<=task['batch_intervals']<=64:
        raise ValueError('积分块区间数需要1至64')
    if type(task['session_id']) is not str:raise ValueError('积分会话需要文本')
    keys(task['binding'],_BINDING)
    keys(task['bindings'],('session_id','timebase','domain','sources','signals','derived_names',
                           'synchronization','config_version','identity'))
    for name in ('sources','signals','derived_names','synchronization'):
        value=task['bindings'][name]
        if type(value) is not list or len(value)>4096:raise ValueError('积分绑定列表非法')
    for value in task['expressions']:
        keys(value,('text','unit'))
        if any(type(item) is not str for item in value.values()):raise ValueError('积分表达式需要文本')
    for value in task['specs']:
        keys(value,(*_SPECS,'window'))
        if value['operation']!='integral' or value['scope']!='session':raise ValueError('积分任务仅支持会话积分')
    for value in task['derived']:keys(value,('name','expr','unit'))


def restore_task(task):
    """仅通过明确构造器重建数值任务，并核原声明身份。

    参数: task为pack_task产生的原生dict。返回: dict[str, object]，供FileIntegralTerms构造时展开。
    异常: 固定字段或声明身份不一致时ValueError；原类型、表达式和声明构造错误继续传播。
    此处不加载DBC和报文文件。
    """
    from ..core.binding import SynchronizationEvidence
    from ..core.calculations import CalculationDefinition
    from ..core.declarations import DeclarationBindings, DeclaredSource
    from ..core.expression import DerivedDefinition, validate_expression
    from .same_frame_integrals import SameFrameBinding
    check_task(task)
    data=task['bindings']
    sources=[]
    for source in data['sources']:
        keys(source,('name','timebase','input_identity','offset_ns'))
        sources.append(DeclaredSource(source['name'],_restore_timebase(source['timebase']),source['input_identity'],source['offset_ns']))
    sync=[]
    for item in data['synchronization']:
        keys(item,('source','analysis_timebase','evidence'))
        sync.append(SynchronizationEvidence(item['source'],_restore_timebase(item['analysis_timebase']),item['evidence']))
    bindings=DeclarationBindings(data['session_id'],_restore_timebase(data['timebase']),_restore_interval(data['domain']),
        tuple(sources),tuple(restore_signal(item) for item in data['signals']),tuple(data['derived_names']),tuple(sync),
        config_version=data['config_version'])
    if bindings.identity!=data['identity'] or bindings.session_id!=task['session_id']:
        raise ValueError('积分工作进程声明身份不符')
    derived=tuple(DerivedDefinition(**item) for item in task['derived'])
    expressions=tuple(validate_expression(item['text'],bindings,derived=derived,unit=item['unit']) for item in task['expressions'])
    specs=tuple(CalculationDefinition(**{name:item[name] for name in _SPECS},window=_restore_interval(item['window']))
                for item in task['specs'])
    return dict(definitions=tuple(restore_signal(item) for item in task['definitions']),expressions=expressions,
        specs=specs,binding=SameFrameBinding(**task['binding']),session_id=task['session_id'],derived=derived,
        domain=_restore_interval(task['domain']),batch_intervals=task['batch_intervals'])


@dataclass(frozen=True)
class IntegralPacket:
    """一个已核验数据块；eof标明数据终点，完整资源释放另等finished控制确认。"""
    file_index: int  # 原来源声明中的零起文件序号，不按worker完成先后重排。
    number: int  # 当前文件从0递增的块序号。
    events: tuple  # 固定首组、面积列、末组或异常前缀边界事件。
    eof: bool  # 原帧读尽且读取器/数值owner已关闭；块工作区仍待发送完成后释放。
    facts: dict  # 同次原帧计数、实际首末范围、精确顺序时间及必要帧型提示。


class IntegralBlockError(ValueError):
    """面积块格式、长度或展开量不满足固定协议。"""


def event_cost(event):
    """按固定字段计算事件的保守传输/展开上界，不遍历每个面积值。

    参数: event为首组、面积块、末组或已关闭边界事件。
    返回: tuple[int, int]，依次为保守编码字节数及模型展开字节数，不含整包事实。
    异常: 不支持事件时IntegralBlockError；只用于有界分块，不代替解码校验。
    """
    from .file_integral_terms import FileIntegralHead, IntegralTermsChunk, FileIntegralTail, FileIntegralFrontier
    if type(event) is IntegralTermsChunk:
        return (42+sum(58+9*len(column.areas) for column in event.columns),
                512+sum(512+48*len(column.areas) for column in event.columns))
    if type(event) is FileIntegralFrontier:return 19,256
    if type(event) in (FileIntegralHead,FileIntegralTail):
        group=event.group
        return _group_cost(len(group.first_values)) if group is not None else (3,512)
    raise IntegralBlockError('未知积分块事件')


def _group_cost(count):
    """按最大整数编码估算首尾边界。

    参数: count为已验证的非负字段数int。
    返回: tuple[int, int]，依次为保守编码和模型展开字节数。异常: 合法内部计数不抛业务异常。
    """
    return 95+96*count,512+832*count


def _compatibility_cost(names):
    """按UTF-8长度估算兼容提示图。

    参数: names为规范字段键str的可迭代对象。
    返回: tuple[int, int]，依次为保守编码和模型展开字节数。
    异常: 字符不能编码时UnicodeEncodeError；非法内部类型错误继续传播。
    """
    sizes=tuple(len(name.encode('utf-8')) for name in names)
    return sum(5+size for size in sizes),sum(256+4*size for size in sizes)


def facts_cost(facts, cache):
    """估算固定事实的传输和展开，复用每批未变化的兼容字段图费用。

    参数: facts为同次读取的固定dict，含精确Decimal时间及compatibility_fields tuple；
        cache为本批dict[int, tuple[int, int]]，按兼容字段tuple的对象身份复用费用。
    返回: tuple[int, int]，依次为保守编码和模型展开字节数。
    异常: 缺字段时KeyError；原时间类型或UTF-8编码错误继续传播。
    仅在形成事件或封包时调用，不逐帧扫描字段名。
    """
    fields=facts['compatibility_fields'];key=id(fields)
    if key not in cache:cache[key]=_compatibility_cost(name for name,_ in fields)
    wire,model=cache[key];wire+=256;model+=1024
    for name in ('first_order_time','last_order_time'):
        value=facts[name]
        if value is not None:
            digits=len(value.as_tuple().digits);wire+=24+digits;model+=256+16*digits
    return wire,model


def boundary_supported(definitions):
    """判断声明的单个首尾边界及全部兼容提示能否进入既有有界包。

    参数: definitions为已验证SignalDefinition序列。
    返回: bool；False表示单个边界过宽，调用方在首帧前选择原执行路线。
    异常: 非法声明时AttributeError或TypeError，字段编码错误继续传播；不读取输入。
    时间和包头另留64KiB/1MiB，
        运行时仍按实际精确时间与事实长度封包，不截短或改成浮点时间。
    """
    wire,model=_group_cost(len(definitions))
    fields_wire,fields_model=_compatibility_cost(item.field for item in definitions)
    return wire+fields_wire+65536<=WIRE_LIMIT and model+fields_model+1048576<=MODEL_LIMIT


class _Writer:
    """在512KiB包长内构造固定字段；body只持有当前包的bytearray正文。"""
    def __init__(self):
        """初始化有限字节区。参数: 无。返回: None，构造编码器。异常: MemoryError。"""
        self.body=bytearray()
    def add(self,value):
        """追加片段前核上限。参数: bytes。返回: None。异常: IntegralBlockError。"""
        if len(self.body)+len(value)+8>WIRE_LIMIT:raise IntegralBlockError('积分块超过512KiB')
        self.body.extend(value)
    def byte(self,value):
        """写uint8。参数: int。返回: None。异常: 范围或包长错误。"""
        self.add(bytes((value,)))
    def count(self,value):
        """写uint32数量。参数: int。返回: None。异常: 范围或包长错误。"""
        self.add(_U32.pack(value))
    def integer(self,value):
        """无损写有界整数。参数: int或None。返回: None。异常: 类型或长度错误。"""
        if value is None:self.byte(0);return
        if type(value) is not int:raise IntegralBlockError('积分整数类型错误')
        width=max(1,(abs(value).bit_length()+7)//8)
        if width>16:raise IntegralBlockError('积分整数超过128位')
        self.byte(1 if value>=0 else 2);self.byte(width);self.add(abs(value).to_bytes(width,'big'))
    def decimal(self,value):
        """写精确时间元组。参数: 有限Decimal或None。返回: None。异常: 类型/包长错误。"""
        self.byte(value is not None)
        if value is not None:
            if type(value) is not Decimal or not value.is_finite():raise IntegralBlockError('积分顺序时间必须有限Decimal')
            sign,digits,exponent=value.as_tuple()
            self.byte(sign);self.integer(exponent);self.count(len(digits));self.add(bytes(digits))


class _Reader:
    """先检查数量再分配模型；data为借用包，position为字节游标，expansion为累计展开字节数。"""
    def __init__(self,packet):
        """核包头。参数: packet为bytes。返回: None，构造解码器。异常: 格式或长度错误时IntegralBlockError。"""
        if type(packet) is not bytes or not 8<=len(packet)<=WIRE_LIMIT:raise IntegralBlockError('积分块长度非法')
        magic,size=_HEAD.unpack_from(packet)
        if magic!=b'P5I1' or size!=len(packet)-8:raise IntegralBlockError('积分块版本或长度不符')
        self.data=packet;self.position=8;self.expansion=0
    def take(self,size):
        """读取有限片段。参数: 非负int。返回: bytes。异常: 截断错误。"""
        if size<0 or self.position+size>len(self.data):raise IntegralBlockError('积分块被截断')
        start=self.position;self.position+=size;return self.data[start:self.position]
    def charge(self,size):
        """核模型展开费用。参数: size为非负int字节数。返回: None。异常: 超过MODEL_LIMIT时IntegralBlockError。"""
        self.expansion+=size
        if self.expansion>MODEL_LIMIT:raise IntegralBlockError('积分块模型展开超过4MiB')
    def byte(self):
        """读取uint8。参数: 无。返回: int。异常: 截断。"""
        return self.take(1)[0]
    def boolean(self):
        """读取精确bool。参数: 无。返回: bool。异常: 非0/1标志。"""
        value=self.byte()
        if value not in (0,1):raise IntegralBlockError('积分布尔标志非法')
        return bool(value)
    def count(self,maximum=4096):
        """读取受限数量。参数: 最大条数。返回: int。异常: 超限或截断。"""
        value=_U32.unpack(self.take(4))[0]
        if value>maximum or value>len(self.data)-self.position:raise IntegralBlockError('积分块数量非法')
        return value
    def integer(self):
        """恢复整数或None。参数: 无。返回: int|None。异常: 标记/长度错误。"""
        sign=self.byte()
        if sign==0:return None
        width=self.byte()
        if sign not in (1,2) or not 1<=width<=16:raise IntegralBlockError('积分整数编码非法')
        value=int.from_bytes(self.take(width),'big')
        return value if sign==1 else -value
    def decimal(self):
        """恢复精确时间。参数: 无。返回: Decimal|None。异常: 数字或指数错误。"""
        if not self.boolean():return None
        sign=self.byte();exponent=self.integer();count=self.count(WIRE_LIMIT)
        if sign not in (0,1) or type(exponent) is not int or count<1:raise IntegralBlockError('积分时间结构非法')
        self.charge(256+16*count)
        digits=tuple(self.take(count))
        if any(digit>9 for digit in digits):raise IntegralBlockError('积分时间数字非法')
        return Decimal((sign,digits,exponent))


def _write_scalar(writer,value):
    """写规范数值。参数: 编码器、ScalarValue。返回: None。异常: 非支持值类型。"""
    from ..core.types import SignalDType as D
    if value.labels or value.code is not None or value.partial:raise IntegralBlockError('积分边界不能含扩展标量')
    writer.byte((D.INT64,D.UINT64,D.FLOAT64).index(value.dtype));writer.byte(value.valid);writer.integer(int(value.quality))
    writer.byte(value.value is not None)
    if value.value is not None:
        if value.dtype is D.FLOAT64:writer.add(_F64.pack(value.value))
        else:writer.integer(value.value)


def _read_scalar(reader):
    """恢复规范数值。参数: 解码器。返回: ScalarValue。异常: 类型/质量/结构错误。"""
    from ..core.numeric import ScalarValue
    from ..core.types import SignalDType as D, QualityFlag as Q
    index=reader.byte()
    if index>2:raise IntegralBlockError('积分边界dtype非法')
    dtype=(D.INT64,D.UINT64,D.FLOAT64)[index]
    valid=reader.boolean();quality=reader.integer();present=reader.boolean()
    value=(_F64.unpack(reader.take(8))[0] if dtype is D.FLOAT64 else reader.integer()) if present else None
    reader.charge(384)
    return ScalarValue(value,dtype,valid,Q(quality))


def _write_group(writer,group):
    """写同刻边界摘要。参数: 编码器、固定group。返回: None。异常: 包长或字段错误。"""
    for name in ('time_ns','first_sequence','last_sequence','count'):writer.integer(getattr(group,name))
    writer.count(len(group.first_values))
    for values in (group.first_values,group.last_values):
        for value in values:_write_scalar(writer,value)
    for value in group.first_conflicts:writer.integer(value)


def _read_group(reader):
    """恢复同刻边界摘要。参数: 解码器。返回: SameTimeGroupSummary。异常: 固定模型错误。"""
    from .file_integral_terms import SameTimeGroupSummary
    coordinates=tuple(reader.integer() for _ in range(4));count=reader.count()
    reader.charge(512+count*64)
    first=tuple(_read_scalar(reader) for _ in range(count));last=tuple(_read_scalar(reader) for _ in range(count))
    conflicts=tuple(reader.integer() for _ in range(count))
    return SameTimeGroupSummary(*coordinates,first,last,conflicts)


def encode_packet(file_index,number,events,eof,facts):
    """编码一个面积事件块，不改变浮点位型或事件顺序。

    参数: file_index和number为非负文件/块号；events为固定事件tuple；
        eof为本文件数据终点bool，facts为同次读取事实dict。
    返回: bytes，含包头最多512KiB；不会把文件面积先累计成部分和。
    异常: 未支持事件或超限时IntegralBlockError；字段、编码及struct原错误继续传播。
    """
    from .file_integral_terms import FileIntegralHead, IntegralTermsChunk, FileIntegralTail, FileIntegralFrontier
    writer=_Writer();writer.integer(file_index);writer.integer(number);writer.byte(eof);writer.count(len(events))
    for event in events:
        if type(event) is FileIntegralHead:
            writer.byte(0);_write_group(writer,event.group);writer.integer(event.next_time_ns)
        elif type(event) is IntegralTermsChunk:
            writer.byte(1);writer.integer(event.left_ns);writer.integer(event.right_ns);writer.byte(event.right_closed);writer.count(len(event.columns))
            for column in event.columns:
                writer.count(len(column.areas))
                if len(column.areas)!=len(column.valid):raise IntegralBlockError('积分面积与掩码长度不同')
                for value in column.areas:writer.add(_F64.pack(value))
                writer.add(bytes(column.valid))
                for value in (column.covered_ns,column.valid_ns,int(column.quality)):writer.integer(value)
        elif type(event) is FileIntegralTail:
            writer.byte(2);writer.byte(event.group is not None)
            if event.group is not None:_write_group(writer,event.group)
            writer.byte(event.same_as_head)
        elif type(event) is FileIntegralFrontier:
            writer.byte(3);writer.integer(event.time_ns)
        else:raise IntegralBlockError('未知积分块事件')
    keys(facts,_FACTS)
    for name in _FACTS[:4]:writer.integer(facts[name])
    for name in _FACTS[4:6]:writer.decimal(facts[name])
    writer.count(len(facts['compatibility_fields']))
    for name,value in facts['compatibility_fields']:
        encoded=name.encode('utf-8');writer.count(len(encoded));writer.add(encoded);writer.byte(value)
    return _HEAD.pack(b'P5I1',len(writer.body))+writer.body


def decode_packet(packet):
    """恢复一个固定事件块，并核完整消费与有界模型。

    参数: packet为encode_packet产生的bytes。返回: IntegralPacket，保留事件顺序和精确时间。
    异常: 截断、非法计数/事件或展开超限时IntegralBlockError；非法UTF-8及固定模型构造错误继续传播。
    只重建列出的模型，不加载任意类。
    """
    from math import isfinite
    from ..core.types import QualityFlag as Q
    from .file_integral_terms import FileIntegralHead, IntegralTermsChunk, FileIntegralTail, IntegralColumnTerms, FileIntegralFrontier
    reader=_Reader(packet);index=reader.integer();number=reader.integer();eof=reader.boolean()
    if any(type(value) is not int or value<0 for value in (index,number)):raise IntegralBlockError('积分文件或块号非法')
    events=[]
    for _ in range(reader.count(MAX_EVENTS)):
        kind=reader.byte()
        if kind==0:events.append(FileIntegralHead(_read_group(reader),reader.integer()))
        elif kind==1:
            left=reader.integer();right=reader.integer();right_closed=reader.boolean();columns=[]
            for _ in range(reader.count()):
                size=reader.count(64);reader.charge(512+size*48)
                areas=tuple(_F64.unpack(reader.take(8))[0] for _ in range(size))
                valid=tuple(reader.boolean() for _ in range(size))
                covered=reader.integer();valid_ns=reader.integer();quality=reader.integer()
                if any(not isfinite(value) for value in areas):raise IntegralBlockError('积分面积需要有限float64')
                columns.append(IntegralColumnTerms(areas,valid,covered,valid_ns,Q(quality)))
            events.append(IntegralTermsChunk(left,right,tuple(columns),right_closed))
        elif kind==2:
            group=_read_group(reader) if reader.boolean() else None
            events.append(FileIntegralTail(group,reader.boolean()))
        elif kind==3:events.append(FileIntegralFrontier(reader.integer()))
        else:raise IntegralBlockError('积分事件标记非法')
    facts={name:reader.integer() for name in _FACTS[:4]}
    facts.update({name:reader.decimal() for name in _FACTS[4:6]})
    compatibility=[]
    for _ in range(reader.count()):
        size=reader.count(WIRE_LIMIT);reader.charge(256+4*size)
        compatibility.append((reader.take(size).decode('utf-8'),reader.boolean()))
    facts['compatibility_fields']=tuple(compatibility)
    if any(type(facts[name]) is not int or facts[name]<0 for name in ('count','decode_calls')):
        raise IntegralBlockError('积分文件计数非法')
    if reader.position!=len(packet):raise IntegralBlockError('积分块含尾随内容')
    return IntegralPacket(index,number,tuple(events),eof,facts)
