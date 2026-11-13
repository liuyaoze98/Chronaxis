"""内部有限控制消息；Connection 只收发 bytes，不使用隐含 pickle。

CCP1 的固定头为版本、通道、命令和 uint64 总字节数，主体分片不超过 64KiB。
普通CAN/fast由已有工作预算限定；独立batch沿用无全批RAM硬上限的边界。
任务与固定结果逐片接收，不按声明总长预分配，也不截断合法身份。
"""
import json
from math import isfinite
import struct

from ._control_models import pack_message, restore_message, native, check_message_fields

CHUNK = 65536
_HEADER = struct.Struct('!4sBBQ')
_FAMILIES = {'can':1, 'fast':2, 'batch':3}
_COMMANDS = {
    'can': ('file','next','close','ready','block','sent','error'),
    'fast': ('file','program_file','direct','spool','next','close','offer','delivered','stored','eof','error'),
    'batch': ('run','fast','cleanup','close','result','fast_result','cleaned','cleanup_failed'),
}
_PARENT_COMMANDS = {
    'can': {'file','next','close'},
    'fast': {'file','program_file','direct','spool','next','close'},
    'batch': {'run','fast','cleanup','close'},
}
_LARGE = {'file','program_file','run','fast','result','fast_result','eof'}


class ControlProtocolError(ValueError):
    """内部协议版本、长度、命令或固定字段错误。"""


def _pairs(items):
    """建立不重复的JSON对象。

    参数: items为json解析器给出的键值对。
    返回: dict。
    异常: 重复键时ControlProtocolError。
    """
    result = {}
    for key,value in items:
        if key in result:
            raise ControlProtocolError('控制JSON包含重复键')
        result[key] = value
    return result


def _depth(data):
    """在解析前核JSON容器深度。

    参数: data为受长度限定的bytes或bytearray。
    返回: None，忽略字符串内的括号。
    异常: 超过320层或结构未闭合时ControlProtocolError。
    """
    depth = 0
    quoted = escaped = False
    for char in data:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91,123):
            depth += 1
            if depth > 320:
                raise ControlProtocolError('控制JSON嵌套超过320层')
        elif char in (93,125):
            depth -= 1
            if depth < 0:
                raise ControlProtocolError('控制JSON容器结构非法')
    if quoted or depth:
        raise ControlProtocolError('控制JSON截断或容器结构非法')


def encode_json(value, maximum):
    """逐片编码有限JSON结构。

    参数: value为已检查原生树，maximum为字节上限或父当前计划的None。
    返回: bytearray。
    异常: JSON类型、非有限数或超过额度。
    """
    output = bytearray()
    encoder = json.JSONEncoder(ensure_ascii=True,allow_nan=False,separators=(',',':'))
    for part in encoder.iterencode(value):
        data = part.encode('ascii')
        if maximum is not None and len(output)+len(data) > maximum:
            raise ControlProtocolError('控制消息超过本次接收额度')
        output.extend(data)
    return output


def decode_json(data):
    """解码有限JSON为原生值。

    参数: data为已按本次额度接收的字节。
    返回: dict/list/原生标量。
    异常: 重复键、非有限数、语法或深度错误。
    """
    _depth(data)
    def constant(value):
        """拒绝JSON宽松常量。

        参数: value为NaN/Infinity类原标记。
        返回: 无，始终抛错。
        异常: ControlProtocolError。
        """
        raise ControlProtocolError('控制JSON不允许非有限常量')
    try:
        value = json.loads(data,object_pairs_hook=_pairs,parse_constant=constant)
        # JSON 1e999 不走parse_constant，需要核最终数值是否有限。
        return native(value)
    except (UnicodeError,json.JSONDecodeError,RecursionError) as error:
        raise ControlProtocolError('控制JSON不是完整有效结构') from error


def _integer(value, minimum=0):
    """判断原生整数下界。

    参数: value候选值，minimum默认0。
    返回: bool，不把bool当整数。
    异常: 无。
    """
    return type(value) is int and value >= minimum


def _time(value):
    """判断有限非负计时。

    参数: value为候选秒数。
    返回: bool。
    异常: 无。
    """
    return type(value) in (int,float) and isfinite(value) and value >= 0


