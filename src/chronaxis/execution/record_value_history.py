"""只为需要回看范围的消费者保存计算值，一份实际时间和必要有效截止。

同一表达式/条件/驱动可共享此文件。最后一点留在内存，便于非驱动失效更新
它的截止；其余记录定长保存，可二分定位而无需全量核验或JSON重建。
"""
from struct import Struct
from tempfile import TemporaryFile
from ..core.numeric import ScalarValue
from ..core.types import SignalDType as D,QualityFlag as Q
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram,_release_owned_ram,_cleanup_owner


class RecordValueHistory:
    """拥有单个必要临时文件和最后一个计算点；没有原帧、原文或第二时间轴。"""

    def __init__(self,budget,path,dtype,conditioned=False,*,sample_updates=False,labels=()):
        """预付有限读写状态，不立即建文件。

        参数: 预算/专用路径/值类型/条件开关；sample_updates按需存真实更新标志，labels共享枚举域。
        返回: owner。异常: 原构造错。
        """
        self._budget,self._path,self._dtype,self._conditioned=budget,path,dtype,conditioned
        self._sample_updates,self._labels=sample_updates,labels
        self._held_cost=self._fixed_cost=0
        self._file=self._last=None
        self._count=0
        self._closed=self._failed=False
        try:
            _reserve_owned_ram(self,65536,'_fixed_cost')
            if type(sample_updates) is not bool:raise TypeError('样本标志开关需要bool')
            if dtype is D.ENUM:
                if type(labels) is not tuple or not labels:raise ValueError('枚举历史需要共享标签域')
                _reserve_owned_ram(self,4096+sum(1024+64*len(label) for label in labels),'_fixed_cost')
            code={D.FLOAT64:'d',D.INT64:'q',D.UINT64:'Q',D.BOOL:'?',D.ENUM:'I'}[dtype]
            self._codec=Struct('>q'+code+'?Iq?'+('??Iq?' if conditioned else '')+('?' if sample_updates else ''))
        except BaseException as error:
            _cleanup_owner(self,error,'record_value_history_cleanup_owner','必要计算历史构造')
            raise

    @property
    def count(self):
        """含内存末点的记录数。参数: 无。返回: int。异常: 无。"""
        return self._count+(self._last is not None)

    @property
    def last_time(self):
        """最后真实驱动时刻。参数: 无。返回: int或None。异常: 无。"""
        return None if self._last is None else self._last[0]

    def _open(self):
        """拒绝失败/关闭后使用。参数: 无。返回: None。异常: ResultClosedError。"""
        if self._closed or self._failed:
            raise ResultClosedError('必要计算历史已关闭或失败')

    def append(self,row,condition=None,*,actual_update=False):
        """写前一点并留下新点；输入是本执行器已验证的求值结果。

        参数: row(time,ScalarValue,deadline)，condition为同样三元组或None；actual_update标识真实值更新。
        返回: None。异常: 顺序/短写/预算错误，失败后只能清理。
        """
        self._open()
        try:
            if type(actual_update) is not bool:raise TypeError('真实更新标志需要bool')
            time,value,deadline=row
            if self._last is not None and time<=self._last[0]:
                raise ValueError('必要计算历史时间须递增')
            if self._last is not None:
                if self._file is None:
                    self._file=TemporaryFile(mode='w+b',dir=self._path,prefix='calculation-values-')
                t,v,d,c,cd=self._last[:5]
                number=self._labels.index(v.value) if self._dtype is D.ENUM and v.valid else v.value if v.valid else 0
                # 本执行私有暂存中的高位携带部分状态，永不混入 ScalarValue 的有效性质量。
                fields=(t,number,v.valid,int(v.quality) | (int(v.partial)<<31),d or 0,d is not None)
                if self._conditioned:
                    fields+=(bool(c.value) if c.valid else False,c.valid,int(c.quality) | (int(c.partial)<<31),cd or 0,cd is not None)
                if self._sample_updates:fields+=(self._last[5],)
                payload=self._codec.pack(*fields)
                self._budget.reserve_spool(len(payload))
                self._file.seek(0,2)
                if self._file.write(payload)!=len(payload):
                    raise OSError('必要计算历史短写')
                self._count+=1
            self._last=(time,value,deadline,None if condition is None else condition[1],
                        None if condition is None else condition[2])+((actual_update,) if self._sample_updates else ())
        except BaseException:
            self._failed=True
            raise

    def expire_at(self,time_ns,*,condition=False):
        """非驱动失效只裁最后点，不添加假记录。参数: 实际截止/条件标识。返回: None。异常: 时间回退。"""
        self._open()
        if self._last is None:
            return
        if time_ns<self._last[0]:
            raise ValueError('必要计算历史截止回退')
        index=4 if condition else 2
        old=self._last[index]
        self._last=self._last[:index]+(time_ns if old is None else min(old,time_ns),)+self._last[index+1:]

    def at(self,index):
        """读取一个实际记录，不全量扫描。参数: 已登记索引。返回: 点及条件五元组。异常: 越界/短读。"""
        self._open()
        if not 0<=index<self.count:
            raise IndexError('必要计算历史索引越界')
        if index==self._count:
            return self._last
        self._file.seek(index*self._codec.size)
        payload=self._file.read(self._codec.size)
        if len(payload)!=self._codec.size:
            raise ValueError('必要计算历史短读')
        fields=self._codec.unpack(payload)
        t,v,valid,quality,deadline,has_deadline=fields[:6]
        value=ScalarValue((self._labels[v] if self._dtype is D.ENUM else v) if valid else None,
                         self._dtype,valid,Q(quality & 0x7fffffff),self._labels,partial=bool(quality>>31))
        selected=selected_deadline=None
        if self._conditioned:
            c,valid,quality,selected_deadline,has_end=fields[6:11]
            selected=ScalarValue(c if valid else None,D.BOOL,valid,Q(quality & 0x7fffffff),partial=bool(quality>>31))
            if not has_end:
                selected_deadline=None
        return (t,value,deadline if has_deadline else None,selected,selected_deadline)+((fields[-1],) if self._sample_updates else ())

    def lower(self,time_ns):
        """二分首个不早于time_ns的索引。参数: 实际时间。返回: int。异常: 原读取错。"""
        lo,hi=0,self.count
        while lo<hi:
            mid=(lo+hi)//2
            if self.at(mid)[0]<time_ns:
                lo=mid+1
            else:
                hi=mid
        return lo

    def rows(self,start_ns,end_ns):
        """只借出范围两侧及其中的记录，保留裁剪分母。参数: 实际起止。返回: 迭代器。异常: 原读取错。"""
        self._open()
        if not self.count:
            return
        first=self.lower(start_ns)
        if first==self.count or first>0 and self.at(first)[0]>start_ns:
            first-=1
        last=min(self.count-1,self.lower(end_ns))
        for index in range(first,last+1):
            yield self.at(index)

    @property
    def closed(self):
        """返回自有资源关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """关闭必要文件并退款，不碰原输入。参数: 无。返回: None。异常: 原关闭错，可重试。"""
        if self._closed:
            return
        if self._file is not None:
            self._file.close()
            self._file=None
        self._last=None
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
