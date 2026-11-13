"""在独立spawn进程按单条PULL许可调用共用BLF读取与串行解码政策。

有效INIT后导入依赖并加载一次DBC；惰性读取器在首次PULL才打开输入，READY不取帧。
每次许可按原序读取和解码一次，STATUS/ACK/STOP不授予读取许可。只使用限长JSON
bytes协议，异常发送有限事实，实际子退出和父侧预算清理由协议控制器确认。"""

# spawn加载时不触及CAN库或输入；读取依赖只在收到有效INIT后加载。
from importlib import metadata
import os
from pathlib import Path
import platform
from ..dbc_loading import load_dbc_file
from .records import (LegacyCANRequest, LegacyDecodedFrame, LegacyRawFrame, MAX_WIRE_BYTES,
    PROFILE_ID, decode_packet, decoded_to_dict, encode_packet, field_from_dict, field_to_dict)

def _send(connection, packet):
    """通过bytes接口发送一个有界JSON包，不调用pickle通道。

    参数: connection为本子进程Connection；packet为协议dict。返回: None。
    异常: 原wire类型/限额或管道错误；不重试导致重复ITEM。
    """
    connection.send_bytes(encode_packet(packet))


def _receive(connection):
    """只接收一个不超过单包上限的bytes消息。

    参数: connection为本子进程Connection。返回: 已校验dict。
    异常: EOFError/OSError/协议错误传播，不把断管当正常来源EOF。
    """
    return decode_packet(connection.recv_bytes(MAX_WIRE_BYTES))


def _exact(packet, names):
    """限制每种控制包的精确字段，不让多余许可或版本字段静默生效。

    参数: packet为已解析dict；names为允许键容器。返回: None。
    异常: ValueError为字段缺失或多余。
    """
    if set(packet) != set(names):
        raise ValueError('旧CAN控制包字段缺失或多余')


def _request(packet):
    """解析唯一INIT，只接受单个实际BLF和原DBC路径，不读取其内容摘要。

    参数: packet为INIT dict。返回: LegacyCANRequest。
    异常: 类型/形状/版本/路径错误；不打开BLF或加载DBC。
    """
    _exact(packet, ('op', 'version', 'path', 'dbc_path', 'fields'))
    if packet['op'] != 'init' or type(packet['version']) is not int or packet['version'] != 1:
        raise ValueError('旧CAN需要init/version1')
    if type(packet['path']) is not str or type(packet['dbc_path']) is not str or type(packet['fields']) is not list:
        raise TypeError('旧CAN INIT需要文本路径与fields数组')
    request = LegacyCANRequest(Path(packet['path']), Path(packet['dbc_path']),
        tuple(field_from_dict(value) for value in packet['fields']))
    # 只做stat和扩展名边界；不额外读取原CAN或预扫消息，不暗换另一种profile。
    if request.input_path.suffix.lower() != '.blf' or not request.input_path.is_file():
        raise ValueError('首版旧CAN仅支持单个现有BLF文件')
    if not request.dbc_path.is_file():
        raise FileNotFoundError(request.dbc_path)
    return request


def _load_can_runtime():
    """在有效INIT后导入真实CAN依赖，模块导入本身只使用标准库。

    参数: 无。返回: python-can与cantools模块。异常: 保留缺失依赖的可执行提示。
    不读取来源、DBC或原项目文件，不安装同名vendor模块。
    """
    from ..can_dependencies import import_can_dependency
    return import_can_dependency('can'), import_can_dependency('cantools')


def _iter_blf(path):
    """按许可惰性创建共用BLF读取器，原消息顺序交付且可靠关闭本次文件。

    参数: 已检查的BLF路径。返回: can.Message生成器。异常: 真实读取/关闭错误。
    创建生成器不打开文件；第一次next才调用BLFRead，STOP或EOF关闭同一owner。
    """
    from ..sources.blf import BLFRead, BLFSpec
    from ..results.budget import ResourceBudget, _cleanup_owner
    reader = primary = None
    try:
        reader = BLFRead(BLFSpec(Path(path)), ResourceBudget(), frame_only=True)
        yield from reader
    except BaseException as error:
        primary = error
        if reader is None:
            pending=getattr(error,'blf_read_cleanup_owner',None)
            if pending is not None:
                _cleanup_owner(pending,error,'blf_read_cleanup_owner','协议BLF构造')
        raise
    finally:
        if reader is not None and not reader.closed:
            if primary is None or isinstance(primary,GeneratorExit):
                reader.close()
            else:
                _cleanup_owner(reader,primary,'blf_read_cleanup_owner','协议BLF读取器')


