"""按同次解码值离线生成网格报文，并与未选/未知原帧稳定合并。

输入FrameSample含精确原帧、物理值、实际复用选择器和已知报文事实；本模块
不再读原日志/DBC或调用解码。先用有界磁盘排序按完整身份分组，每组只持相邻
样本，再将生成/透传/未生成说明按时间有界排序。连续量用独立reference或
NumPy内核；基础帧等距取左，只更新允许位。未知报文默认透传，可显式最近邻。
所有暂存、格式对象和输入游标由本owner关闭，失败不发布成品。
"""

from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import groupby
import json
from math import isfinite
from pathlib import Path

from ..core.export_interpolation import linear_reference,linear_numpy
from ..core.models import Interval
from ..execution.history import _metadata_bytes
from ..legacy.records import frame_to_dict,frame_from_dict
from ..timebase.conversion import require_int64_ns,checked_add_ns
from .budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from .codec import _pack,_unpack
from .errors import ResultClosedError
from .frame_exports import ExportCANFrame,SkippedCANFrame
from .frame_patch import FrameRebuildRule,DBCFramePatch
from .frame_sort import FrameSort


@dataclass(frozen=True)
class FrameSample:
    """保同次已解码事实；layout用原始选择器整数，非物理缩放值。"""

    record: ExportCANFrame
    values: tuple[tuple[str,int | float | bool | None],...] = ()
    layout: tuple[tuple[str,int],...] = ()
    known: bool = False
    valid: bool = True

    def __post_init__(self):
        """核冻结值与定位结构。参数: 无。返回: None。异常: 类型/重复字段/布局非法。
        """
        if type(self.record) is not ExportCANFrame or type(self.known) is not bool or type(self.valid) is not bool:
            raise TypeError('重建样本需要真实导出帧和明确布尔事实')
        for pairs,types in ((self.values,(int,float,bool,type(None))),(self.layout,(int,))):
            if type(pairs) is not tuple or len(pairs)>4096:
                raise ValueError('重建样本字段超过有限能力')
            names=set()
            for pair in pairs:
                if type(pair) is not tuple or len(pair)!=2 or type(pair[0]) is not str or not pair[0] or type(pair[1]) not in types or pair[0] in names:
                    raise ValueError('重建样本字段重复或类型非法')
                names.add(pair[0])


@dataclass(frozen=True)
class FrameGridSpec:
    """统一整数网格及明确的插值/最近邻上限，不按文件或批次重新起算。"""

    period_ns: int | None  # None为各已选报文的DBC周期，运行前一次解析。
    origin_ns: int
    max_gap_ns: int
    unknown_policy: str = 'passthrough'
    max_distance_ns: int | None = None

    def __post_init__(self):
        """核网格与未知报文策略。参数: 无。返回: None。异常: 非法时间/策略/距离。
        """
        for name in ('period_ns','origin_ns','max_gap_ns'):
            if name=='period_ns' and self.period_ns is None:continue
            require_int64_ns(getattr(self,name),name)
        if self.period_ns is not None and self.period_ns<=0 or self.max_gap_ns<=0 or self.unknown_policy not in ('passthrough','nearest'):
            raise ValueError('需要正网格/间隔和显式未知策略')
        if self.max_distance_ns is not None:
            require_int64_ns(self.max_distance_ns)
            if self.max_distance_ns<0:
                raise ValueError('最近邻距离不能为负')
        if self.period_ns is None and self.unknown_policy=='nearest':
            raise ValueError('未知报文没有DBC周期；最近邻网格必须给固定period')
        if self.unknown_policy=='nearest' and self.max_distance_ns is None:
            raise ValueError('未知报文最近邻必须声明最大距离')