def _check(family, command, args):
    """核控制命令基础形状。

    参数: family通道、command命令、args参数列表或元组。
    返回: None。
    异常: 数量或字段基本类型不符时ControlProtocolError。
    """
    if type(args) not in (tuple,list):
        raise ControlProtocolError('控制消息参数非法')
    if command in ('next','close','direct','spool','cleanup'):
        valid = len(args)==0
    elif command == 'error':
        valid = len(args)==2 and all(type(v) is str for v in args)
    elif family == 'can':
        valid = (command=='file' and len(args)==5
            or command=='ready' and len(args)==2 and _integer(args[0],1) and _integer(args[1],1)
            or command=='block' and len(args)==4 and _integer(args[0],1) and all(_time(v) for v in args[1:])
            or command=='sent' and len(args)==1 and _time(args[0]))
    elif family == 'fast':
        valid = (command in ('file','program_file') and len(args)==4 and _integer(args[0])
                    and type(args[1]) is dict and type(args[2]) is str and type(args[3]) is str
            or command in ('offer','delivered','stored') and len(args)==3 and all(_integer(v) for v in args)
            or command=='eof' and len(args)==5 and all(_integer(v) for v in args[:2])
                    and type(args[2]) is dict and type(args[3]) is dict and _integer(args[4],1))
    else:
        valid = (command in ('run','fast') and len(args)==3 and type(args[0]) is dict
                    and type(args[1]) is str and (args[2] is None or type(args[2]) is str)
            or command=='result' and len(args)==2 and type(args[1]) is bool
            or command=='fast_result' and len(args) in (2,3) and type(args[0]) is dict and type(args[1]) is bool
            or command=='cleaned' and len(args)==1 and args[0] is None
            or command=='cleanup_failed' and len(args)==1 and type(args[0]) in (list,tuple)
                    and all(type(v) is str for v in args[0]))
    if not valid:
        raise ControlProtocolError('控制命令参数结构不符：'+command)