def _field_metadata(db, fields, *, cycle_fields=()):
    """只读同次db公开messages/signals核定位唯一，并返回原单位。

    参数: db为同次加载的唯一DBC数据库；fields为原LegacyCANField tuple；
        cycle_fields仅指定需要周期的字段，须在fields中。默认不访问cycle_time。
    返回: 按请求顺序的字段事实；周期请求的字段另含正cycle_ns。
        仅DBC为FD而定位为经典CAN时增加固定兼容提示。
        channel保声明，不冒称DBC已测通道；不把DBC声明写回原帧。
    异常: ValueError为ID/消息/帧型/信号歧义或不符，TypeError为单位不受支持。
    """
    if cycle_fields:
        from .dbc_cycles import require_cycle_fields, cycle_time_ns
        require_cycle_fields(cycle_fields)
        if not set(cycle_fields).issubset(fields):
            raise ValueError('周期字段须包含在本次DBC定位中')
    from .binding import dbc_candidates
    periods = {} if cycle_fields else None
    result = []
    for field in fields:
        # 多定义允许由实际原帧决定；初始化所需的单位不能随候选改变。
        candidates = dbc_candidates(db, field.frame_id, (field.signal,), field.is_extended, field.is_fd)
        units = {signal.unit for message in candidates for signal in message.signals if signal.name == field.signal}
        if len(units) != 1:
            raise ValueError('候选DBC信号单位不同，请补充 is_extended 或 is_fd: ' + field.signal)
        unit = next(iter(units))
        compatible = field.is_fd is False and all(message.is_fd is True for message in candidates)
        if unit is not None and type(unit) is not str:
            raise TypeError('原DBC公开unit需要文本或None')
        item = {'locator': field_to_dict(field), 'unit': unit}
        if field.is_extended is None or field.is_fd is None:
            # 父读取器据此跳过同ID但不含所需信号的帧，不伪造一次失效更新。
            item['dbc_frames'] = [list(pair) for pair in dict.fromkeys(
                (message.is_extended_frame, message.is_fd) for message in candidates)]
        if compatible:
            item['frame_format_compatibility'] = {'code': 'dbc_fd_classic_selector',
                'dbc_is_fd': True, 'requested_is_fd': False}
        if field in cycle_fields:
            # 同一物理报文多个别名只取一次周期，后续记录不再访问DBC周期。
            values = set()
            for message in candidates:
                # 多信号来自同一消息对象时只读一次周期，同ID不同定义不能相互覆盖。
                identity = id(message)
                if identity not in periods:
                    periods[identity] = cycle_time_ns(message.cycle_time)
                values.add(periods[identity])
            if len(values) != 1:
                raise ValueError('候选DBC周期不同，请补充帧类型、period 或 valid_for: ' + field.signal)
            item['cycle_ns'] = next(iter(values))
        result.append(item)
    return result


def _frame(msg):
    """保存当前消息的公开写出字段，不重建CAN消息或执行解码。

    参数: msg为共用BLF读取器返回的can.Message。返回: LegacyRawFrame。
    异常: 新边界字段校验失败；data仅无损复制为bytes，不改timestamp/DLC/标志。
    """
    if len(msg.data) > 64:
        raise ValueError('原报文data超过64字节，不能先复制再拒绝')
    return LegacyRawFrame(timestamp=msg.timestamp, arbitration_id=msg.arbitration_id,
        is_extended_id=msg.is_extended_id, is_remote_frame=msg.is_remote_frame,
        is_error_frame=msg.is_error_frame, channel=msg.channel, dlc=msg.dlc, data=bytes(msg.data),
        is_fd=msg.is_fd, is_rx=msg.is_rx, bitrate_switch=msg.bitrate_switch,
        error_state_indicator=msg.error_state_indicator)


