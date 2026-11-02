"""解释独立的信号CSV和CAN报文输出选项，默认均关闭。

只构造已实现低层导出的类型化规格；不加载DBC、不读取输入或输出文件。
信号分类使用明确别名，报文重建用明确原字段，范围引用既有会话或窗口。
日期规则按用户确认检查，未支持的选项严格拒绝，不让schema接受空实现。
"""

from dataclasses import dataclass

from ..core.types import SignalDType
from ..results.signal_exports import SignalCSVExportSpec
from ..results.signal_grid import SignalGridSpec
from ..results.frame_exports import FrameExportSpec
from ..results.frame_rebuild import FrameGridSpec
from ..results.frame_patch import FrameRebuildRule
from .checks import (PlanValidationError,array_at,choice_at,coordinate_at,duration_at,model_at,object_at,text_at)
from ..core.validation import require_identifier


@dataclass(frozen=True)
class SignalCSVOutput:
    """保存信号表输出规格及范围，不拥有运行时历史或文件。"""

    spec: SignalCSVExportSpec
    scope: str = 'session'
    window: str | None = None
    period_driver: str | None = None  # 仅DBC信号网格，已解析的原始报文别名。

    def __post_init__(self):
        """校验冻结声明，typed构造同样受约束。参数: 字段。返回: None。异常: 类型/范围错。
        """
        if type(self.spec) is not SignalCSVExportSpec:
            raise TypeError('signal_csv需要SignalCSVExportSpec')
        _typed_scope(self.scope,self.window)
        if self.period_driver is not None:
            require_identifier(self.period_driver,'signal_csv.resampling.period.driver')
        if (self.period_driver is not None)!=(self.spec.resampling is not None and self.spec.resampling.period_ns is None):
            raise ValueError('DBC信号网格需要已解析驱动，固定网格不能附带驱动')


@dataclass(frozen=True)
class CANFramesOutput:
    """保存一个来源的原始/重建帧输出规格，与信号表的网格和开关独立。"""

    source: str
    spec: FrameExportSpec
    scope: str = 'session'
    window: str | None = None
    resampling: FrameGridSpec | None = None
    rules: tuple[FrameRebuildRule,...] = ()

    def __post_init__(self):
        """校验来源、独立规格和重建规则。参数: 字段。返回: None。异常: 类型/范围错。
        """
        require_identifier(self.source,'can_frames.source'); _typed_scope(self.scope,self.window,allow_all=True)
        if type(self.spec) is not FrameExportSpec or self.resampling is not None and type(self.resampling) is not FrameGridSpec:
            raise TypeError('can_frames需要冻结帧规格与可选网格')
        if type(self.rules) is not tuple or len(self.rules)>4096 or any(type(r) is not FrameRebuildRule for r in self.rules):
            raise TypeError('重建规则需要有限FrameRebuildRule tuple')
        if self.rules and self.resampling is None:
            raise ValueError('未启用重采样不能配置重建规则')
        identities={(r.channel,r.frame_id,r.is_extended,r.is_fd) for r in self.rules}
        if len(identities)!=len(self.rules) or self.resampling is not None and not self.rules and self.resampling.unknown_policy!='nearest':
            raise ValueError('重建规则重复或没有可执行规则')


def _typed_scope(scope,window,*,allow_all=False):
    """核typed范围与窗口配对。参数: scope/window。返回: None。异常: 不支持或组合错误。
    """
    if scope not in ('session','segments') or scope=='session' and window is not None:
        raise ValueError('导出范围错误')
    if scope=='segments' and not (allow_all and window is None):
        require_identifier(window,'exports.window')


def require_export_options(plan):
    """核typed选项引用当前来源/信号/窗口，不读DBC。参数: plan。返回: None。异常: 声明或引用错误。
    """
    windows={w.window_id for w in plan.windows}; definitions={s.definition.name:s.definition for s in plan.signals}
    for export_type,expected in (('signal_csv',SignalCSVOutput),('can_frames',CANFramesOutput)):
        option=getattr(plan.outputs,export_type)
        if option is None:
            continue
        if type(option) is not expected:
            raise TypeError(export_type+'需要冻结typed输出声明')
        option.__post_init__()
        if option.scope=='segments' and not ((export_type=='can_frames') and (option.window is None)) and option.window not in windows:
            raise ValueError('导出窗口未在当前计划声明')
        if export_type=='signal_csv':
            if any(name not in definitions for name in option.spec.signals):
                raise ValueError('导出信号未在当前计划声明')
            if option.spec.resampling is not None and any(definitions[name].dtype not in
                    (SignalDType.FLOAT64,SignalDType.INT64,SignalDType.UINT64) for name in option.spec.resampling.continuous):
                raise ValueError('状态/枚举信号不能线性插值')
            if option.period_driver is not None:
                _signal_grid_driver(definitions,plan.sources,option.spec.resampling.continuous,option.period_driver,'$.outputs.signal_csv')
        else:
            source=next((s for s in plan.sources if s.name==option.source),None)
            if source is None or source.source_type not in ('can_blf','can_asc','asc_or_blf','raw_can_csv'):
                raise ValueError('报文导出需要本计划CAN来源')
            _require_frame_direction(source)
            if any(rule.channel!=source.config.channel for rule in option.rules):
                raise ValueError('重建报文通道与来源不同')


