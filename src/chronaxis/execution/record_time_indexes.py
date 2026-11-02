"""只为周期选窗/事件时长保存一份所需驱动时刻，按索引定位。

每条只写一个实际整数时间；偏移只在单次查询中按记录索引计算，不保存改写时间轴。
"""
from fractions import Fraction
from struct import Struct
from tempfile import TemporaryFile
from ..results.errors import ResultClosedError
from ..results.spool import _reserve_owned_ram,_release_owned_ram,_cleanup_owner


class RecordTimeIndexes:
    """拥有各必要驱动的一份定长时间文件，所有消费者借用。"""

    def __init__(self,budget,path,drivers):
        """预付有限索引状态。参数: 预算/私有路径/唯一驱动名称。返回: owner。异常: 原构造错。"""
        self._budget,self._path=budget,path
        self._files={}
        self._counts={}
        self._last={}
        self._held_cost=self._fixed_cost=0
        self._closed=False
        self._codec=Struct('>q')
        try:
            _reserve_owned_ram(self,65536+len(drivers)*32768,'_fixed_cost')
            self._counts=dict.fromkeys(drivers,0)
            self._last=dict.fromkeys(drivers)
        except BaseException as error:
            _cleanup_owner(self,error,'record_time_indexes_cleanup_owner','必要驱动索引构造')
            raise

    def observe_group(self,group):
        """每驱动每实际同刻组只写一次。参数: 完整组。返回: None。异常: 顺序/IO/预算错误。"""
        if self._closed:
            raise ResultClosedError('驱动索引已关闭')
        names={sample.name for sample in group.samples}
        for driver in self._counts:
            if driver not in names:
                continue
            if self._last[driver] is not None and group.time_ns<=self._last[driver]:
                raise ValueError('驱动索引时间回退或重复')
            if driver not in self._files:
                self._files[driver]=TemporaryFile(mode='w+b',dir=self._path,prefix='driver-times-')
            self._budget.reserve_spool(8)
            handle=self._files[driver]
            handle.seek(0,2)
            if handle.write(self._codec.pack(group.time_ns))!=8:
                raise OSError('驱动索引短写')
            self._counts[driver]+=1
            self._last[driver]=group.time_ns

    def count(self,driver):
        """读取已写条数。参数: 驱动。返回: int。异常: 未声明驱动。"""
        return self._counts[driver]

    def last(self,driver):
        """读取已写末时刻。参数: 驱动。返回: int或None。异常: 未声明驱动。"""
        return self._last[driver]

    def at(self,driver,index):
        """只读取一个时间整数。参数: 驱动/索引。返回: int。异常: 越界/短读。"""
        if self._closed:
            raise ResultClosedError('驱动索引已关闭')
        if not 0<=index<self._counts[driver]:
            raise IndexError('驱动索引越界')
        handle=self._files[driver]
        handle.seek(index*8)
        data=handle.read(8)
        if len(data)!=8:
            raise ValueError('驱动索引短读')
        return self._codec.unpack(data)[0]

    def lower(self,driver,time_ns):
        """二分首个不早于time_ns的时刻。参数: 驱动/实际时间。返回: 索引。异常: 原读取错。"""
        lo,hi=0,self._counts[driver]
        while lo<hi:
            mid=(lo+hi)//2
            if self.at(driver,mid)<time_ns:
                lo=mid+1
            else:
                hi=mid
        return lo

    def position(self,driver,time_ns):
        """单次查询实际时刻位于哪对记录及其比例，不保存转换时间轴。

        参数: 驱动/实际时间。返回: (Fraction记录位置,是否超出观测)。异常: 空索引或读取错。
        """
        if not self.count(driver):
            raise ValueError('记录位置需要真实驱动')
        count=self.count(driver)
        right=self.lower(driver,time_ns)
        if right==count:
            position=Fraction(count-1)
            outside=time_ns>self.at(driver,count-1)
        elif self.at(driver,right)==time_ns:
            position=Fraction(right)
            outside=False
        elif right==0:
            position=Fraction(0)
            outside=True
        else:
            left_time,right_time=self.at(driver,right-1),self.at(driver,right)
            position=Fraction(right-1)+Fraction(time_ns-left_time,right_time-left_time)
            outside=False
        return position,outside

    def shift(self,driver,time_ns,offset_ns,step_ns):
        """按所选周期偏移记录位置，返回实际时刻及首尾裁剪标识。

        参数: 驱动、实际锚点、带符号偏移ns、正周期ns。返回: (实际ns,是否裁剪)。
        非整周期按原实际间隔比例定位，最终纳秒沿既有最近偶数舍入；不补观测之外的记录。
        异常: 空索引/非法周期/实际读取错。
        """
        if step_ns<=0 or not self.count(driver):
            raise ValueError('周期选窗需要正周期及真实驱动记录')
        count=self.count(driver)
        position,outside=self.position(driver,time_ns)
        target=position+Fraction(offset_ns,step_ns)
        if target<0:
            return self.at(driver,0),True
        if target>count-1:
            return self.at(driver,count-1),True
        left=target.numerator//target.denominator
        if target==left:
            return self.at(driver,left),outside
        a,b=self.at(driver,left),self.at(driver,left+1)
        return round(Fraction(a)+(target-left)*(b-a)),outside

    @property
    def closed(self):
        """返回关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    def close(self):
        """只关闭本次必要文件，失败可重试。参数: 无。返回: None。异常: 原关闭错。"""
        if self._closed:
            return
        for driver in tuple(self._files):
            self._files[driver].close()
            del self._files[driver]
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
