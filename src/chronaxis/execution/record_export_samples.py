"""只在片段信号导出需要回看时保存所选样本；每行一个值和一个实际时间。

别名、来源、单位和枚举标签留在有限声明中，行内用序号引用。
定长数据按实际时间二分，不构造原文、输入指纹或逐条来源JSON。
"""
from struct import Struct
from tempfile import TemporaryFile
from ..core.models import SourceRef
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D,QualityFlag as Q
from ..results.budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from ..results.errors import ResultClosedError
from .history import _metadata_bytes
from .record_sample import RecordSample


class RecordExportSamples:
    """拥有一个惰性定长临时文件；范围查询期间只恢复一条所需样本。"""
    def __init__(self,budget,path,definitions,session):
        """只保有限定义和文件槽。参数: 预算/私有目录/所选定义/会话。返回: owner。异常: 原构造错。"""
        self._budget,self._path=budget,path
        self._held_cost=self._fixed_cost=0
        self._file=None;self._count=0;self._last=None
        self._closed=self._failed=False
        self._definitions=self._names=self._refs=self._codes=self._labels=None
        try:
            _reserve_owned_ram(self,65536+32*_metadata_bytes(definitions),'_fixed_cost')
            self._definitions=definitions
            self._names={d.name:i for i,d in enumerate(definitions)}
            self._refs=tuple(SourceRef(session,d.source,d.field) for d in definitions)
            self._codes=tuple(Struct('>'+{D.FLOAT64:'d',D.INT64:'q',D.UINT64:'Q',D.BOOL:'q',D.ENUM:'q'}[d.dtype]) for d in definitions)
            self._labels=tuple(tuple(dict.fromkeys(label for _,label in d.choices)) if d.dtype is D.ENUM else () for d in definitions)
            self._codec=Struct('>IqQ8sI')
        except BaseException as error:
            _cleanup_owner(self,error,'record_export_samples_cleanup_owner','片段导出样本');raise

    def append(self,sample):
        """保存一次所选真实更新，保同刻原序号。参数: HistorySample。返回: None。异常: 顺序/预算/短写。"""
        if self._closed or self._failed:raise ResultClosedError('导出样本已关闭或失败')
        try:
            if self._last is not None and sample.time_ns<self._last:raise ValueError('导出样本时间回退')
            index=self._names[sample.name]
            value=sample.array_value if sample.value.valid else 0
            if self._definitions[index].dtype is D.BOOL:value=int(value)
            data=self._codec.pack(index,sample.time_ns,sample.sequence,self._codes[index].pack(value),int(sample.value.quality))
            self._budget.reserve_spool(len(data))
            if self._file is None:self._file=TemporaryFile(mode='w+b',dir=self._path,prefix='export-samples-')
            self._file.seek(0,2)
            if self._file.write(data)!=len(data):raise OSError('导出样本短写')
            self._count+=1;self._last=sample.time_ns
        except BaseException:
            self._failed=True;raise

    def _fields(self,index):
        """只按已登记位置读取一条。参数: 行号。返回: 解包字段。异常: 越界/短读。"""
        if self._closed or self._failed:raise ResultClosedError('导出样本已关闭或失败')
        if not 0<=index<self._count:raise IndexError('导出样本行号越界')
        self._file.seek(index*self._codec.size)
        payload=self._file.read(self._codec.size)
        if len(payload)!=self._codec.size:raise ValueError('导出样本短读')
        return self._codec.unpack(payload)

    def _lower(self,time_ns):
        """二分首个不早于time_ns的行。参数: 实际时间。返回: 索引。异常: 原读取错。"""
        lo,hi=0,self._count
        while lo<hi:
            mid=(lo+hi)//2
            if self._fields(mid)[1]<time_ns:lo=mid+1
            else:hi=mid
        return lo

    def rows(self,interval):
        """只回读半开片段内所选样本，不全量核验或扫描。参数: Interval。返回: 迭代器。异常: 原读取/模型错。"""
        for row in range(self._lower(interval.start_ns),self._lower(interval.end_ns)):
            index,time,sequence,payload,quality=self._fields(row)
            definition=self._definitions[index];dtype=definition.dtype
            physical=self._codes[index].unpack(payload)[0]
            if dtype is D.BOOL:physical=bool(physical)
            value=self._labels[index][physical] if dtype is D.ENUM and quality==0 else physical
            scalar=ScalarValue(value if quality==0 else None,dtype,quality==0,Q(quality),self._labels[index])
            yield RecordSample(definition.name,time,sequence,scalar,definition.unit,self._refs[index],
                physical if definition.dtype is D.ENUM else None)

    @property
    def closed(self):
        """返回实际资源状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """关闭自有临时文件并释放定义；不碰原输入。参数: 无。返回: None。异常: 原关闭错，可重试。"""
        if self._closed:return
        if self._file is not None:self._file.close();self._file=None
        self._definitions=self._names=self._refs=self._codes=self._labels=None
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost');self._closed=True
