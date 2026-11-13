"""为显式报文导出保存同次记录和新编码所需DBC上下文。

默认关闭时不创建这些对象。TextFrameStore只保存本次文本读取已交付的原帧、
物理值和定位，可为多个窗口有限回放；不重新读原文件。FrameDBCContext负责
新编码的DBC身份/字段声明，可借给新文本解码器共用一次加载。旧BLF链自身的
DBC加载和解码不改变；为新增编码另加载同一哈希的定义属于新输出的显式成本。
"""

from hashlib import file_digest
from pathlib import Path

from ..dbc_loading import load_dbc_file

from ..legacy.records import LegacyCANField
from ..legacy.binding import dbc_candidates, select_message
from ..results.budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from ..results.errors import ResultClosedError
from ..results.frame_exports import as_export_frame
from ..results.frame_patch import DBCFramePatch
from ..results.frame_rebuild import FrameSample,_sample_packet,_restore_sample
from ..results.frame_sort import FrameSort
from .history import _metadata_bytes


class FrameDBCContext:
    """拥有供新输出使用的DBC定义、摘要和额外请求字段，借用者不负责释放。"""

    def __init__(self,path,rules,budget,*,cycle_periods=False,integrity=True):
        """加载并核身份，生成连续量/选择器请求。参数: path、规则tuple、budget。返回: owner。异常: DBC/预算/字段/I/O错。
        """
        if type(integrity) is not bool: raise TypeError("integrity需要bool")
        self.path=Path(path); self.rules=rules; self._budget=budget
        self._held_cost=self._fixed_cost=0; self.closed=self._closed=False
        self.database=self._handle=self._patcher=None; self.sha256=None; self.extra_fields=();self.periods=None
        self._candidates=(); self._selected=[]; self._identities=[]; self._cycle_periods=cycle_periods
        self._by_frame_id={}; self._cycle_values={}
        try:
            size=self.path.stat().st_size
            _reserve_owned_ram(self,1048576+size*64+_metadata_bytes(rules)*32,'_fixed_cost')
            before_stat=self.path.stat()
            before=self._hash() if integrity else None
            from ..can_dependencies import import_can_dependency
            cantools = import_can_dependency('cantools')
            self.database=load_dbc_file(str(self.path), cantools)
            # 导出的未知报文策略需要判断DBC是否认识该帧；一次建索引，不逐帧扫描DBC。
            for message in self.database.messages:
                self._by_frame_id.setdefault(message.frame_id,[]).append(message)
            after_stat=self.path.stat()
            changed=(before_stat.st_size,before_stat.st_mtime_ns,before_stat.st_ino)!=(after_stat.st_size,after_stat.st_mtime_ns,after_stat.st_ino)
            if changed or integrity and self._hash()!=before:
                raise ValueError('新增编码加载DBC期间内容发生变化')
            self.sha256=before; self.version=cantools.__version__
            fields=[]; candidates=[]
            for rule in rules:
                choices=dbc_candidates(self.database,rule.frame_id,(*rule.continuous,*rule.protected),rule.is_extended,rule.is_fd)
                if not choices:
                    raise ValueError('DBC缺少重建报文或指定信号: '+str(rule.frame_id))
                candidates.append(choices)
                # 候选定义均须可重建；最终选择等实际帧到达，不按DBC顺序取第一个。
                for message in choices:
                    if cycle_periods and id(message) not in self._cycle_values:
                        # 声明DBC网格时，在打开日志前拒绝缺失或非法周期；只读取一次。
                        from ..legacy.dbc_cycles import cycle_time_ns
                        self._cycle_values[id(message)]=cycle_time_ns(message.cycle_time)
                    try:
                        self._patcher=DBCFramePatch(rule,message,budget)
                    except BaseException as error:
                        self._patcher=getattr(error,'frame_patch_cleanup_owner',None)
                        raise
                    self._patcher.close(); self._patcher=None
                    names=tuple(dict.fromkeys((*rule.continuous,*(s.name for s in message.signals if s.is_multiplexer))))
                    fields.extend(LegacyCANField(rule.channel,name,rule.frame_id,message.is_extended_frame,rule.is_fd) for name in names)
            self.extra_fields=tuple(dict.fromkeys(fields))
            self._candidates=tuple(candidates)
            self._selected=[None]*len(rules); self._identities=[None]*len(rules)
        except BaseException as error:
            _cleanup_owner(self,error,'frame_dbc_cleanup_owner','导出DBC上下文')
            raise

    def _hash(self):
        """核同一文件的完整内容身份。参数: 无。返回: SHA256文本。异常: 打开/读取/真实关闭错。
        """
        self._handle=self.path.open('rb')
        digest=file_digest(self._handle,'sha256').hexdigest()
        self._handle.close(); self._handle=None
        return digest

    def require_open(self):
        """禁止使用已释放DBC。参数: 无。返回: None。异常: ResultClosedError。
        """
        if self.closed:
            raise ResultClosedError('导出DBC上下文已关闭')

    def pairs(self):
        """交付规则与同次定义的有限借用。参数: 无。返回: tuple。异常: 已关闭或身份缺失。
        """
        self.require_open()
        pairs=[]
        for index,rule in enumerate(self.rules):
            message=self._selected[index]
            if message is None:
                choices=self._candidates[index]
                # 从未收到该报文时无需构造一个猜测的多候选输出规则。
                if len(choices)!=1:
                    continue
                message=choices[0]
            pairs.append((rule,message))
        if self._cycle_periods:
            self.periods=tuple(self._cycle_values[id(message)] for _,message in pairs)
        return tuple(pairs)

    def observe(self,frame):
        """用正在读取的实际帧确定输出定义，禁止一条自动规则混用两种身份。

        参数: frame为原始帧。返回: 匹配的DBC Message或None。异常: DBC或实际身份歧义。
        副作用: 每条规则只保存一个已识别定义和身份，不保留额外帧或扫描文件。
        """
        self.require_open()
        if frame.is_remote_frame or frame.is_error_frame:
            return None
        selected=[]
        for index,rule in enumerate(self.rules):
            if not rule.matches(frame):
                continue
            message=select_message(self._candidates[index],frame)
            if message is None:
                continue
            identity=(frame.is_extended_id,frame.is_fd)
            prior=self._identities[index]
            if prior is not None and prior!=identity:
                differing='is_extended' if prior[0]!=identity[0] else 'is_fd'
                raise ValueError('报文重建规则匹配到多种实际帧，请补充'+differing)
            self._identities[index]=identity; self._selected[index]=message
            selected.append(message)
        if len(selected)>1:
            raise ValueError('同一实际报文匹配多个重建规则，请收紧帧类型约束')
        return selected[0] if selected else None

    def is_known_frame(self,frame):
        """只判断未知报文输出策略，不要求未选报文的信号或定义唯一。

        参数: frame为原始帧。返回: bool。异常: 已关闭时ResultClosedError。
        副作用: 无，不解码或记录帧内容。
        """
        self.require_open()
        return any(message.is_extended_frame==frame.is_extended_id
            and (not frame.is_fd or message.is_fd)
            for message in self._by_frame_id.get(frame.arbitration_id,()))

    def close(self):
        """在借用者关闭后释放定义和实际句柄。参数: 无。返回: None。异常: 原关闭/释放错可恢复。
        """
        if self.closed:
            return
        if self._handle is not None:
            self._handle.close(); self._handle=None
        if self._patcher is not None:
            self._patcher.close(); self._patcher=None
        self.database=None; self.extra_fields=();self.periods=None
        self._candidates=(); self._selected=[]; self._identities=[]; self._by_frame_id={}; self._cycle_values={}
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost'); self.closed=self._closed=True