def _short(value, maximum):
    # 只编码有限前缀，不为截短而遍历完整巨型错误文本。
    """按JSON转义后的字节数截短诊断。

    参数: value文本，maximum为字节上限。
    返回: 短文本，发生截断时明确注明。
    异常: 输入不是文本时类型错误。
    """
    prefix = value[:maximum]
    encoded = json.dumps(prefix,ensure_ascii=True)
    if len(value)<=maximum and len(encoded)<=maximum:
        return value
    while len(encoded)>maximum-100 and prefix:
        prefix = prefix[:max(0,len(prefix)*3//4)]
        encoded = json.dumps(prefix,ensure_ascii=True)
    return prefix+'…[诊断已截断]'


def _diagnostics(family, command, args):
    """限制仅供展示的错误信息。

    参数: family通道、command命令、args已展开参数。
    返回: 参数列表，只修改独立结果字典中的诊断。
    异常: 诊断字段类型非法。
    """
    if command=='error':
        return [_short(args[0],128),_short(args[1],4096)]
    if family=='batch' and command=='cleanup_failed':
        return [[_short(value,1024) for value in args[0][:16]]]
    if family=='batch' and command in ('result','fast_result'):
        args[0] = dict(args[0])
        for name,maximum in (('error_type',128),('error_message',4096)):
            if args[0].get(name) is not None:
                args[0][name] = _short(args[0][name],maximum)
        args[0]['error_chain'] = [_short(value,1024) for value in args[0].get('error_chain',())[:16]]
    return args


class ControlChannel:
    """单个管道端的有限控制编码；不拥有额外句柄，close关闭实际Connection。

    parent表示父端，只允许向worker派发已定义命令；worker只能回报已定义事实。
    max_bytes是CAN/fast已有预算。独立batch任务及固定结果总长没有原有硬上限；
    每片仍至多64KiB，只随实际收到内容增长，不能把分片长度当作总RAM上限。
    """
    def __init__(self, connection, family, *, parent, max_bytes=None):
        """绑定一个已有控制端点。

        参数: connection真实Connection，family通道，parent方向，max_bytes已有预算或batch的None。
        返回: 新编码端点，不新增句柄。
        异常: 通道、方向或额度错误。
        """
        if family not in _FAMILIES or type(parent) is not bool:
            raise ValueError('控制通道类型非法')
        if max_bytes is not None and not _integer(max_bytes,1):
            raise ValueError('控制接收额度非法')
        self._connection, self.family, self.parent = connection,family,parent
        self.maximum = max_bytes
        self.last_payload_bytes = 0

    def _limit(self, operation, *, sending):
        """取得当前消息可用额度。

        参数: operation固定命令，sending区分发送或接收。
        返回: 字节上限。
        异常: batch固定大消息沿用None；CAN/fast未提供预算时ControlProtocolError。
        """
        if operation not in _LARGE:
            return CHUNK
        if self.family != 'batch':
            if self.maximum is None:
                raise ControlProtocolError('CAN/fast控制通道缺少既有预算上限')
            return self.maximum
        # 路径任务的合法身份长度不能从短路径推断；不新增父端配置读取或任意阈值。
        # recv仅按实际片增长，不按对端声明的总长预约或预分配。
        return None

    def _direction(self, operation, *, sending):
        """核发送者是否有权发此命令。

        参数: operation命令，sending为本端发送与否。
        返回: None。
        异常: 父子方向不符时ControlProtocolError。
        """
        from_parent = self.parent if sending else not self.parent
        if (operation in _PARENT_COMMANDS[self.family]) != from_parent:
            raise ControlProtocolError('控制命令发送方向非法')

    def send(self, message):
        """发送一条固定命令。

        参数: message为现有控制tuple/list。
        返回: None，返回前释放编码副本。
        异常: 字段、额度或实际管道写入错误。
        """
        if type(message) not in (tuple,list) or not message or message[0] not in _COMMANDS[self.family]:
            raise ControlProtocolError('控制命令未知')
        operation = message[0]
        self._direction(operation,sending=True)
        _check(self.family,operation,message[1:])
        arguments = _diagnostics(self.family,operation,pack_message(self.family,message))
        check_message_fields(self.family,operation,arguments)
        payload = encode_json(arguments,self._limit(operation,sending=True))
        self.last_payload_bytes = len(payload)
        try:
            # 小消息只写一次管道，避免每个原控制通知变成两次系统调用。
            # 大消息首片含固定头，其后每片至多64KiB；不会缓存整批任务。
            first_size=min(len(payload),CHUNK-_HEADER.size)
            first=bytearray(_HEADER.pack(b'CCP1',_FAMILIES[self.family],
                _COMMANDS[self.family].index(operation),len(payload)))
            view = memoryview(payload)
            try:
                first.extend(view[:first_size])
                self._connection.send_bytes(first)
                first=None
                for offset in range(first_size,len(payload),CHUNK):
                    self._connection.send_bytes(view[offset:offset+CHUNK])
            finally:
                view.release()
        finally:
            payload = arguments = first = None

    def recv(self):
        """接收一条固定消息。

        参数: 无。
        返回: 现有消费者使用的tuple。
        异常: 版本、长度、字段、截断或管道错误。
        """
        first = self._connection.recv_bytes(CHUNK)
        if len(first)<_HEADER.size:
            raise ControlProtocolError('控制消息头截断')
        magic,family,code,size = _HEADER.unpack_from(first)
        if magic!=b'CCP1' or family!=_FAMILIES[self.family] or code>=len(_COMMANDS[self.family]):
            raise ControlProtocolError('控制消息版本/通道/命令未知')
        operation = _COMMANDS[self.family][code]
        self._direction(operation,sending=False)
        maximum = self._limit(operation,sending=False)
        if size==0 or maximum is not None and size>maximum:
            raise ControlProtocolError('控制声明长度超过本次接收额度')
        first_size=min(size,CHUNK-_HEADER.size)
        if len(first)!=_HEADER.size+first_size:
            raise ControlProtocolError('控制首片长度不符')
        payload = bytearray(memoryview(first)[_HEADER.size:])
        first=None
        try:
            while len(payload)<size:
                expected = min(CHUNK,size-len(payload))
                packet = self._connection.recv_bytes(expected)
                if len(packet)!=expected:
                    raise ControlProtocolError('控制分片截断或长度不符')
                payload.extend(packet)
            arguments = decode_json(payload)
            _check(self.family,operation,arguments)
            check_message_fields(self.family,operation,arguments)
            self.last_payload_bytes = size
            return restore_message(self.family,operation,arguments)
        finally:
            payload = None

    def __enter__(self):
        """保持原管道上下文用法。

        参数: 无。
        返回: 当前编码端点。
        异常: 无。
        """
        return self

    def __exit__(self, *args):
        """按原管道上下文关闭。

        参数: args为上下文异常三元组。
        返回: 原Connection.__exit__返回值。
        异常: 真实关闭错误。
        """
        return self._connection.__exit__(*args)

    def poll(self, *args):
        """查询实际管道是否可读。

        参数: args沿用Connection.poll的等待参数。
        返回: bool。
        异常: 真实管道错误。
        """
        return self._connection.poll(*args)

    def fileno(self):
        """返回同一实际管道句柄。

        参数: 无。
        返回: int，供multiprocessing.wait使用。
        异常: 已关闭等底层句柄错误。
        """
        return self._connection.fileno()

    @property
    def closed(self):
        """报告实际管道关闭状态。

        参数: 无。
        返回: bool。
        异常: 无。
        """
        return self._connection.closed

    def close(self):
        """关闭本端实际管道。

        参数: 无。
        返回: None。
        异常: 真实关闭错误。
        """
        return self._connection.close()