def _frame_packet(record):
    """编码固定原帧及定位结构。参数: record。返回: JSON dict。异常: 原模型非法。
    """
    frame=frame_to_dict(record.frame)
    if not record.provenance:
        # writer实际用output_time_ns；默认暂存不再保存它的float秒副本。
        frame.pop('timestamp')
    packet={'sequence':record.sequence,'time_ns':record.time_ns,'frame':frame,'frame_origin':record.frame_origin}
    if record.output_time_ns!=record.time_ns:
        packet['output_time_ns']=record.output_time_ns
    if record.provenance:
        packet['provenance']=record.provenance
    return packet


def _restore_frame(packet):
    """恢复本次认证暂存的固定原帧。参数: packet。返回: ExportCANFrame。异常: 非法模型。
    """
    output=packet.get('output_time_ns',packet['time_ns'])
    frame=packet['frame']
    if 'timestamp' not in frame:
        frame=dict(frame,timestamp=output/10**9)
    return ExportCANFrame(packet['sequence'],packet['time_ns'],output,
        frame_from_dict(frame),tuple(tuple(p) for p in packet.get('provenance',())),packet['frame_origin'])


def _sample_packet(sample):
    """保存无效NaN等诊断而不输出非法JSON。参数: sample。返回: 固定dict。异常: 编码错。
    """
    return {'record':_frame_packet(sample.record),'values':_pack(sample.values),'layout':sample.layout,
        'known':sample.known,'valid':sample.valid}


def _restore_sample(packet):
    """恢复已认证样本，不加载DBC。参数: packet。返回: FrameSample。异常: 结构错。
    """
    return FrameSample(_restore_frame(packet['record']),_unpack(packet['values']),
        tuple(tuple(p) for p in packet['layout']),packet['known'],packet['valid'])


def _facts(sample):
    """比较同刻计算事实，排除来源序号但保实际载荷/布局/质量。参数: sample。返回: 有限JSON。异常: 编码错。
    """
    return json.dumps((frame_to_dict(sample.record.frame),sample.record.output_time_ns,
        _pack(sample.values),sample.layout,sample.known,sample.valid),sort_keys=True,allow_nan=False)


