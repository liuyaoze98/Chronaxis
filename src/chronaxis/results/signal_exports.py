"""将指定信号的已解码历史写为原始采样及可选连续量网格CSV长表。

输入为同次读取生成的HistorySample/HistoryProgress流及显式导出范围，不打开日志
或DBC；输出original.csv及清单，启用线性时另写resampled.csv。异步信号分别
一行，状态/计数不补点；显式连续量交给独立有界网格owner。
值无效时留空并保质量原因和完整来源引用；原无效值以既有安全编码保存。
逐行缓冲和编码先付预算，输入正常/失败/取消均关闭，整个目录最终独占发布。
"""

import csv
from dataclasses import dataclass
from io import StringIO
import json

from ..core.models import Interval
from ..core.validation import require_identifier
from ..execution.record_sample import RecordSample
from ..execution.history_records import HistorySample, HistoryProgress, estimate_record_bytes
from ..execution.history import _metadata_bytes
from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .codec import _pack
from .export_files import ExportFiles
from .signal_grid import SignalGridSpec, SignalGrid


@dataclass(frozen=True)
class SignalCSVExportSpec:
    """指定待导出的已绑定别名；字段含义和单位沿用原绑定，不由文件名推断。"""

    signals: tuple[str,...]  # 唯一非空别名，最多4096，保持配置顺序。
    resampling: SignalGridSpec | None = None  # 默认原始采样，显式连续量才进入线性网格。

    def __post_init__(self):
        """只核静态选择。参数: 无。返回: None。异常: 类型/数量/重复或非法别名。
        """
        if type(self.signals) is not tuple or not 1 <= len(self.signals) <= 4096:
            raise ValueError('信号CSV需要1到4096个显式别名')
        for name in self.signals:
            require_identifier(name,'signal_csv_export.signal')
        if len(set(self.signals)) != len(self.signals):
            raise ValueError('信号CSV别名重复')
        if self.resampling is not None and (type(self.resampling) is not SignalGridSpec
                or any(name not in self.signals for name in self.resampling.continuous)):
            raise ValueError('重采样必须是所选信号的明确子集')


_COLUMNS = ('time_ns','source','signal','field','value','unit','valid','quality','status',
            'sequence','source_ref_json','original_value_json')


def _csv_bytes(values):
    """编码一个有界CSV行。参数: values有限标量列表。返回: UTF8 bytes。异常: CSV/Unicode/内存错。
    """
    # newline交由CSV处理，引号、逗号和换行按标准转义，不拼接未经转义的来源文字。
    stream = StringIO(newline='')
    csv.writer(stream,lineterminator='\n').writerow(values)
    return stream.getvalue().encode('utf-8')


def _sample_row(sample, compact=False):
    """提取原样本可读列及完整证据。参数: sample已校验HistorySample，compact关闭原文/来源列。返回: 行tuple。异常: 安全编码错。
    """
    value = sample.value
    if compact:
        return (sample.time_ns,sample.name,value.value if value.valid else '',sample.unit,int(value.quality))
    return (sample.time_ns,sample.source_ref.source_name,sample.name,sample.source_ref.field,
            value.value if value.valid else '',sample.unit,value.valid,int(value.quality),
            'observed' if value.valid else 'invalid',sample.sequence,
            json.dumps(_pack(sample.source_ref),ensure_ascii=False,allow_nan=False,separators=(',',':')),
            json.dumps(_pack(sample.original_value),ensure_ascii=False,allow_nan=False,separators=(',',':'))
                if sample.original_present else '')


def _reference_json(sample):
    """编码实际端点引用。参数: sample或None。返回: JSON文本或空字符串。异常: 安全编码错。
    """
    return '' if sample is None else json.dumps(_pack(sample.source_ref),ensure_ascii=False,
                                                allow_nan=False,separators=(',',':'))


def _write_grid(owner, rows, counts, compact=False):
    """有界编码网格行及两端引用。参数: owner/rows/固定计数字典及compact引用开关。返回: None。异常: 编码/预算/I/O/取消错。
    """
    owner.select_file('resampled.csv')
    for row in rows:
        _reserve_owned_ram(owner,8192+_metadata_bytes(row)*16,'_row_cost')
        try:
            # 左右时间和引用均来自实际采样，目标时间不伪装成原行记录。
            left,right=row.left,row.right
            values=(row.time_ns,row.name,'' if row.value is None else row.value,row.unit,
                row.status,row.reason,row.quality)
            if not compact:
                values+=('' if left is None else left.time_ns,'' if right is None else right.time_ns,
                    _reference_json(left),_reference_json(right))
            owner.append(_csv_bytes(values))
            counts[row.status]+=1
        finally:
            _release_owned_ram(owner,owner._row_cost,'_row_cost')