def _scope(raw,path,windows,*,allow_all=False):
    """核会话或单个显式窗口引用。参数: raw/path/windows。返回: (scope,window)。异常: 配置错。
    """
    scope=choice_at(raw.get('scope','session'),('session','segments'),path+'.scope')
    window=raw.get('window')
    if scope=='session' and window is not None:
        raise PlanValidationError(path+'.window','session范围不能同时指定窗口')
    if scope=='segments' and not (allow_all and 'window' not in raw):
        window=text_at(window,path+'.window',identifier=True)
        if window not in {item.window_id for item in windows}:
            raise PlanValidationError(path+'.window','未知窗口：'+window)
    return scope,window


def _grid(raw,path):
    """解析显式单位的全局网格。参数: raw/path。返回: period/origin/max_gap整数ns。异常: 时间错。
    """
    return (duration_at(raw['period'],path+'.period',positive=True),
        coordinate_at(raw.get('origin','0s'),path+'.origin'),duration_at(raw['max_gap'],path+'.max_gap',positive=True))


def _signal_grid_driver(definitions,sources,continuous,driver,path):
    """同一信号网格使用一个明确DBC周期；多报文不能擅自选最快周期。

    参数: 有限定义/来源/连续量/可选驱动/路径。返回: 唯一原始别名。异常: 类型/格式/歧义。
    """
    from ..sources.can_spec import can_field_from_key
    source_types={source.name:source.source_type for source in sources}
    candidates={}
    for name in continuous:
        definition=definitions[name]
        if source_types[definition.source] not in ('can_blf','can_asc','asc_or_blf','raw_can_csv'):
            raise PlanValidationError(path+'.resampling.period','已解析信号不能选择DBC周期')
        field=can_field_from_key(definition.field)
        candidates.setdefault((definition.source,field.channel,field.frame_id,field.is_extended,field.is_fd),name)
    if driver is not None:
        if type(driver) is not str or driver not in continuous:
            raise PlanValidationError(path+'.resampling.period.driver','驱动须属于本次连续原始信号')
        return driver
    if len(candidates)!=1:
        raise PlanValidationError(path+'.resampling.period.driver','多个报文周期需要明确指定驱动信号')
    return next(iter(candidates.values()))


def parse_signal_output(value,signals,windows,*,sources=()):
    """核显式信号选择及连续量分类。参数: value、当前信号/窗口。返回: SignalCSVOutput或None。异常: 定位配置错。
    """
    if value is None:
        return None
    path='$.outputs.signal_csv'
    raw=object_at(value,path,('signals',),('scope','window','resampling'))
    names=tuple(array_at(raw['signals'],path+'.signals'))
    definitions={s.definition.name:s.definition for s in signals}
    if any(type(n) is not str or n not in definitions for n in names):
        raise PlanValidationError(path+'.signals','导出信号必须为已定义的原信号别名')
    grid=None;driver=None
    if raw.get('resampling') is not None:
        res=object_at(raw['resampling'],path+'.resampling',('continuous','period','max_gap'),('origin',))
        continuous=tuple(array_at(res['continuous'],path+'.resampling.continuous'))
        if any(type(n) is not str or n not in definitions or definitions[n].dtype not in
                (SignalDType.FLOAT64,SignalDType.INT64,SignalDType.UINT64) for n in continuous):
            raise PlanValidationError(path+'.resampling.continuous','连续量必须为当前已定义的数值信号，状态/枚举不能插值')
        if type(res['period']) is dict:
            period_choice=object_at(res['period'],path+'.resampling.period',('mode',),('driver',))
            if 'driver' in period_choice and type(period_choice['driver']) is not str:
                raise PlanValidationError(path+'.resampling.period.driver','显式driver必须为信号名称')
            if period_choice['mode']!='dbc':raise PlanValidationError(path+'.resampling.period.mode','网格对象需dbc，固定周期使用带单位数值')
            driver=_signal_grid_driver(definitions,sources,continuous,period_choice.get('driver'),path)
            period=None
            origin=coordinate_at(res.get('origin','0s'),path+'.resampling.origin')
            gap=duration_at(res['max_gap'],path+'.resampling.max_gap',positive=True)
        else:
            period,origin,gap=_grid(res,path+'.resampling')
        grid=model_at(SignalGridSpec,path+'.resampling',continuous,period,origin,gap)
    spec=model_at(SignalCSVExportSpec,path,names,grid)
    scope,window=_scope(raw,path,windows)
    return SignalCSVOutput(spec,scope,window,driver)