class FrameRebuildRead:
    """拥有输入、两份排序仓和有限DBC位域对象；只在完整准备后开放输出。"""

    def __init__(self,records,spec,interval,rules,budget,work_dir,*,backend='numpy',check_cancel=None,periods=None,integrity=True,trace=True):
        """静态核配置并预约资源。参数: records、网格/范围、(rule,已加载Message)tuple、预算/新目录、后端/取消；periods为同次初始化已解析DBC周期。
        返回: 可关闭重建owner。异常: 配置/预算/I/O错，清理失败附frame_rebuild_cleanup_owner。
        """
        if type(spec) is not FrameGridSpec or type(interval) is not Interval or backend not in ('reference','numpy'):
            raise ValueError('报文重建需要网格、范围及明确后端')
        if type(rules) is not tuple or len(rules)>4096 or any(type(p) is not tuple or len(p)!=2 or type(p[0]) is not FrameRebuildRule for p in rules):
            raise ValueError('重建规则需要有限(rule,Message)tuple')
        identities=[(r.channel,r.frame_id,r.is_extended,r.is_fd) for r,_ in rules]
        if len(set(identities))!=len(identities):
            raise ValueError('不能对同一报文身份声明两个重建规则')
        self._budget=budget; self._held_cost=self._fixed_cost=self._group_cost=self._row_cost=0
        self._closed=False; self.ready=False; self.reader=None; self.input_sort=self.output_sort=None
        self.patchers=[]; self.pending_patcher=None; self.cursor=None
        self.spec=spec; self.interval=interval; self.backend=backend; self.check_cancel=check_cancel
        self._export_metadata=None
        self.trace=trace
        self.input_count=self.generated=self.passthrough=self.skipped=0
        self.grid=0
        self._periods=()
        self._group_period=spec.period_ns
        try:
            _reserve_owned_ram(self,2*1048576+_metadata_bytes(tuple(rule for rule,_ in rules))*16,'_fixed_cost')
            self.reader=iter(records)
            if spec.period_ns is None:
                from ..legacy.dbc_cycles import cycle_time_ns
                self._periods=(tuple(cycle_time_ns(message.cycle_time) for _,message in rules) if periods is None else periods)
                if type(self._periods) is not tuple or len(self._periods)!=len(rules) or any(type(p) is not int or not 0<p<(1<<63) for p in self._periods):
                    raise ValueError('DBC逐报文周期与已选规则不符')
            elif periods is not None:
                raise ValueError('固定网格不能再附DBC周期')
            root=Path(work_dir)
            if any(p.casefold()=='refprojects' for p in (*root.parts,*root.resolve().parts)):
                raise ValueError('报文重建不能写RefProjects')
            root.mkdir(parents=True,exist_ok=False)
            self.input_sort=FrameSort(root/'groups',budget,check_cancel=check_cancel,integrity=integrity)
            self.output_sort=FrameSort(root/'timeline',budget,check_cancel=check_cancel,integrity=integrity)
            for rule,message in rules:
                try:
                    self.pending_patcher=DBCFramePatch(rule,message,budget)
                except BaseException as error:
                    self.pending_patcher=getattr(error,'frame_patch_cleanup_owner',None)
                    raise
                self.patchers.append(self.pending_patcher); self.pending_patcher=None
        except BaseException as error:
            # 构造失败也接管尚未赋值成功的真实排序对象。
            if self.input_sort is None:
                self.input_sort=getattr(error,'frame_sort_cleanup_owner',None)
            elif self.output_sort is None:
                self.output_sort=getattr(error,'frame_sort_cleanup_owner',None)
            _cleanup_owner(self,error,'frame_rebuild_cleanup_owner','报文重建构造')
            raise

    def _cancel(self):
        """检查已关闭及用户取消。参数: 无。返回: None。异常: 关闭/取消。
        """
        if self._closed:
            raise ResultClosedError('报文重建已关闭')
        if self.check_cancel is not None:
            self.check_cancel()

    def _output(self,item,identity=()):
        """保存真实/生成/未生成结果到时间排序。参数: item和有限身份。返回: None。异常: 排序/配额错。
        """
        if type(item) is SkippedCANFrame:
            packet={'skip':True,'time_ns':item.time_ns,'reason':item.reason,'details':item.details}
            key=(item.time_ns,2,0,str(identity)); self.skipped+=1
        else:
            packet={'skip':False,'record':_frame_packet(item)}
            key=(item.time_ns,int(item.frame_origin=='generated'),item.sequence,str(identity))
            if item.frame_origin=='generated':
                self.generated+=1
            else:
                self.passthrough+=1
        self.output_sort.append(key,packet)

    def prepare(self):
        """单次消费同次样本，按身份重建并封口时间序列。参数: 无。返回: self。异常: 输入/解码事实/排序/预算/取消。
        """
        self._cancel()
        if self.ready:
            return self
        try:
            last=sequence=None
            for sample in self.reader:
                self._cancel()
                if type(sample) is not FrameSample:
                    raise TypeError('报文重建需要同次FrameSample流')
                record=sample.record
                _reserve_owned_ram(self,1048576+_metadata_bytes((sample.values,sample.layout,record.provenance))*32,'_row_cost')
                try:
                    if last is not None and (record.time_ns<last or record.sequence<=sequence):
                        raise ValueError('原帧时间或原序回退，不能借离线排序掩盖输入错误')
                    last=record.time_ns; sequence=record.sequence; self.input_count+=1
                    if not self.interval.start_ns<=record.time_ns<self.interval.end_ns:
                        continue
                    frame=record.frame
                    if frame.is_rx is None:
                        raise ValueError('原始报文重建需要收发方向is_rx')
                    matched=[i for i,p in enumerate(self.patchers) if p.rule.matches(frame)]
                    if len(matched)>1:
                        raise ValueError('同一实际帧匹配多个重建规则，请收紧帧类型约束')
                    rule_index=matched[0] if matched else None
                    rebuild=not(frame.is_error_frame or frame.is_remote_frame) and (
                        rule_index is not None or not sample.known and self.spec.unknown_policy=='nearest')
                    if not rebuild:
                        self._output(record); continue
                    if rule_index is not None and (not sample.known or frame.dlc!=len(frame.data)
                            or len(frame.data)!=self.patchers[rule_index].message.length):
                        raise ValueError('已选报文缺真实DBC解码身份或长度异常')
                    if rule_index is not None:
                        self.patchers[rule_index].accept_frame(frame)
                    # 收发方向/实际帧型/通道分组，布局切换留在组内作为明确禁止跨越的边界。
                    identity=(rule_index if rule_index is not None else -1,json.dumps(frame.channel),frame.arbitration_id,
                        int(frame.is_extended_id),int(frame.is_fd),int(frame.is_rx))
                    self.input_sort.append(identity+(record.time_ns,record.sequence),_sample_packet(sample))
                finally:
                    _release_owned_ram(self,self._row_cost,'_row_cost')
            self._close_input(); self.input_sort.seal()
            for identity,rows in groupby(self.input_sort.rows(),key=lambda row:row[0][:-2]):
                patcher=self.patchers[identity[0]] if identity[0]>=0 else None
                size=0 if patcher is None else len(patcher.rule.continuous)
                _reserve_owned_ram(self,8*1048576+size*16384,'_group_cost')
                try:
                    self._group((_restore_sample(row[2]) for row in rows),patcher,identity)
                finally:
                    _release_owned_ram(self,self._group_cost,'_group_cost')
            self.output_sort.seal()
            self._export_metadata={'period_ns':self.spec.period_ns,'origin_ns':self.spec.origin_ns,
                'max_gap_ns':self.spec.max_gap_ns,'unknown_policy':self.spec.unknown_policy,
                'max_distance_ns':self.spec.max_distance_ns,'backend':self.backend,
                'quantization':'nearest_even-v1','quantization_input':'decimal_endpoints_integer_time',
                'range_ns':(self.interval.start_ns,self.interval.end_ns),'input_frames':self.input_count,
                'generated':self.generated,'passthrough':self.passthrough,'skipped':self.skipped,
                'checksum_recomputed':False,'rules':tuple({'channel':p.rule.channel,'frame_id':p.rule.frame_id,
                    **({} if p.rule.is_extended is None else {'is_extended':p.rule.is_extended}),
                    **({} if p.rule.is_fd is None else {'is_fd':p.rule.is_fd}),
                    'continuous':p.rule.continuous,'protected':p.rule.protected,
                    'same_time_policy':p.rule.same_time_policy,
                    **({'period_ns':self._periods[i]} if self.spec.period_ns is None else {})}
                    for i,p in enumerate(self.patchers))}
            if self.spec.period_ns is None:
                del self._export_metadata['period_ns']
                self._export_metadata['period_mode']='dbc'
            self.ready=True
            return self
        except BaseException as error:
            _cleanup_owner(self,error,'frame_rebuild_cleanup_owner','报文重建')
            raise

    def _group(self,samples,patcher,identity):
        """保相邻两个同刻组并处理全部网格。参数: 单身份样本流、patcher或None、identity。返回: None。异常: 原重建错。
        """
        spec=self.spec
        self._group_period=spec.period_ns if spec.period_ns is not None else self._periods[identity[0]]
        period=self._group_period
        self.grid=spec.origin_ns+((self.interval.start_ns-spec.origin_ns+period-1)//period)*period
        left=pending=None; left_bad=pending_bad=False
        for sample in samples:
            self._cancel()
            if pending is not None and sample.record.time_ns==pending.record.time_ns:
                if patcher is not None and patcher.rule.same_time_policy=='last_by_sequence':
                    if sample.record.sequence>pending.record.sequence:
                        pending=sample
                else:
                    pending_bad=pending_bad or _facts(sample)!=_facts(pending)
                continue
            if pending is not None:
                self._segment(left,pending,left_bad,pending_bad,patcher,identity)
                left,left_bad=pending,pending_bad
            pending=sample; pending_bad=False
        if pending is not None:
            self._segment(left,pending,left_bad,pending_bad,patcher,identity)
            self._segment(pending,None,pending_bad,False,patcher,identity)

    def _reason(self,left,right,left_bad,right_bad,patcher):
        """确定整个两点间隔是否可插值。参数: 两端及冲突、patcher。返回: 原因或None。异常: 非法DBC布局。
        """
        if left_bad or right_bad:
            return 'same_time_conflict'
        if left is None:
            return 'missing_left'
        if right is None:
            return 'missing_right'
        if left.layout!=right.layout:
            return 'layout_changed'
        if left.record.output_time_ns-left.record.time_ns!=right.record.output_time_ns-right.record.time_ns:
            return 'time_mapping_changed'
        if not left.valid or not right.valid:
            return 'invalid_neighbor'
        names=patcher.selected(left.layout)
        if not names:
            return 'inactive_layout'
        for sample in (left,right):
            values=dict(sample.values)
            if any(type(values.get(n)) not in (int,float) or not isfinite(values[n]) for n in names):
                return 'invalid_neighbor'
        if right.record.time_ns-left.record.time_ns>self.spec.max_gap_ns:
            return 'gap_too_large'
        return None

    def _skip(self,time_ns,reason,identity):
        """记录整个目标帧未生成，不补任一物理字段。参数: time_ns/reason/identity。返回: None。异常: 输出错。
        """
        self._output(SkippedCANFrame(time_ns,reason,json.dumps({'identity':identity},ensure_ascii=False) if self.trace else ''),identity)

    def _emit(self,time_ns,base,left,right,patcher,values,identity,mode):
        """从同一基础帧生成目标并保完整两端引用。参数: 目标/基础/两端、位域器和值、身份/模式。返回: None。异常: 量化/输出错。
        """
        frame=base.record.frame; quantization=()
        if values is not None:
            # 数组结果是物理估计；离散码值的恰半边界另用原十进制值及整数时间证明。
            # 这是编码舍入，不重算状态、不读取原载荷，也不将参考内核当NumPy实现。
            a=dict(left.values); b=dict(right.values)
            ratio=Fraction(time_ns-left.record.time_ns,right.record.time_ns-left.record.time_ns)
            exact={name:Fraction(str(a[name]))+(Fraction(str(b[name]))-Fraction(str(a[name])))*ratio for name in values}
            frame,quantization=patcher.patch(frame,values,base.layout,exact_values=exact,trace=self.trace)
        output_ns=checked_add_ns(base.record.output_time_ns,time_ns-base.record.time_ns)
        provenance=()
        if self.trace:
            details={'mode':mode,'base_sequence':base.record.sequence,'base_ref':dict(base.record.provenance),
                'left_sequence':None if left is None else left.record.sequence,
                'right_sequence':None if right is None else right.record.sequence,
                'left_ref':None if left is None else dict(left.record.provenance),
                'right_ref':None if right is None else dict(right.record.provenance),
                'layout':base.layout,'quantization_rule':'nearest_even-v1','quantization':quantization,
                'checksum_recomputed':False}
            provenance=(('reconstruction',json.dumps(details,ensure_ascii=False,allow_nan=False,separators=(',',':'))),)
        result=ExportCANFrame(base.record.sequence,time_ns,output_ns,replace(frame,timestamp=output_ns/10**9),provenance,'generated')
        self._output(result,identity)

    def _nearest(self,time_ns,left,right,left_bad,right_bad,identity):
        """未知报文整帧最近邻，等距选左且不越最大距离。参数: 时间/两端及冲突/身份。返回: None。异常: 输出错。
        """
        choices=[s for s,bad in ((left,left_bad),(right,right_bad)) if s is not None and not bad and s.valid]
        if not choices:
            self._skip(time_ns,'same_time_conflict' if left_bad or right_bad else 'no_neighbor',identity); return
        base=min(choices,key=lambda s:(abs(s.record.time_ns-time_ns),s.record.time_ns))
        if abs(base.record.time_ns-time_ns)>self.spec.max_distance_ns:
            self._skip(time_ns,'neighbor_too_far',identity); return
        self._emit(time_ns,base,left,right,None,None,identity,'nearest_frame')

    def _segment(self,left,right,left_bad,right_bad,patcher,identity):
        """每块最多256网格点计算连续量，实点另外保原字节。参数: 两端/冲突、patcher、identity。返回: None。异常: 原计算/输出错。
        """
        stop=self.interval.end_ns if right is None else min(right.record.time_ns,self.interval.end_ns)
        reason=None if patcher is None else self._reason(left,right,left_bad,right_bad,patcher)
        while self.grid<stop:
            self._cancel()
            count=min(256,(stop-self.grid+self._group_period-1)//self._group_period)
            times=tuple(self.grid+i*self._group_period for i in range(count))
            arrays={}
            if patcher is not None and reason is None:
                names=patcher.selected(left.layout); a=dict(left.values); b=dict(right.values)
                function=linear_reference if self.backend=='reference' else linear_numpy
                arrays={n:function(times,left.record.time_ns,right.record.time_ns,a[n],b[n]) for n in names}
            for index,time in enumerate(times):
                if patcher is None:
                    self._nearest(time,left,right,left_bad,right_bad,identity)
                elif reason is not None:
                    self._skip(time,reason,identity)
                else:
                    base=left if time-left.record.time_ns<=right.record.time_ns-time else right
                    self._emit(time,base,left,right,patcher,{n:float(values[index]) for n,values in arrays.items()},identity,'linear')
            self.grid+=count*self._group_period
        if right is not None and self.grid==right.record.time_ns and self.grid<self.interval.end_ns:
            if patcher is None:
                self._nearest(self.grid,right,right,right_bad,right_bad,identity)
            elif right_bad:
                self._skip(self.grid,'same_time_conflict',identity)
            else:
                names=patcher.selected(right.layout); values=dict(right.values)
                if not right.valid or not names or any(type(values.get(n)) not in (int,float) or not isfinite(values[n]) for n in names):
                    self._skip(self.grid,'invalid_update',identity)
                else:
                    self._emit(self.grid,right,right,right,patcher,None,identity,'observed')
            self.grid+=self._group_period

    def __iter__(self):
        """准备完成后开放一个时间游标。参数: 无。返回: self。异常: 准备或重复游标错。
        """
        self.prepare()
        if self.cursor is None:
            self.cursor=self.output_sort.rows()
        return self

    @property
    def export_metadata(self):
        """返回本次已完成重建的有限清单事实。参数: 无。返回: dict或None。异常: 无。
        """
        return self._export_metadata

    def __next__(self):
        """恢复下一生成/透传帧或缺失说明。参数: 无。返回: ExportCANFrame/SkippedCANFrame。异常: EOF/校验错。
        """
        if self.cursor is None:
            iter(self)
        self._cancel(); packet=next(self.cursor)[2]
        if packet['skip']:
            return SkippedCANFrame(packet['time_ns'],packet['reason'],packet['details'])
        return _restore_frame(packet['record'])

    def _close_input(self):
        """真正关闭源样本游标。参数: 无。返回: None。异常: 原关闭错保责任。
        """
        if self.reader is not None:
            close=getattr(self.reader,'close',None)
            if close is not None:
                close()
            self.reader=None

    def close(self):
        """关闭真实所有权后释放费用，保诊断暂存。参数: 无。返回: None。异常: 原关闭/释放错可重试。
        """
        if self._closed:
            return
        self._close_input()
        if self.cursor is not None:
            self.cursor.close(); self.cursor=None
        for owner in (self.input_sort,self.output_sort,self.pending_patcher,*self.patchers):
            if owner is not None:
                owner.close()
        self.patchers.clear(); self.pending_patcher=None
        _release_owned_ram(self,self._row_cost,'_row_cost')
        _release_owned_ram(self,self._group_cost,'_group_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost'); self._closed=True
