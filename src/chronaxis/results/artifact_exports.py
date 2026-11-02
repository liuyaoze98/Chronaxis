"""拥有本次新增导出目录及有界索引，发布时只复制并核对实际文件。

每个导出至多16个普通文件；片段数量增长只增加磁盘索引，不积累路径列表。
仅请求完整性诊断时保存摘要；复制沿必要读取计算，普通运行核文件身份与大小。
"""

from pathlib import Path
import os
import stat
from hashlib import sha256
import json
from .frame_sort import FrameSort
from .budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from .errors import ResultClosedError,ResultFormatError
from .raw_exports import _write_all


class ArtifactExportStore:
    """保存一次会话的信号/报文导出及独立清单，不借用原数据reader。"""

    def __init__(self,budget,path,session_id,device_label,*,integrity=True):
        """创建独占目录及索引。参数: 预算/path/会话/设备。返回: owner。异常: 配置/IO/预算错。
        """
        if type(integrity) is not bool: raise TypeError('integrity必须为bool')
        self._integrity=integrity; self.index_info=None
        self._budget=budget; self.path=Path(path); self.session_id=session_id; self.device_label=device_label
        self._held_cost=self._fixed_cost=0; self._sort=None; self._input=self._output=self._index=self._cursor=None
        self.count=0; self.state='building'; self._closed=False
        try:
            if device_label not in ('home','work') or any(p.casefold()=='refprojects' for p in self.path.resolve().parts):
                raise ValueError('新导出需要实际设备标签及新工作目录')
            _reserve_owned_ram(self,524288,'_fixed_cost')
            self.path.mkdir(parents=True,exist_ok=False)
            try:
                self._sort=FrameSort(self.path/'inventory',budget,integrity=integrity)
            except BaseException as error:
                self._sort=getattr(error,'frame_sort_cleanup_owner',None); raise
        except BaseException as error:
            _cleanup_owner(self,error,'artifact_export_store_cleanup_owner','导出索引构造'); raise

    @property
    def closed(self):
        """读取真实关闭状态。参数: 无。返回: bool。异常: 无。
        """
        return self._closed

    @property
    def owned_ram(self):
        """汇总本仓及索引实际费用供父层核账。参数: 无。返回: bytes。异常: 无。
        """
        return self._held_cost+(0 if self._sort is None else self._sort._held_cost)

    def next_path(self):
        """提供当前导出独占子目录。参数: 无。返回: Path。异常: 非building。
        """
        if self._closed or self.state!='building':
            raise ResultClosedError('导出索引不能新增')
        return self.path/f'export-{self.count:08d}'

    def _close_slot(self,slot):
        """真实close成功后撤槽。参数: slot责任名。返回: None。异常: 原close错，保槽重试。
        """
        owner=getattr(self,slot)
        if owner is not None:
            owner.close(); setattr(self,slot,None)

    @staticmethod
    def _identity(path):
        """取得普通文件的替换/修改标识。参数: Path。返回: 四整数tuple。异常: 链接/非普通文件/IO。"""
        info=path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise ResultFormatError('导出内容必须为普通文件')
        return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)

    def _file(self,path,destination=None,expected=None,identity=None):
        """必要复制时才读内容；请求摘要则在同次读取计算。参数: 路径/目标/大小摘要/身份。返回: 大小和可选摘要。"""
        if self._input is not None or self._output is not None:
            raise ResultClosedError('导出文件还有未清理句柄')
        before=self._identity(path)
        # 摘要模式会核实际内容，允许修复为原字节后重试；普通模式没有内容依据，仍拒身份变化。
        if identity is not None and tuple(identity)!=before and not self._integrity:
            raise ResultFormatError('导出文件已被替换或修改')
        if expected is not None and before[2]!=expected[0]:
            raise ResultFormatError('导出文件大小与登记不同')
        if destination is None and not self._integrity:
            return before[2],None
        self._input=path.open('rb',buffering=0)
        opened=os.fstat(self._input.fileno())
        if (opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns)!=before:
            raise ResultFormatError('导出文件在打开时变化')
        if destination is not None:
            self._output=destination.open('xb',buffering=0)
        digest=sha256() if self._integrity else None; count=0
        while True:
            block=self._input.read(65536)
            if not block: break
            count+=len(block)
            if count>before[2]: raise ResultFormatError('导出文件超过登记大小')
            if digest is not None: digest.update(block)
            if self._output is not None:
                self._budget.reserve_spool(len(block)); _write_all(self._output,block)
        value=None if digest is None else digest.hexdigest()
        if count!=before[2] or self._identity(path)!=before:
            raise ResultFormatError('导出文件在读取时变化')
        if expected is not None and expected[1] is not None and value!=expected[1]:
            raise ResultFormatError('导出文件内容与登记摘要不同')
        self._close_slot('_output'); self._close_slot('_input')
        # 写成功和真实close已确认；不再把新目标整份回读一次。
        return count,value

    def append(self,export_type,scope,interval,*,segment_id=None,completed_files=None):
        """登记刚生成目录中有限文件的实际身份。参数: 类型/范围/区间/片段ID。返回: None。异常: 文件/索引错。
        """
        path=self.next_path(); files=[]
        # 内部writer交出的有限事实避免登记时再次扫描；旧调用未交事实则按原开关读取。
        supplied=None if completed_files is None else {item['name']:item for item in completed_files}
        if supplied is not None and len(supplied)>16: raise ValueError('导出文件事实超过上限')
        try:
            if export_type not in ('signal_csv','can_frames') or scope not in ('session','segments'):
                raise ValueError('导出种类或范围错误')
            for entry in path.iterdir():
                if len(files)>=16 or not entry.is_file() or entry.is_symlink() or not entry.name.isascii():
                    raise ValueError('导出目录只允许至多16个普通文件')
                identity=self._identity(entry)
                if supplied is None:
                    size,digest=self._file(entry,identity=identity)
                else:
                    fact=supplied.pop(entry.name,None)
                    if fact is None or fact['bytes']!=identity[2]:
                        raise ResultFormatError('导出文件与writer事实不符')
                    size,digest=fact['bytes'],fact.get('sha256') if self._integrity else None
                    if self._integrity and (type(digest) is not str or len(digest)!=64):
                        raise ResultFormatError('请求摘要但writer没有提供')
                files.append(dict(name=entry.name,bytes=size,_identity=identity,
                    **({} if digest is None else {'sha256':digest})))
            if supplied: raise ResultFormatError('writer登记的文件缺失')
            if not any(f['name']=='manifest.json' for f in files):
                raise ValueError('导出缺完成清单')
            self._sort.append((self.count,),dict(index=self.count,export_type=export_type,scope=scope,segment_id=segment_id,
                interval=None if interval is None else [interval.start_ns,interval.end_ns],
                directory=path.name,files=sorted(files,key=lambda f:f['name']),device_label=self.device_label))
            self.count+=1
        except BaseException as error:
            self.state='failed'; error.artifact_export_store_cleanup_owner=self; raise

    def seal(self):
        """封口目录索引后才允许移交。参数: 无。返回: None。异常: 状态/排序IO错。
        """
        self.next_path(); self._sort.seal(); self.state='sealed'

    def copy_to(self,destination):
        """逐目录复制到新发布位置，按请求在同次读取核摘要。参数: 新结果根。返回: exports.jsonl路径。异常: IO/完整性错。
        """
        if self._closed or self.state!='sealed' or self._cursor is not None or self._index is not None:
            raise ResultClosedError('导出索引未封口或有发布资源待恢复')
        root=Path(destination)/'exports'; root.mkdir(exist_ok=False)
        index=Path(destination)/'exports.jsonl'
        index_digest=sha256() if self._integrity else None; index_bytes=0
        self.index_info=None
        try:
            self._index=index.open('xb',buffering=0)
            self._cursor=self._sort._read(self._sort.path/f'{self._sort.level}-0.jsonl')
            count=0
            for key,sequence,record in self._cursor:
                if key!=[count] and key!=(count,):
                    raise ResultFormatError('导出索引序号不连续')
                if record['directory']!=f'export-{count:08d}':
                    raise ResultFormatError('导出索引目录错误')
                target=root/record['directory']; target.mkdir(exist_ok=False)
                for entry in record['files']:
                    name=entry['name']
                    if Path(name).name!=name or '/' in name or '\\' in name or ':' in name:
                        raise ResultFormatError('导出索引包含不安全文件名')
                    self._file(self.path/record['directory']/name,target/name,
                        (entry['bytes'],entry.get('sha256')),entry['_identity'])
                    # 修改标识仅用于当前文件生命周期，不逐文件发布另一套证明。
                    del entry['_identity']
                payload=(json.dumps(record,ensure_ascii=False,allow_nan=False,sort_keys=True)+'\n').encode('utf-8')
                self._budget.reserve_spool(len(payload)); _write_all(self._index,payload); count+=1
                if index_digest is not None: index_digest.update(payload)
                index_bytes+=len(payload)
            if count!=self.count:
                raise ResultFormatError('导出索引数量不符')
            self._close_slot('_cursor'); self._close_slot('_index')
            self.index_info=dict(name=index.name,bytes=index_bytes,
                **({} if index_digest is None else {'sha256':index_digest.hexdigest()}))
            return index
        except BaseException as error:
            error.artifact_export_store_cleanup_owner=self
            try:
                self.recover_copy()
            except BaseException as cleanup:
                error.add_note('导出复制清理失败: '+type(cleanup).__name__)
            raise

    def recover_copy(self):
        """关闭失败发布句柄，可重新发布到另一新目录。参数: 无。返回: None。异常: 实际close错可重试。
        """
        for slot in ('_output','_input','_cursor','_index'):
            self._close_slot(slot)
        # 生成器已退出而真实close持续失败时，句柄仍登记在索引仓，重试必须处理它们。
        if self._sort is not None:
            while self._sort.handles:
                self._sort._close_file(self._sort.handles[-1])

    def close(self):
        """真实关闭索引及IO后释放自己的费用，保留磁盘。参数: 无。返回: None。异常: 原close错。
        """
        if self._closed:
            return
        self.recover_copy(); self._close_slot('_sort')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost'); self._closed=True