def _argument_text(value, limit):
    """只摘要原生异常参数，不执行任意对象str或先展开完整巨型消息。

    参数: value为一个原args值；limit为最大字符数。返回: 有限str，短原str保持内容。
    异常: 无主动异常；未知对象仅标明类型，不调用其自定义字符串方法。
    """
    if type(value) is str:
        return value[:limit]
    if value is None or type(value) in (bool, float):
        return repr(value)[:limit]
    if type(value) is int:
        return str(value)[:limit] if value.bit_length() <= 128 else '<超过128位的整数参数>'
    return '<参数类型:' + type(value).__name__[:64] + '>'


def _error_packet(exc, phase, request_id):
    """保存有限原错误事实，不把远端异常对象或任意类传给父进程。

    参数: exc为本child原错；phase为有限阶段文本；request_id为当前许可或None。
    返回: 有限ERROR dict；message是至多4个args摘要，traceback仅至多8个栈地点，
        均不是完整str(exc)或完整traceback，截断有明确note，短单str参数保持原文本。
    异常: 标准库字段访问/编码错误传播；调用方仍须确定退出，不伪报正常EOF。
    """
    # 不全量format_exception/str(exc)，仅读有限原参数及栈地点，绝不访问locals/gi_frame。
    arguments = exc.args if type(exc.args) is tuple else ()
    message = ', '.join(_argument_text(value, 1024) for value in arguments[:4])
    if not arguments:
        message = '远端异常无可安全摘要的原生args'
    places, current = [], exc.__traceback__
    for _ in range(8):
        if current is None:
            break
        code = current.tb_frame.f_code
        places.append(code.co_filename[:256] + ':' + str(current.tb_lineno) + ' ' + code.co_name[:128])
        current = current.tb_next
    trace = '\n'.join(places)
    original_notes = getattr(exc, '__notes__', ())
    notes = [note[:256] if type(note) is str else '<非文本note>' for note in
        (original_notes[:8] if type(original_notes) in (tuple, list) else ())]
    notes.append('远端message仅原args有限摘要；traceback仅有限栈地点，非完整str/trace。')
    limit = 4096
    while True:
        packet = {'op': 'error', 'request_id': request_id, 'phase': phase,
            'error': {'module': type(exc).__module__[:128], 'type': type(exc).__name__[:128],
                'message': message[:limit], 'traceback': trace[:limit],
                'notes': [note[:min(limit, 256)] for note in notes] + ['远端诊断有界；可能截断。']}}
        try:
            encode_packet(packet)
            return packet
        except ValueError:
            # 每轮减半，固定包头的诊断不受输入长度放大；最短仍明确失败类型。
            if limit <= 64:
                return {'op': 'error', 'request_id': request_id, 'phase': phase,
                    'error': {'module': type(exc).__module__[:32], 'type': type(exc).__name__[:32],
                        'message': '远端错误诊断超过wire上限', 'traceback': '', 'notes': ['诊断已截断。']}}
            limit //= 2


def _report_error(connection, exc, phase, request_id):
    """尽力发送原错误事实，断管不替代child原错或阻止退出。

    参数: connection为本连接；exc/phase/request_id为原失败事实。返回: None。
    异常: 不传播附加报告错误；原失败仍由worker最终非零退出表达。
    """
    try:
        _send(connection, _error_packet(exc, phase, request_id))
    except BaseException as diagnostic:
        exc.add_note('旧CAN远端错误报告附加失败: ' + type(diagnostic).__name__)


