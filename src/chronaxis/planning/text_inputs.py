"""静态解释新的ASC和原始CAN表配置，不打开输入或DBC。

来源使用既有name/time/dbc_by_channel及path或有序paths；parser明确ASC版本
或CSV布局/时间模式。offsets可逐文件声明相对于共同time.offset的额外平移，
不自动猜跨日、设备同步或日期。返回CANTextSpec及规范来源身份供公共AnalysisRunner。
"""

from hashlib import sha256

from ..core.models import TimebaseSpec
from ..core.types import TimeType
from ..sources.asc import ASCSpec
from ..sources.blf import BLFSpec
from ..sources.raw_csv import CANCSVSpec,CSVTimeSpec
from ..sources.raw_csv_layout import CANCSVLayout
from ..sources.text_can_spec import CANTextSpec
from ..timebase.conversion import checked_add_ns
from .checks import (PlanValidationError,absolute_path,array_at,canonical,choice_at,coordinate_at,
    duration_at,metadata_at,model_at,object_at,text_at,timezone_at)


def parse_text_source(raw,base,path):
    """建立一个明确的新文本CAN来源。参数: raw原对象、base配置目录、path错误位置。
    返回: SourcePlan。异常: PlanValidationError定位配置问题；不发生原始输入I/O。
    """
    from .models import SourcePlan
    raw=object_at(raw,path,('name','source_type','time','dbc_by_channel'),('path','paths','parser','offsets','metadata','input_check','file_merge') + (('reader_options',)))
    source_type=choice_at(raw['source_type'],('can_asc','asc_or_blf','raw_can_csv'),path+'.source_type')
    name=text_at(raw['name'],path+'.name',identifier=True)
    clock=object_at(raw['time'],path+'.time',('time_type','unit'),('origin','offset','timezone'))
    time_type=choice_at(clock['time_type'],('relative','absolute'),path+'.time.time_type')
    unit=choice_at(clock['unit'],('s','ms','us','ns','ISO8601'),path+'.time.unit')
    if time_type=='relative':
        if 'origin' not in clock or 'timezone' in clock or unit=='ISO8601':
            raise PlanValidationError(path+'.time','relative必须声明共同origin，且不补日历时区')
        origin=text_at(clock['origin'],path+'.time.origin')
        clock_id='relative_'+sha256(origin.encode('utf-8')).hexdigest()[:16]
    else:
        if 'origin' in clock:
            raise PlanValidationError(path+'.time.origin','absolute不接受relative origin')
        origin=None; clock_id='utc'
    timebase=model_at(TimebaseSpec,path+'.time',clock_id,TimeType(time_type),origin)
    offset=coordinate_at(clock.get('offset','0s'),path+'.time.offset')
    zone=None
    if 'timezone' in clock:
        tz=timezone_at(clock['timezone'],path+'.time.timezone')
        delta=None if tz is None else tz.utcoffset(None)
        if delta is None or delta.total_seconds()%60:
            raise PlanValidationError(path+'.time.timezone','此原始报文读取器需要固定时区：UTC或±HH:MM')
        zone=int(delta.total_seconds()//60)
    if ('path' in raw)==('paths' in raw):
        raise PlanValidationError(path,'path和paths必须且只能提供一种')
    names=[raw['path']] if 'path' in raw else array_at(raw['paths'],path+'.paths')
    if not 1<=len(names)<=4096:
        raise PlanValidationError(path+'.paths','需要1至4096个有序文件')
    paths=tuple(absolute_path(item,base,f'{path}.paths[{i}]') for i,item in enumerate(names))
    if source_type=='asc_or_blf' and any(p.suffix.lower() not in {'.asc','.blf'} for p in paths):
        raise PlanValidationError(path+'.paths','自动读取只支持ASC/BLF后缀')
    offsets=array_at(raw.get('offsets',['0s']*len(paths)),path+'.offsets')
    if len(offsets)!=len(paths):
        raise PlanValidationError(path+'.offsets','逐文件偏移数量必须与paths相同')
    shifted=tuple(model_at(checked_add_ns,f'{path}.offsets[{i}]',offset,coordinate_at(value,f'{path}.offsets[{i}]'))
        for i,value in enumerate(offsets))
    dbc=raw['dbc_by_channel']
    if type(dbc) is not dict or len(dbc)!=1:
        raise PlanValidationError(path+'.dbc_by_channel','当前文本CAN需要一个明确通道到DBC路径')
    channel=next(iter(dbc))
    from .channels import channel_index
    channel_number=channel_index(channel,path+'.dbc_by_channel',key=True)
    dbc_path=absolute_path(dbc[channel],base,path+'.dbc_by_channel.'+channel)
    parser=raw.get('parser',{})
    if source_type in ('can_asc','asc_or_blf'):
        parser=object_at(parser,path+'.parser',(),('version','encoding'))
        if unit!='s':
            raise PlanValidationError(path+'.time.unit','ASC原文字以秒表示')
        inputs=tuple(model_at(BLFSpec,path+'.parser',p,shift) if source_type=='asc_or_blf' and p.suffix.lower()=='.blf' else
            model_at(ASCSpec,path+'.parser',p,parser.get('version','vector-asc-v1'),
            parser.get('encoding','utf-8-sig'),'epoch' if time_type=='absolute' else 'relative',zone,shift)
            for p,shift in zip(paths,shifted))
    else:
        parser=object_at(parser,path+'.parser',('layout','time_format'),
            ('id_base','length_base','channel_origin','payload_style','rollover_min_drop'))
        layout_raw=parser['layout']
        if type(layout_raw) is dict and type(layout_raw.get('fields')) is dict:
            fields=dict(layout_raw['fields'])
            # 通道列缺省时继承当前来源唯一通道；先还原输入起点，reader只减一次。
            origin=parser.get('channel_origin',0)
            if type(origin) is not int or origin not in (0,1):
                raise PlanValidationError(path+'.parser.channel_origin','通道起点须为0或1')
            fields.setdefault('channel',{'fixed':channel_number+origin})
            layout_raw=dict(layout_raw,fields=fields)
        layout=model_at(CANCSVLayout.from_dict,path+'.parser.layout',layout_raw)
        time_format=choice_at(parser['time_format'],('numeric','clock','clock-ms-us-v1','iso8601'),path+'.parser.time_format')
        if ((time_format in ('clock','clock-ms-us-v1') and (time_type!='relative' or unit!='s'))
                or time_format=='iso8601' and (time_type!='absolute' or unit!='ISO8601')
                or time_format=='numeric' and (unit=='ISO8601' or zone is not None)):
            raise PlanValidationError(path+'.time','时间种类/单位/时区与原表解析模式不符')
        rollover=duration_at(parser['rollover_min_drop'],path+'.parser.rollover_min_drop',positive=True) if 'rollover_min_drop' in parser else None
        inputs=tuple(model_at(CANCSVSpec,path+'.parser',p,layout,
            model_at(CSVTimeSpec,path+'.parser',time_format,unit if time_format=='numeric' else 's',shift,zone,rollover),
            parser.get('id_base','auto'),parser.get('length_base',10),parser.get('channel_origin',0),parser.get('payload_style','spaced'))
            for p,shift in zip(paths,shifted))
    options=object_at(raw.get('reader_options',{}),path+'.reader_options',(),('decode_policy',))
    policy=choice_at(options.get('decode_policy','strict'),
        ('strict','partial','legacy'),path+'.reader_options.decode_policy')
    input_check=choice_at(raw.get('input_check','auto'),('auto','full'),path+'.input_check')
    merge=choice_at(raw.get('file_merge','concatenate'),('concatenate','time_order'),path+'.file_merge')
    if source_type=='raw_can_csv' and 'file_merge' in raw:
        raise PlanValidationError(path+'.file_merge','file_merge仅适用于ASC/BLF来源')
    spec=model_at(CANTextSpec,path,name,inputs,dbc_path,channel_number,timebase,policy,input_check,merge)
    identity=dict(raw,paths=tuple(str(p) for p in paths),dbc_by_channel={channel:str(dbc_path)})
    identity.pop('path',None)
    return SourcePlan(name,source_type,spec,unit,clock.get('timezone'),canonical(identity),metadata_at(raw.get('metadata',{}),path+'.metadata'))