class TextFrameStore:
    """保存连续原序的同次文本CAN事实；封口后允许多个窗口逐个回放。"""

    def __init__(self,path,budget,source,session_id,read_identity,*,database_context=None,channel=None,integrity=True,trace=True):
        """建立有限排序暂存及真实读取身份。参数: 新路径、budget、源/会话/read身份，可借用重建DBC及声明通道。返回: owner。异常: I/O/预算错。
        """
        self.path=Path(path); self._budget=budget; self._held_cost=self._fixed_cost=self._row_cost=0
        self.source_name=source; self.session_id=session_id; self.read_identity=read_identity
        self.database_context=database_context; self.channel=channel; self.trace=trace
        self.sort=None; self.count=0; self.last_ns=None; self.state='building'; self.closed=self._closed=False
        try:
            _reserve_owned_ram(self,131072,'_fixed_cost')
            try:
                self.sort=FrameSort(self.path,budget,integrity=integrity)
            except BaseException as error:
                self.sort=getattr(error,'frame_sort_cleanup_owner',None)
                raise
        except BaseException as error:
            _cleanup_owner(self,error,'text_frame_store_cleanup_owner','文本原帧暂存构造')
            raise

    def append(self,record):
        """保原序原时间，不让排序掩盖回退。参数: DecodedCANRecord同次记录。返回: None。异常: 时序/状态/预算/I/O错。
        """
        if self.closed or self.state!='building' or record.sequence!=self.count:
            raise ValueError('文本原帧仓状态或连续序号不符')
        if self.last_ns is not None and record.raw.time_ns<self.last_ns:
            raise ValueError('文本原帧时间回退')
        _reserve_owned_ram(self,1048576+_metadata_bytes((record.values,record.frame_values,record.frame_layout))*32,'_row_cost')
        try:
            known=record.status!='unknown'
            if self.database_context is not None:
                self.database_context.require_open()
                frame=record.raw.frame
                # 实际类型只在同次读取中匹配，输出不使用按ID覆盖的DBC字典。
                message=self.database_context.observe(frame)
                known=frame.channel==self.channel and self.database_context.is_known_frame(frame)
            sample=FrameSample(as_export_frame(record,compact=not self.trace),record.frame_values,record.frame_layout,known)
            self.sort.append((record.sequence,),_sample_packet(sample))
            self.count+=1; self.last_ns=record.raw.time_ns
        finally:
            _release_owned_ram(self,self._row_cost,'_row_cost')

    def seal(self):
        """完整真实EOF后封口。参数: 无。返回: None。异常: 状态/配额/I/O错。
        """
        if self.closed or self.state!='building':
            raise ResultClosedError('文本原帧仓不能重复封口')
        self.sort.seal(); self.state='sealed'

    def iter_samples(self):
        """打开一个有界完整回放，提前关闭不声称完整核验。参数: 无。返回: FrameSample生成器。异常: 仓状态/篡改/I/O错。
        """
        if self.closed or self.state!='sealed':
            raise ResultClosedError('文本原帧仓不可读')
        cursor=self.sort._read(self.sort.path/f'{self.sort.level}-0.jsonl')
        try:
            for _,sequence,packet in cursor:
                sample=_restore_sample(packet)
                if sample.record.sequence!=sequence:
                    raise ValueError('文本原帧暂存序号不一致')
                yield sample
        finally:
            cursor.close()

    def iter_frames(self):
        """只交付原帧及定位，不重新解码。参数: 无。返回: ExportCANFrame生成器。异常: 原回放错。
        """
        cursor=self.iter_samples()
        try:
            for sample in cursor:
                yield sample.record
        finally:
            cursor.close()

    def close(self):
        """关闭全部真实回放FD和排序仓，保诊断文件。参数: 无。返回: None。异常: 清理错可重试。
        """
        if self.closed:
            return
        if self.sort is not None:
            self.sort.close()
        _release_owned_ram(self,self._row_cost,'_row_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost'); self.closed=self._closed=True