class SignalCSVWriter(ExportFiles):
    """复用原写文件和线性网格，支持逐样本推进而不强制暂存整份输入。"""

    def __init__(self,spec,interval,destination,budget,*,device_label,check_cancel=None,
                 definitions=(),backend='numpy',compact=False,integrity=True,timestamped=False):
        """预付输出状态并建立所需表。参数: 导出规格/范围/目标/预算与后端。返回: owner。异常: 原构造错。"""
        if type(compact) is not bool:
            raise TypeError('compact必须为bool')
        if type(spec) is not SignalCSVExportSpec or type(interval) is not Interval:
            raise TypeError('信号导出需要选择及明确Interval')
        if (device_label not in ('home','work') or backend not in ('reference','numpy')
                or check_cancel is not None and not callable(check_cancel)):
            raise ValueError('导出需要实际设备标签及可选取消回调')
        super().__init__(destination,budget,integrity=integrity,timestamped=timestamped)
        self.spec,self.interval,self.definitions=spec,interval,definitions
        self.device_label,self.backend,self.compact=device_label,backend,compact
        self._check_cancel=check_cancel
        self._count=self._invalid=0
        self._grid_counts={'observed':0,'estimated':0,'missing':0}
        self._selected=None
        try:
            _reserve_owned_ram(self,4096+sum(len(n.encode('utf-8'))*16+256 for n in spec.signals),'_fixed_cost')
            self._selected=set(spec.signals)
            if spec.resampling is not None:
                try:
                    self.worker=SignalGrid(spec.resampling,definitions,interval,budget,
                        backend=backend,check_cancel=check_cancel)
                except BaseException as error:
                    self.worker=getattr(error,'signal_grid_cleanup_owner',None);raise
                self.open_file('resampled.csv')
                self.append(_csv_bytes(('time_ns','signal','value','unit','status','reason','quality')+
                    (() if compact else ('left_time_ns','right_time_ns','left_ref_json','right_ref_json'))))
            if not compact or spec.resampling is None or self._selected-set(spec.resampling.continuous):
                self.select_file('original.csv')
                self.append(_csv_bytes(('time_ns','signal','value','unit','quality') if compact else _COLUMNS))
        except BaseException as error:
            self._failed = True
            _cleanup_owner(self,error,'export_cleanup_owner','信号CSV构造');raise

    def push(self,sample):
        """写一个已验证样本或推进原网格。参数: HistorySample/Progress。返回: None。异常: 原输入/写入错。"""
        if self._closed:
            raise ValueError('信号导出已关闭')
        if self._check_cancel is not None: self._check_cancel()
        if type(sample) is HistoryProgress: return
        if type(sample) not in (HistorySample,RecordSample):
            raise TypeError('信号导出只接受已解码历史记录')
        if sample.name not in self._selected or not self.interval.start_ns<=sample.time_ns<self.interval.end_ns:
            return
        if self.worker is not None and sample.name in self.spec.resampling.continuous:
            _write_grid(self,self.worker.push(sample),self._grid_counts,self.compact)
            return
        _reserve_owned_ram(self,estimate_record_bytes(sample)*2,'_row_cost')
        try:
            self.select_file('original.csv')
            self.append(_csv_bytes(_sample_row(sample,self.compact)))
        finally:
            _release_owned_ram(self,self._row_cost,'_row_cost')
        self._count+=1;self._invalid+=not sample.value.valid

    def observed_end(self,end_ns):
        """在线调用方在末组交付前收紧EOF；不能用它改已经写出的记录。

        参数: 实际末端，须在初始范围中。返回: None。异常: 越界。
        """
        if not self.interval.start_ns<=end_ns<=self.interval.end_ns:
            raise ValueError('导出末端超出声明范围')
        self.interval=Interval(self.interval.start_ns,end_ns)
        if self.worker is not None: self.worker.interval=self.interval

    def complete(self):
        """结束网格、写一次必要清单并原子发布。参数: 无。返回: 输出Path。异常: 原完成错。"""
        interval,spec=self.interval,self.spec
        metadata={'export_type':'signal_csv','device_label':self.device_label,'signals':spec.signals,
            'range_ns':(interval.start_ns,interval.end_ns),'resampling':False,
            'rows':self._count,'observed':self._count-self._invalid,'invalid':self._invalid}
        if self.worker is not None:
            _write_grid(self,self.worker.finish(),self._grid_counts,self.compact)
            grid=spec.resampling
            metadata.update(resampling={'mode':'linear','continuous':grid.continuous,
                'period_ns':grid.period_ns,'origin_ns':grid.origin_ns,'max_gap_ns':grid.max_gap_ns,
                'causal':False,'numeric':'float64_estimate','ordering':'per_signal_monotonic'},
                resampled_counts=self._grid_counts,backend=self.backend,
                bindings=tuple({'name':d.name,'source':d.source,'field':d.field,'unit':d.unit,
                    'dtype':d.dtype.value,'same_time_policy':d.same_time_policy}
                    for d in self.definitions if d.name in grid.continuous))
        if self.compact: metadata['row_format']='compact-v2'
        return self.finish(metadata)


def export_signal_csv(records,spec,interval,destination,budget,*,device_label,check_cancel=None,
                      definitions=(),backend='numpy',compact=False,integrity=True,file_consumer=None):
    """消费既有记录流并复用在线写出器，保原公开调用与关闭责任。

    参数: 可关闭记录流、规格/范围/目标/预算；设备、取消、绑定、后端、精简开关。
    integrity只在请求时计算文件摘要；file_consumer接收写入时取得的有限文件身份，供内部登记复用。
    返回: 公开ExportManifest含实际路径；内部file_consumer模式返回Path。异常: 原格式/输入/预算/取消错；清理失败附真实owner。
    """
    if file_consumer is not None and not callable(file_consumer):
        raise TypeError('file_consumer须为回调')
    owner=SignalCSVWriter(spec,interval,destination,budget,device_label=device_label,
        check_cancel=check_cancel,definitions=definitions,backend=backend,compact=compact,integrity=integrity,
        timestamped=file_consumer is None)
    try:
        owner.reader=iter(records)
        for sample in owner.reader: owner.push(sample)
        output=owner.complete()
        if file_consumer is not None: file_consumer(tuple(owner.files))
        return output
    except BaseException as error:
        owner._failed = True
        _cleanup_owner(owner,error,'export_cleanup_owner','信号CSV导出');raise