def _require_frame_direction(source):
    """只有原帧导出/重建需要收发方向；分析可保留未知方向。"""
    if source.source_type == 'raw_can_csv' and any(
            'is_rx' not in item.layout.fields for item in source.config.inputs):
        raise PlanValidationError('$.outputs.can_frames',
            '原始报文导出或重建需要收发方向，请在CSV字段映射中提供is_rx；普通分析可以省略')


def parse_frame_output(value,sources,windows):
    """核帧来源、日期和可选重建规则。参数: value、当前来源/窗口。返回: CANFramesOutput或None。异常: 定位配置错。
    """
    if value is None:
        return None
    path='$.outputs.can_frames'
    raw=object_at(value,path,('format',),('source','scope','window','resampling','output_offset',
        'source_time_reference','capture_date','timezone_offset_minutes'))
    from .input_defaults import source_reference
    source=source_reference(raw,sources,path,can_only=True)
    declared=next((s for s in sources if s.name==source),None)
    if declared is None or declared.source_type not in ('can_blf','can_asc','asc_or_blf','raw_can_csv'):
        raise PlanValidationError(path+'.source','报文导出需要当前已支持的CAN来源')
    _require_frame_direction(declared)
    reference=raw.get('source_time_reference','epoch' if declared.config.timebase.time_type.value=='absolute' else 'relative')
    spec=model_at(FrameExportSpec,path,choice_at(raw['format'],('asc','blf'),path+'.format'),
        coordinate_at(raw.get('output_offset','0s'),path+'.output_offset'),reference,
        raw.get('capture_date'),raw.get('timezone_offset_minutes'))
    scope,window=_scope(raw,path,windows,allow_all=True)
    grid=None; rules=[]
    if raw.get('resampling') is not None:
        res=object_at(raw['resampling'],path+'.resampling',('period','max_gap','messages'),
            ('origin','unknown_policy','max_distance'))
        if type(res['period']) is dict:
            choice=object_at(res['period'],path+'.resampling.period',('mode',),())
            if (choice['mode']!='dbc'):
                raise PlanValidationError(path+'.resampling.period','按各报文DBC周期重采样时，period.mode必须为dbc')
            period=None
            origin=coordinate_at(res.get('origin','0s'),path+'.resampling.origin')
            gap=duration_at(res['max_gap'],path+'.resampling.max_gap',positive=True)
        else:
            period,origin,gap=_grid(res,path+'.resampling')
        distance=duration_at(res['max_distance'],path+'.resampling.max_distance',positive=False) if 'max_distance' in res else None
        grid=model_at(FrameGridSpec,path+'.resampling',period,origin,gap,res.get('unknown_policy','passthrough'),distance)
        for index,item in enumerate(array_at(res['messages'],path+'.resampling.messages')):
            where=f'{path}.resampling.messages[{index}]'
            item=object_at(item,where,('frame_id','continuous'),('channel','is_extended','is_fd','protected','same_time_policy'))
            # 省略表示自动识别；显式null不能悄悄取得默认行为。
            for flag in ('is_extended','is_fd'):
                if flag in item and type(item[flag]) is not bool:
                    raise PlanValidationError(where+'.'+flag,'填写时需要bool；自动识别请省略该项')
            from .channels import channel_index
            channel = channel_index(item['channel'],where+'.channel') if 'channel' in item else declared.config.channel
            rule=model_at(FrameRebuildRule,where,channel,item['frame_id'],
                tuple(array_at(item['continuous'],where+'.continuous')),item.get('is_extended'),item.get('is_fd'),
                tuple(array_at(item.get('protected',[]),where+'.protected')),item.get('same_time_policy','error'))
            if rule.channel!=declared.config.channel:
                raise PlanValidationError(where+'.channel','重建规则通道必须匹配来源的DBC通道')
            rules.append(rule)
        identities=[(r.channel,r.frame_id,r.is_extended,r.is_fd) for r in rules]
        if len(rules)>4096 or len(set(identities))!=len(rules):
            raise PlanValidationError(path+'.resampling.messages','报文规则重复或超过4096项')
        if not rules and grid.unknown_policy!='nearest':
            raise PlanValidationError(path+'.resampling.messages','重建需明确报文清单或未知报文最近邻策略')
    return CANFramesOutput(source,spec,scope,window,grid,tuple(rules))
