"""为离线报文导出进行有界磁盘排序，不把整段报文留在内存。

输入为有限标量排序键和新导出自己的JSON记录，输出按键稳定排列的记录流。
每批最多64行，归并只开两路输入；旧run留作诊断且累计计入spool。旧调用默认用摘要绑定每行与结束标记；新版仅显式完整性诊断时启用。
不启用摘要时仍校验行结构、行长和结束计数，拒绝截断，不提供防篡改证明。
所有句柄在owner上登记，持续关闭失败仍可重试；本模块不读原日志或加载DBC。
"""

from hashlib import blake2b
from hmac import compare_digest
import json
from pathlib import Path
from secrets import token_bytes

from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .errors import ResultClosedError, ResultFormatError


class FrameSort:
    """拥有一个新目录、最多64行缓冲和三个实际文件，封口后只允许顺序回读。"""

    def __init__(self,path,budget,*,check_cancel=None,buffer_rows=64,integrity=True):
        """预约并创建暂存。参数: path新目录、budget、取消回调及批行数。返回: owner。异常: 配置/预算/I/O错。
        """
        if type(buffer_rows) is not int or not 1<=buffer_rows<=64:
            raise ValueError('报文排序缓冲需要1至64行')
        if type(integrity) is not bool: raise TypeError("integrity需要bool")
        self.integrity=integrity
        self.path=Path(path); self._budget=budget; self.check_cancel=check_cancel
        self._held_cost=self._fixed_cost=self._buffer_cost=0
        self.buffer_rows=buffer_rows; self.buffer=[]; self.handles=[]
        self._closed=False; self.state='building'; self.count=self.runs=0
        self.level=0; self.secret=None; self.cursor=None; self.pending_file=None
        try:
            # 两路解码树/编码/缓冲及句柄均有固定工作空间，实际行缓冲另计。
            _reserve_owned_ram(self,6*1048576,'_fixed_cost')
            if any(p.casefold()=='refprojects' for p in (*self.path.parts,*self.path.resolve().parts)):
                raise ValueError('报文排序不能写RefProjects')
            self.path.mkdir(parents=True,exist_ok=False); self.secret=token_bytes(32) if integrity else None
        except BaseException as error:
            _cleanup_owner(self,error,'frame_sort_cleanup_owner','报文排序构造')
            raise

    def _check(self):
        """在有界I/O间检查取消。参数: 无。返回: None。异常: 关闭或取消。
        """
        if self._closed:
            raise ResultClosedError('报文排序已关闭')
        if self.check_cancel is not None:
            self.check_cancel()

    def _open(self,path,mode):
        """登记真实句柄后交付。参数: path、模式。返回: 文件。异常: 打开或登记失败。
        """
        self.pending_file=path.open(mode,buffering=65536)
        stream=self.pending_file
        self.handles.append(stream); self.pending_file=None
        return stream

    def _close_file(self,stream):
        """关闭成功才撤销登记。参数: stream实际流。返回: None。异常: 关闭错保责任。
        """
        stream.close(); self.handles.remove(stream)

    def _mac(self,path,index,body):
        """把完整行绑定当前run及顺序。参数: path/index/body。返回: 64字节摘要。异常: 原类型错。
        """
        digest=blake2b(key=self.secret,digest_size=32)
        digest.update(path.name.encode('ascii')); digest.update(str(index).encode('ascii'))
        digest.update(b'\0'); digest.update(body)
        return digest.hexdigest().encode('ascii')

    def _write(self,stream,index,packet):
        """有界编码并实写一行。参数: stream/index/packet。返回: None。异常: 配额/超行/写入错。
        """
        self._check()
        body=json.dumps(packet,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
        if len(body)>65536:
            raise ResultFormatError('报文排序单行超过64KiB')
        payload=(self._mac(Path(stream.name),index,body)+b' ' if self.integrity else b'')+body+b'\n'
        self._budget.reserve_spool(len(payload))
        position=0
        while position<len(payload):
            written=stream.write(payload[position:])
            if type(written) is not int or not 0<written<=len(payload)-position:
                raise OSError('报文排序写入无进展')
            position+=written

    def _read(self,path):
        """逐行核完整性，必须读到合法结束记录。参数: path本次run。返回: 记录生成器。异常: 改写/截断/关闭错。
        """
        stream=self._open(path,'rb'); index=0; primary=None
        try:
            while True:
                self._check(); raw=stream.readline(65604)
                if not raw.endswith(b'\n') or len(raw)>(65602 if self.integrity else 65537) or self.integrity and raw[64:65]!=b' ':
                    raise ResultFormatError('报文排序行截断或超限')
                body=raw[65:-1] if self.integrity else raw[:-1]
                if self.integrity and not compare_digest(raw[:64],self._mac(path,index,body)):
                    raise ResultFormatError('报文排序行内容或顺序被修改')
                packet=json.loads(body)
                if type(packet) is dict:
                    if packet!={'end':index} or stream.read(1):
                        raise ResultFormatError('报文排序结束记录不一致')
                    return
                if type(packet) is not list or len(packet)!=3 or type(packet[0]) is not list:
                    raise ResultFormatError('报文排序行结构非法')
                index+=1
                yield (tuple(packet[0]),packet[1],packet[2])
        except BaseException as error:
            primary=error
            raise
        finally:
            # 校验/取消是主错误；关闭错误只能附注，真实句柄保owner供再次close。
            try:
                self._close_file(stream)
            except BaseException as cleanup:
                if primary is None:
                    raise
                primary.add_note('报文排序回读关闭待恢复: '+repr(cleanup))

    def append(self,key,packet):
        """预约后缓冲一条。参数: key有限同类型标量tuple、packet有限JSON对象。返回: None。异常: 结构/预算/I/O错。
        """
        self._check()
        if self.state!='building' or type(key) is not tuple or len(key)>32 or any(type(v) not in (int,str) for v in key):
            raise ValueError('报文排序需要building及有限标量键')
        encoded=json.dumps(packet,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
        if len(encoded)>65000:
            raise ResultFormatError('报文记录超过排序行能力')
        # JSON往返冻结调用者数据，避免追加后修改改变尚未写盘的结果。
        _reserve_owned_ram(self,4096+len(encoded)*32,'_buffer_cost')
        self.buffer.append((key,self.count,json.loads(encoded))); self.count+=1
        if len(self.buffer)>=self.buffer_rows:
            self._flush()

    def _flush(self):
        """稳定排序有限缓冲并保存一个run。参数: 无。返回: None。异常: 排序/I/O/配额错。
        """
        if not self.buffer:
            return
        self.buffer.sort(key=lambda item:(item[0],item[1]))
        stream=self._open(self.path/f'0-{self.runs}.jsonl','xb')
        for index,packet in enumerate(self.buffer):
            self._write(stream,index,packet)
        self._write(stream,len(self.buffer),{'end':len(self.buffer)})
        self._close_file(stream); self.runs+=1; self.buffer.clear()
        _release_owned_ram(self,self._buffer_cost,'_buffer_cost')

    def _merge(self,left,right,target):
        """只保两路当前行进行稳定归并。参数: 两个run及新目标。返回: None。异常: 输入校验/写入/关闭错。
        """
        first=self._read(left); second=self._read(right) if right is not None else iter(())
        stream=self._open(target,'xb'); count=0; primary=None
        try:
            a=next(first,None); b=next(second,None)
            while a is not None or b is not None:
                choose_first=b is None or a is not None and (a[0],a[1])<=(b[0],b[1])
                row=a if choose_first else b
                self._write(stream,count,row); count+=1
                if choose_first:
                    a=next(first,None)
                else:
                    b=next(second,None)
            self._write(stream,count,{'end':count}); self._close_file(stream)
        except BaseException as error:
            primary=error
            raise
        finally:
            cleanup_error=None
            for reader in (first,second):
                close=getattr(reader,'close',None)
                if close is not None:
                    try:
                        close()
                    except BaseException as cleanup:
                        cleanup_error=cleanup_error or cleanup
            if cleanup_error is not None:
                if primary is None:
                    raise cleanup_error
                primary.add_note('报文归并游标关闭待恢复: '+repr(cleanup_error))

    def seal(self):
        """完成所有有界归并，空输入也有完整结束记录。参数: 无。返回: None。异常: 输入/预算/取消/I/O错。
        """
        self._check()
        if self.state!='building':
            raise ResultClosedError('报文排序不能重复封口')
        self._flush()
        if not self.runs:
            stream=self._open(self.path/'0-0.jsonl','xb')
            self._write(stream,0,{'end':0}); self._close_file(stream); self.runs=1
        while self.runs>1:
            for index in range(0,self.runs,2):
                self._merge(self.path/f'{self.level}-{index}.jsonl',
                    self.path/f'{self.level}-{index+1}.jsonl' if index+1<self.runs else None,
                    self.path/f'{self.level+1}-{index//2}.jsonl')
            self.level+=1; self.runs=(self.runs+1)//2
        self.state='sealed'

    def rows(self):
        """交付单一可关闭回读游标。参数: 无。返回: (key,序号,记录)生成器。异常: 非sealed或已有游标。
        """
        self._check()
        if self.state!='sealed' or self.cursor is not None:
            raise ResultClosedError('报文排序未封口或已交付游标')
        self.cursor=self._read(self.path/f'{self.level}-0.jsonl')
        return self.cursor

    def close(self):
        """关闭全部实际文件后释放自有预算；保暂存供诊断。参数: 无。返回: None。异常: 原关闭/释放错可重试。
        """
        if self._closed:
            return
        if self.cursor is not None:
            self.cursor.close(); self.cursor=None
        if self.pending_file is not None:
            self.pending_file.close(); self.pending_file=None
        while self.handles:
            self._close_file(self.handles[-1])
        self.buffer.clear(); self.secret=None
        _release_owned_ram(self,self._buffer_cost,'_buffer_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost'); self._closed=True
