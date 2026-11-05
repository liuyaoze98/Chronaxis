"""用有限缓冲写新导出目录，全部文件真正关闭后才独占发布。

供信号CSV及新报文导出共用：输入是已编码的有限bytes，输出为按模式返回的目录或实际路径清单。
临时文件保留供排查；失败不覆盖用户目录、不删除已有数据。累计spool先预约，
RAM按自有槽释放；关闭失败保真实句柄供重试。沿用项目已验证的Windows rename
语义，其他平台预先拒绝。此层不读取原始日志、不解码，也不计算插值。
"""

from hashlib import sha256
import json
from pathlib import Path
import platform
from uuid import uuid4

from .budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .errors import ResultClosedError, ResultFormatError


class ExportFiles:
    """拥有当前/挂起的有限输出文件、消费游标及可选处理owner，最多16文件。"""

    def __init__(self, destination, budget, *, integrity=True, timestamped=False):
        """预检输出并创建独占临时目录。参数: destination输出根、budget共享账本，integrity控制摘要，timestamped为内部选择的公开时间命名模式。

        返回: owner。异常: 路径/平台/预算/I/O错；清理失败附export_cleanup_owner。
        """
        if not isinstance(destination,(str,Path)) or not isinstance(budget,ResourceBudget):
            raise TypeError('导出需要目录路径和ResourceBudget')
        if type(integrity) is not bool:
            raise TypeError('integrity必须为bool')
        self._integrity=integrity
        self._timestamped = timestamped
        self._failed = False
        self._temporary_identity = None
        self.destination = Path(destination).absolute()
        # 检查词法及解析路径，防止通过链接写回历史项目；已有目标不复用。
        if any(p.casefold()=='refprojects' for p in (*self.destination.parts,*self.destination.resolve().parts)):
            raise ValueError('导出不能位于RefProjects')
        if platform.system()!='Windows':
            raise NotImplementedError('导出原子安装目前只验证Windows')
        try:
            self.destination.lstat()
        except FileNotFoundError:
            pass
        else:
            if not timestamped or not self.destination.is_dir() or self.destination.is_symlink():
                raise FileExistsError(self.destination)
        self._budget = budget
        self._held_cost = self._fixed_cost = self._row_cost = 0
        self._closed = False
        self.reader = self.worker = self.stream = self.verifier = self.temporary = None
        self._parked = {}
        self._name = self._hash = None
        self._bytes = 0
        self.files = []
        try:
            _reserve_owned_ram(self,131072+len(str(self.destination).encode('utf-8'))*32,'_fixed_cost')
            self.destination.parent.mkdir(parents=True,exist_ok=True)
            self.temporary = self.destination.parent/('.'+self.destination.name+'.'+uuid4().hex+'.incomplete')
            self.temporary.mkdir(exist_ok=False)
            from .owned_directory import directory_identity
            self._temporary_identity = directory_identity(self.temporary)
        except BaseException as error:
            self._failed = True
            _cleanup_owner(self,error,'export_cleanup_owner','导出目录构造')
            raise

    @property
    def closed(self):
        """返回真实关闭状态。参数: 无。返回: bool。异常: 无。
        """
        return self._closed

    def open_file(self, name):
        """打开一个固定平面文件。参数: name安全文件名。返回: None。异常: 未关闭/重复/非法名/I/O错。
        """
        if self._closed or self.stream is not None:
            raise ResultClosedError('导出已关闭或前一文件未关闭')
        if (type(name) is not str or not name or len(name)>128 or Path(name).name!=name
                or any(c in name for c in '/\\:') or name in ('.','..') or len(self.files)+len(self._parked)>=16):
            raise ValueError('导出文件名或数量非法')
        if name in self._parked or any(item['name']==name for item in self.files):
            raise ValueError('导出文件重复')
        # 多张表共用同次输入时会同时存在缓冲；每个新文件单独预约，不各自借满总预算。
        _reserve_owned_ram(self,131072,'_fixed_cost')
        self.stream = (self.temporary/name).open('xb',buffering=65536)
        self._name,self._hash,self._bytes = name,sha256() if self._integrity else None,0

    def select_file(self, name):
        """切换有限输出表，不重新打开或覆盖。参数: name已开或新固定文件名。返回: None。异常: 打开/状态错。
        """
        if self._closed:
            raise ResultClosedError('导出已关闭')
        if self._name == name:
            return
        if self.stream is not None:
            self._parked[self._name] = (self.stream,self._hash,self._bytes)
            self.stream = self._name = self._hash = None
        if name in self._parked:
            self.stream,self._hash,self._bytes = self._parked.pop(name)
            self._name = name
        else:
            self.open_file(name)

    def append(self, payload):
        """有限块实际写入并更新摘要。参数: payload最多64KiB bytes。返回: None。异常: 配额/写入/结构错。
        """
        if self._closed or self.stream is None:
            raise ResultClosedError('导出文件未打开')
        if type(payload) is not bytes or len(payload)>65536:
            raise ResultFormatError('导出块需要至多64KiB bytes')
        # 配额在任何写动作之前预约，短写继续；零进展不能伪装成功。
        self._budget.reserve_spool(len(payload))
        position = 0
        while position < len(payload):
            written = self.stream.write(payload[position:])
            if type(written) is not int or not 0 < written <= len(payload)-position:
                raise OSError('导出写入没有合法进展')
            position += written
        if self._hash is not None: self._hash.update(payload)
        self._bytes += len(payload)

    def close_file(self):
        """真实关闭后登记摘要。参数: 无。返回: None。异常: 关闭失败保留句柄供重试。
        """
        if self.stream is None:
            return
        self.stream.close()
        self.stream = None
        self.files.append(dict(name=self._name,bytes=self._bytes,
            **({} if self._hash is None else {'sha256':self._hash.hexdigest()})))
        self._name = self._hash = None

    def close_reader(self):
        """关闭已接管的输入游标。参数: 无。返回: None。异常: 原关闭错误，保留游标供重试。
        """
        if self.reader is not None:
            close = getattr(self.reader,'close',None)
            if close is not None:
                close()
            self.reader = None

    def close_files(self):
        """关闭当前及挂起文件。参数: 无。返回: None。异常: 原关闭错误，未关的仍在owner中。
        """
        self.close_file()
        while self._parked:
            name = next(iter(self._parked))
            self.select_file(name)
            self.close_file()

    def register_external(self,name):
        """登记同目录内已关闭的外部writer文件。参数: name固定文件名。返回: None。异常: 名称/读取/关闭错。

        外部writer已付spool，本层仅有限回读计算摘要，不再次计算磁盘费用。
        """
        if (self._closed or self.verifier is not None or type(name) is not str or not name or len(name)>128 or Path(name).name!=name
                or any(c in name for c in '/\\:') or name in ('.','..')
                or len(self.files)+len(self._parked)+(self.stream is not None)>=16
                or name==self._name or name in self._parked or any(f['name']==name for f in self.files)):
            raise ValueError('外部导出文件名称或状态非法')
        # 未请求完整性诊断时，只登记外部writer已关闭文件的实际大小，不为摘要回读。
        if not self._integrity:
            self.files.append({'name':name,'bytes':(self.temporary/name).stat().st_size})
            return
        self.verifier=(self.temporary/name).open('rb')
        digest=sha256(); size=0
        while True:
            chunk=self.verifier.read(65536)
            if not chunk:
                break
            digest.update(chunk); size+=len(chunk)
        self.verifier.close()
        self.verifier=None
        self.files.append({'name':name,'sha256':digest.hexdigest(),'bytes':size})

    def finish(self, metadata):
        """写完成清单并原子安装目录。参数: metadata有界JSON事实。返回: 内部目录Path或公开ExportManifest。

        异常: 序列化/配额/关闭/竞态目标错误；失败保.incomplete目录，不冒报发布成功。
        """
        from ..execution.history import _metadata_bytes
        # 输入完整消费并真实关闭、数据文件关闭后才写完成清单。
        self.close_reader()
        if self.worker is not None:
            self.worker.close()
            self.worker = None
        if self.verifier is not None:
            self.verifier.close()
            self.verifier=None
        self.close_files()
        publication = None
        result = None
        try:
            # 内部导出仍使用新目录；公开调用在已有根下使用同次时间文件名。
            if self._timestamped:
                from .publication import PublicationNames
                publication = PublicationNames(self.destination, (*[f['name'] for f in self.files], 'manifest.json'))
                metadata = dict(metadata)
                if 'exact_source_index' in metadata:
                    metadata['exact_source_index'] = publication.names[metadata['exact_source_index']]
            _reserve_owned_ram(self,65536+_metadata_bytes(metadata)*16,'_row_cost')
            try:
                files = tuple(dict(f, name=publication.names[f['name']]) if publication else dict(f) for f in self.files)
                document = dict(metadata,export_version=1,status='completed',files=files)
                payload = (json.dumps(document,ensure_ascii=False,allow_nan=False,sort_keys=True)+'\n').encode('utf-8')
                self.open_file('manifest.json')
                # 清单受声明规模和RAM预算约束，按有限块写出。
                for start in range(0,len(payload),65536):
                    self.append(payload[start:start+65536])
                self.close_file()
            finally:
                _release_owned_ram(self,self._row_cost,'_row_cost')
            self.close()
            if publication is None:
                self.temporary.rename(self.destination)
                return self.destination
            from .manifest import ExportManifest
            result = ExportManifest(self.destination, self.destination/publication.names['manifest.json'],
                                    tuple(self.destination/f['name'] for f in files))
            publication.publish(self.temporary, 'manifest.json')
            self.temporary.rmdir()
            return result
        except BaseException as error:
            if publication is not None and publication.completed:
                error.completed_manifest = result
            if publication is not None:
                try:
                    publication.close()
                except BaseException as cleanup:
                    error.add_note('导出命名锁释放失败：' + str(cleanup))
            raise

    def close(self):
        """只关闭自有资源，保留诊断文件。参数: 无。返回: None。异常: 原关闭/释放错，允许重试。
        """
        if self._closed:
            try:
                self._cleanup_failed_output()
            except BaseException:
                self._closed = False
                raise
            return
        self.close_reader()
        if self.worker is not None:
            self.worker.close()
            self.worker = None
        if self.verifier is not None:
            self.verifier.close()
            self.verifier=None
        self.close_files()
        _release_owned_ram(self,self._row_cost,'_row_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._cleanup_failed_output()
        self._closed = True

    def _cleanup_failed_output(self):
        """公开导出失败时清理本次临时目录。参数: 无。返回: None。异常: 身份或IO错误，可重试close。"""
        if self._failed and self._timestamped and self.temporary is not None:
            from .owned_directory import remove_owned_directory
            remove_owned_directory(self.temporary, self._temporary_identity)