def worker_main(connection):
    """作为spawn目标按INIT/PULL协议调用共用BLF读取与串行兼容解码，等待许可时不预取。

    参数: connection为父传来的独立duplex Connection。返回: 正常STOP或真实EOF时None。
    异常: 原错误尽力发ERROR后以SystemExit(1)退出；连接/生成器附加关闭错误也非零。
    副作用: 本child内一次DBC加载、一次iter_frames、每许可一次next/parse；不额外扫描。
    """
    iterator, failure, request_id = None, None, None
    phase = 'init'
    pulls_received = frames_returned = parse_calls = 0
    try:
        request = _request(_receive(connection))
        phase = 'dependencies'
        can, cantools = _load_can_runtime()
        phase = 'dbc'
        # 共用安全DBC加载函数执行一次加载，不做第二次解析。
        db = load_dbc_file(str(request.dbc_path), cantools)
        phase = 'metadata'
        from .binding import FrameBindingResolver
        from .decode_policy import decode_serial_frame as _parse_selected
        from collections import Counter
        resolver = FrameBindingResolver(db, request.fields)
        duplicate_ids = {frame_id for frame_id, count in Counter(message.frame_id for message in db.messages).items()
                         if count > 1}
        phase = 'metadata'
        fields = _field_metadata(db, request.fields)
        iterator = _iter_blf(str(request.input_path))
        versions = {'python': platform.python_version(), 'python-can': metadata.version('python-can'),
            'cantools': metadata.version('cantools'), 'natsort': metadata.version('natsort')}
        _send(connection, {'op': 'ready', 'version': 1, 'profile': PROFILE_ID, 'worker_pid': os.getpid(),
            'fields': fields, 'dependency_versions': versions})
        # 只在收到下一条PULL时取原下一帧；STATUS/ACK/STOP均不授予此许可。
        while True:
            phase, request_id = 'control', None
            packet = _receive(connection)
            operation = packet.get('op')
            if operation == 'stop':
                _exact(packet, ('op',))
                break
            if operation == 'status':
                _exact(packet, ('op',))
                _send(connection, {'op': 'status', 'pulls_received': pulls_received,
                    'frames_returned': frames_returned, 'parse_calls': parse_calls})
                continue
            if operation == 'ack':
                expected = ('op', 'request_id') if 'request_id' in packet else ('op',)
                _exact(packet, expected)
                if 'request_id' in packet and (frames_returned == 0 or type(packet['request_id']) is not int
                        or packet['request_id'] != frames_returned - 1):
                    raise ValueError('ACK只允许确认最近返回ITEM')
                _send(connection, packet)
                continue
            if operation != 'pull':
                raise ValueError('未知旧CAN控制操作')
            _exact(packet, ('op', 'request_id'))
            candidate_id = packet['request_id']
            request_id = candidate_id if type(candidate_id) is int and candidate_id >= 0 else None
            if request_id is None or request_id != frames_returned:
                raise ValueError('PULL许可必须从0严格连续')
            pulls_received += 1
            phase = 'next'
            try:
                msg = next(iterator)
            except StopIteration:
                # EOF需要实际多一次许可，候选发出后仍须父确认本child退出，不能靠断管猜EOF。
                _send(connection, {'op': 'eof', 'request_id': request_id, 'frame_count': frames_returned})
                break
            phase = 'parse'
            parse_calls += 1
            fields_for_frame = resolver.fields_for(msg)
            message = resolver.message_for(msg, fields_for_frame)
            values = _parse_selected(db, msg, message, duplicate_ids)
            phase = 'item'
            record = LegacyDecodedFrame(frames_returned, _frame(msg), values)
            _send(connection, {'op': 'item', 'request_id': request_id, 'record': decoded_to_dict(record)})
            frames_returned += 1
            # 释放本层当前wire/记录引用，不给下一帧任何许可；旧generator内部状态不读取。
            msg = values = record = None
    except BaseException as exc:
        failure = exc
        _report_error(connection, exc, phase, request_id)
    finally:
        # 生成器退出时关闭共用BLF owner；父进程仍须确认实际子退出。
        if iterator is not None:
            try:
                iterator.close()
            except BaseException as cleanup:
                if failure is None:
                    failure = cleanup
                    _report_error(connection, cleanup, 'generator_close', request_id)
                else:
                    failure.add_note('旧生成器关闭附加失败: ' + type(cleanup).__name__)
        try:
            connection.close()
        except BaseException as cleanup:
            if failure is None:
                failure = cleanup
            else:
                failure.add_note('旧CAN子连接关闭附加失败: ' + type(cleanup).__name__)
    if failure is not None:
        raise SystemExit(1)
