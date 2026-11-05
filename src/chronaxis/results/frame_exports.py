"""把明确范围内的原帧写成新ASC或复用旧封装的BLF，同时保精确逐帧索引。

输入来自同次读取的新暂存，包含未参与分析和DBC未知的帧；不重新读日志/解码。
ASC时间用整数纳秒文本；BLF沿现有writer及float秒接口，其精度和错误帧能力限制
在清单记录，精确源时间和全部原字段保存在frames.jsonl。筛选使用分析坐标，
写出仍保原坐标，只有显式output_offset_ns才移动输出时间。关闭后独占发布目录。
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
import json
from math import isfinite

from ..core.models import Interval
from ..core.validation import require_identifier
from ..execution.history import _metadata_bytes
from ..legacy.records import LegacyRawFrame, StoredRawFrame, frame_to_dict
from ..legacy.export_write import LegacyCANProcessWrite
from ..sources.raw_can import RawCANRecord
from ..sources.text_can_decode import DecodedCANRecord
from ..timebase.conversion import require_int64_ns, checked_add_ns, convert_time
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .export_files import ExportFiles


@dataclass(frozen=True)
class FrameExportSpec:
    """选择目标格式及明确的输出时间平移；范围仍使用分析坐标，不随平移变化。"""

    format: str = 'asc'
    output_offset_ns: int = 0
    source_time_reference: str = 'relative'
    capture_date: str | None = None
    timezone_offset_minutes: int | None = None

    def __post_init__(self):
        """核格式与时间。参数: 无。返回: None。异常: 不支持格式或非法偏移。
        """
        if self.format not in ('asc','blf') or type(self.output_offset_ns) is not int:
            raise ValueError('原帧导出需要asc/blf和整数偏移')
        require_int64_ns(self.output_offset_ns,'frame_export.output_offset_ns')
        # 时间基准是声明事实，不能用偏移或大数值绕过用户要求的真实日期。
        if self.source_time_reference not in ('relative','epoch'):
            raise ValueError('必须明确源时间为relative或epoch，不能按数字大小猜日期')
        if (self.capture_date is None)!=(self.timezone_offset_minutes is None):
            raise ValueError('采集日期和时区必须一起填写')
        if self.capture_date is not None:
            if (type(self.capture_date) is not str or len(self.capture_date)!=10
                    or date.fromisoformat(self.capture_date).isoformat()!=self.capture_date
                    or type(self.timezone_offset_minutes) is not int
                    or not -1439<=self.timezone_offset_minutes<=1439):
                raise ValueError('需要YYYY-MM-DD实际采集日期及合法整数时区分钟')
            if self.source_time_reference=='epoch':
                raise ValueError('已有绝对时间不能重复叠加采集日期')
        if self.format=='blf' and self.source_time_reference=='relative' and self.capture_date is None:
            raise ValueError('BLF导出前必须填写实际采集日期和时区')

    def date_origin_ns(self):
        """把日内零点映射到实际当地午夜。参数: 无。返回: 精确UTC纳秒或0。异常: int64溢出。
        """
        if self.capture_date is None:
            return 0
        # 用整数日/秒换算；机器本地时区及浮点timestamp都不参与日期映射。
        midnight=datetime.combine(date.fromisoformat(self.capture_date),datetime.min.time(),
            timezone(timedelta(minutes=self.timezone_offset_minutes)))
        delta=midnight-datetime(1970,1,1,tzinfo=timezone.utc)
        value=(delta.days*86400+delta.seconds)*10**9
        require_int64_ns(value,'frame_export.date_origin_ns')
        return value


@dataclass(frozen=True)
class ExportCANFrame:
    """统一真实/生成记录；保分析坐标、原输出坐标、完整原帧和有限原始定位。"""

    sequence: int
    time_ns: int
    output_time_ns: int
    frame: LegacyRawFrame
    provenance: tuple[tuple[str,str | int | float | bool | None],...]
    frame_origin: str = 'passthrough'

    def __post_init__(self):
        """核静态字段。参数: 无。返回: None。异常: 类型、范围、重复定位或非有限值。
        """
        if type(self.sequence) is not int or self.sequence<0 or type(self.frame) is not LegacyRawFrame:
            raise TypeError('导出帧需要非负原序及LegacyRawFrame')
        require_int64_ns(self.time_ns); require_int64_ns(self.output_time_ns)
        if self.frame_origin not in ('passthrough','generated') or type(self.provenance) is not tuple or len(self.provenance)>32:
            raise ValueError('导出帧种类或定位非法')
        keys=set()
        for pair in self.provenance:
            if (type(pair) is not tuple or len(pair)!=2 or type(pair[0]) is not str or not pair[0]
                    or type(pair[1]) not in (str,int,float,bool,type(None))):
                raise TypeError('帧定位需要有限键值tuple')
            if pair[0] in keys or type(pair[1]) is float and not isfinite(pair[1]):
                raise ValueError('帧定位重复或非有限')
            keys.add(pair[0])


@dataclass(frozen=True)
class SkippedCANFrame:
    """保存重建未生成的网格点；不是原帧，不进入ASC/BLF，也不伪装成零载荷。"""

    time_ns: int
    reason: str
    details: str

    def __post_init__(self):
        """核有界诊断。参数: 无。返回: None。异常: 时间、原因或文本非法。
        """
        require_int64_ns(self.time_ns)
        if type(self.reason) is not str or not self.reason or type(self.details) is not str or len(self.details.encode('utf-8'))>60000:
            raise ValueError('未生成帧需要有限原因及JSON说明文本')


def as_export_frame(record, *, compact=False):
    """保既有原帧及原坐标，转换有限导出外壳。参数: 真实文本/暂存/已统一帧，compact不构造追溯。返回: ExportCANFrame。异常: 类型错。
    """
    if type(record) is ExportCANFrame:
        return record
    if type(record) is StoredRawFrame:
        # 旧BLF原float秒与分析offset分开，不把映射后的时间回写原报文。
        converted=convert_time(record.frame.timestamp,'s')
        return ExportCANFrame(record.sequence,record.time_ns,converted.time_ns,record.frame,
            () if compact else (('profile','sclicer-functions-v1'),('yield_sequence',record.sequence),
             ('timestamp',record.frame.timestamp),('time_quantized',converted.quantized)))
    if type(record) in (RawCANRecord,DecodedCANRecord):
        raw=record.raw if type(record) is DecodedCANRecord else record
        provenance=() if compact else (('path',str(raw.path)),('line_number',raw.line_number),('parser_version',raw.parser_version),
            ('record_sequence',raw.sequence),('raw_time',raw.raw_time),('time_quantized',raw.time_quantized))
        if not compact and type(record) is DecodedCANRecord:
            provenance+=(('input_index',record.input_index),('decode_status',record.status))
        # 分析offset只决定筛选位置；导出日期应叠加原始日内时间，不能叠加归零后的分析时间。
        source_ns=raw.time_ns if raw.source_time_ns is None else raw.source_time_ns
        return ExportCANFrame(record.sequence,raw.time_ns,source_ns,raw.frame,provenance)
    raise TypeError('帧导出需要同次原始/解码暂存记录')


def _asc_line(record,output_ns):
    """写标准ASC数据行及无法表达的原字段名单。参数: record、非负精确输出ns。返回: (bytes,losses)。异常: 格式不可表达。
    """
    frame=record.frame
    if frame.is_rx is None:
        raise ValueError('原始报文导出需要收发方向is_rx，不能把未知方向写为Tx或Rx')
    if output_ns<0 or type(frame.channel) is not int or not 0<=frame.channel<65536:
        raise ValueError('ASC需要非负时间和明确0基整数通道')
    seconds,nanos=divmod(output_ns,10**9)
    prefix=f'{seconds}.{nanos:09d}'
    channel=str(frame.channel+1); direction='Rx' if frame.is_rx else 'Tx'
    identifier=format(frame.arbitration_id,'x')+('x' if frame.is_extended_id else '')
    if not frame.is_extended_id and frame.arbitration_id>0x7ff:
        raise ValueError('ASC标准帧ID超出11位')
    if frame.is_error_frame:
        # 标准错误行不能保存数据帧附加字段；完整原值保在索引，清单明确格式损失。
        expected={'arbitration_id':0,'is_extended_id':False,'dlc':0,'data':b'',
                  'bitrate_switch':False,'error_state_indicator':False,'is_remote_frame':False}
        if not frame.is_fd:
            expected['is_rx']=True
        losses=tuple(k for k,v in expected.items() if getattr(frame,k)!=v)
        body=f'CANFD {channel} {direction} ErrorFrame' if frame.is_fd else f'{channel} ErrorFrame'
    else:
        losses=()
        if frame.is_remote_frame:
            if frame.is_fd or frame.data or not 0<=frame.dlc<=8:
                raise ValueError('ASC远程帧需要经典CAN、空数据和0至8 DLC')
            body=f'{channel} {identifier} {direction} r {frame.dlc:x}'
        elif frame.is_fd:
            lengths=(0,1,2,3,4,5,6,7,8,12,16,20,24,32,48,64)
            if frame.dlc!=len(frame.data) or frame.dlc not in lengths:
                raise ValueError('ASC FD长度或DLC不一致')
            body=f'CANFD {channel} {direction} {identifier} {int(frame.bitrate_switch)} {int(frame.error_state_indicator)} {lengths.index(frame.dlc):x} {frame.dlc} '+frame.data.hex(' ')
        else:
            if frame.dlc!=len(frame.data) or frame.dlc>8:
                raise ValueError('ASC经典帧长度不一致')
            body=f'{channel} {identifier} {direction} d {frame.dlc:x} '+frame.data.hex(' ')
        if not frame.is_fd:
            losses=tuple(k for k in ('bitrate_switch','error_state_indicator') if getattr(frame,k))
    return (prefix+' '+body.rstrip()+'\n').encode('ascii'),losses


def export_can_frames(records,spec,interval,destination,budget,*,source,device_label,check_cancel=None,compact=False,integrity=True,file_consumer=None):
    """逐条筛选并写出原始范围，完整消费新暂存后发布。

    参数: records同次可关闭原帧流；spec格式/偏移；interval半开分析范围；destination可复用公开输出根，内部file_consumer仍独占新目录；
        budget共享账本；source来源名；device_label设备；check_cancel取消回调；
        compact关闭逐帧副本/三时间/误差计算，仅保目标帧和必要清单。
    返回: 公开ExportManifest含实际目录/清单/文件路径；内部file_consumer模式返回Path。
    异常: 格式/时间/原历史/I/O/预算/取消错；持续清理失败保export_cleanup_owner。
    """
    if type(compact) is not bool:
        raise TypeError('compact必须为bool')
    if type(spec) is not FrameExportSpec or type(interval) is not Interval:
        raise TypeError('帧导出需要FrameExportSpec和Interval')
    require_identifier(source,'frame_export.source')
    if device_label not in ('home','work') or check_cancel is not None and not callable(check_cancel):
        raise ValueError('帧导出需要实际设备及可选取消回调')
    date_origin=spec.date_origin_ns()
    output_offset=checked_add_ns(date_origin,spec.output_offset_ns)
    if file_consumer is not None and not callable(file_consumer):
        raise TypeError('file_consumer须为回调')
    owner=ExportFiles(destination,budget,integrity=integrity,timestamped=file_consumer is None)
    try:
        if not compact:
            owner.open_file('frames.jsonl')
        if spec.format=='asc':
            owner.select_file('frames.asc')
            owner.append(b'base hex timestamps absolute\nno internal events logged\n')
        else:
            try:
                owner.worker=LegacyCANProcessWrite(budget,owner.temporary/'frames.blf')
            except BaseException as error:
                owner.worker=getattr(error,'can_process_write_cleanup_owner',None)
                raise
        owner.reader=iter(records)
        reconstruction=getattr(owner.reader,'export_metadata',None)
        if reconstruction is not None:
            _reserve_owned_ram(owner,_metadata_bytes(reconstruction)*16,'_fixed_cost')
        count=generated=limited=skipped=0
        max_float_error=0
        last=None
        for raw in owner.reader:
            if check_cancel is not None:
                check_cancel()
            _reserve_owned_ram(owner,1048576+(_metadata_bytes(raw.provenance)*16
                               if type(raw) is ExportCANFrame else len(raw.details.encode('utf-8'))*16
                               if type(raw) is SkippedCANFrame else 0),'_row_cost')
            try:
                if type(raw) is SkippedCANFrame:
                    if last is not None and raw.time_ns<last:
                        raise ValueError('未生成帧记录时间回退')
                    last=raw.time_ns
                    if interval.start_ns<=raw.time_ns<interval.end_ns:
                        if not compact:
                            owner.select_file('skipped_frames.jsonl')
                            owner.append((json.dumps({'time_ns':raw.time_ns,'reason':raw.reason,'details':raw.details},
                                ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'))
                        skipped+=1
                    continue
                record=as_export_frame(raw,compact=True) if compact else as_export_frame(raw)
                if last is not None and record.time_ns<last:
                    raise ValueError('导出帧时间回退，不能重排原记录')
                last=record.time_ns
                if not interval.start_ns<=record.time_ns<interval.end_ns:
                    continue
                if record.frame.is_rx is None:
                    raise ValueError('原始报文导出需要收发方向is_rx')
                output_ns=checked_add_ns(record.output_time_ns,output_offset)
                if spec.format=='asc':
                    payload,losses=_asc_line(record,output_ns)
                    owner.select_file('frames.asc'); owner.append(payload)
                else:
                    # 不调用旧库的隐式“相对时间头归零”分支；缺日期先要求显式映射。
                    if output_ns<631152000*10**9:
                        raise ValueError('现有BLF写库不支持1990年以前的日期，不能改写为固定参考日期')
                    if type(record.frame.channel) is not int or not 0<=record.frame.channel<65535:
                        raise ValueError('BLF需要0至65534的明确整数通道，避免写库隐式改通道')
                    # 库接口仅接受float秒；记录转换误差，同时以整数索引保留精确真值。
                    timestamp=output_ns/10**9
                    if not compact:
                        delta=abs(Fraction(timestamp)*10**9-output_ns)
                        max_float_error=max(max_float_error,(delta.numerator+delta.denominator-1)//delta.denominator)
                    owner.worker.write(replace(record.frame,timestamp=timestamp))
                    losses=('error_frame_flags_or_payload',) if record.frame.is_error_frame else ()
                if not compact:
                    owner.select_file('frames.jsonl')
                    packet={'index':count,'source':source,'sequence':record.sequence,'analysis_time_ns':record.time_ns,
                        'source_time_ns':record.output_time_ns,'output_time_ns':output_ns,'frame_origin':record.frame_origin,
                        'provenance':dict(record.provenance),'frame':frame_to_dict(record.frame),'format_limits':losses}
                    owner.append((json.dumps(packet,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8'))
                count+=1; generated+=record.frame_origin=='generated'; limited+=bool(losses)
            finally:
                _release_owned_ram(owner,owner._row_cost,'_row_cost')
        owner.close_reader()
        # 旧写进程真正结束后才能回读摘要；文件没关、摘要失败均不发布正式目录。
        if owner.worker is not None:
            owner.worker.finish()
            owner.worker=None
            owner.register_external('frames.blf')
        metadata={'frame_origin':'can_frames','device_label':device_label,'source':source,'format':spec.format,
            'range_ns':(interval.start_ns,interval.end_ns),'output_offset_ns':spec.output_offset_ns,
            'source_time_reference':spec.source_time_reference,'capture_date':spec.capture_date,
            'timezone_offset_minutes':spec.timezone_offset_minutes,'date_origin_ns':date_origin,
            'frames':count,'generated':generated,'passthrough':count-generated,'format_limited_frames':limited,
            'skipped_grid_points':skipped,
            'reconstruction':reconstruction,
            'time_precision':'integer_ns_text' if spec.format=='asc' else 'legacy_float_seconds',
            }
        if compact:
            metadata['row_format']='compact-v2'
        else:
            metadata.update(max_float_conversion_error_ns=max_float_error,exact_source_index='frames.jsonl')
        output=owner.finish(metadata)
        if file_consumer is not None: file_consumer(tuple(owner.files))
        return output
    except BaseException as error:
        owner._failed = True
        _cleanup_owner(owner,error,'export_cleanup_owner','原始报文导出')
        raise
