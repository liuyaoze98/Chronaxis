"""在隔离子进程按有限批次调用原CAN函数，默认仍解码全部报文。

INIT仍仅加载原DBC和公开字段元数据；每次pull_batch明确许可原帧条数与字节上限。
默认每条执行原next/parse一次。显式decode_frame_ids限制允许解码的ID，只有其中
实际请求了字段的ID才调用parse；纯常量触发帧不调用parse。全部原帧仍
顺序读取并保留原时间、字段校验；所选帧仍一次调用原parse，参数不变。按需模式在
原parse返回后立即只取INIT所需字段，缺失键保持缺失；v3 READY确认这一投影策略。
原帧保留集合与解码集合独立，导出原始帧可保留全部帧而不解码无需求ID。
auto模式在原生消息ID不匹配时先跳过；仅source需要读其时间。selected/none目标
只保存必要身份与所需值；非原生消息沿完整原帧检查并计入新包的回退数量。
字节不足容纳下一条最大记录时先结束当前批，不提前读取再丢弃。真正StopIteration
可与最后批数据一起报告，子实际退出及资源回收仍由父确认。没有后台预读或pickle。
"""

from collections.abc import Mapping
from collections import Counter
from importlib import metadata
import json
from math import isfinite
import os
import platform

from . import worker
from .records import (PROFILE_ID, MAX_WIRE_BYTES, LegacyDecodedFrame, decoded_to_dict,
                      _decoded_values_size)
from .batch_wire import (HEADER, DEMAND_HEADER, LENGTH, MIN_BATCH_BYTES, MAX_BATCH_BYTES,
                         MAX_BATCH_ROWS, FILE_HEADER, FILE_MAGIC, encode_batch)
from .batch_validation import validate_discarded, _item_base_size
from .required_records import RequiredCANFrame, RequiredDecodedFrame, required_to_dict


# [home] READY明确区分按字段投影与旧v2的整条消息values，不能把两种检查范围混同。
REQUESTED_VALUES_POLICY = 'requested_fields-v1'


def _parse_selected(processor, db, frame, message, duplicate_ids):
    """普通ID复用原解码入口，同ID多定义时直接调用选中的同库解码实现。

    参数: processor旧入口、db同次数据库、frame原帧、message已选定义、duplicate_ids重复ID集合。
    返回: 原物理值dict；DBC解码失败为空dict。异常: 非DBC结构错误由外层传播。
    """
    if message is None or frame.arbitration_id not in duplicate_ids:
        return processor.parse_frame(frame, db)
    # 不改冻结旧函数；其仅按整数ID查表会选错定义，此处使用相同库参数和解码方法。
    from cantools.database.errors import DecodeError
    try:
        return message.decode(frame.data, decode_choices=False, allow_truncated=True)
    except DecodeError:
        return {}


def _requested_fields(fields, decode_ids):
    """按固定报文ID整理所需信号名，不读取输入或遍历解码结果。

    参数: fields为INIT已校验的字段tuple；decode_ids为固定解码ID集合。
    返回: ID到去重信号名字典的有限映射，名字次序保持请求顺序。
    异常: ValueError表示字段所在报文不在解码范围；原分配/取消错误直接传播。
    父策略费用为每个字段另付1024B，覆盖此表及构建临时槽；名称借自原请求。
    """
    projected = field = None
    try:
        projected = {}
        for field in fields:
            if field.frame_id not in decode_ids:
                raise ValueError('所需字段的报文ID必须属于固定解码集合')
            projected.setdefault(field.frame_id, {})[field.signal] = None
        return projected
    finally:
        # 构建失败的traceback不能在父关闭并归还策略费用后继续借用投影表。
        projected = field = fields = decode_ids = None


def _project_values(values, names):
    """只读取本报文所需的原值，让后续完整模型只检查这些值。

    参数: values为原parse返回值；names为本ID需要的名字映射或空tuple。
    返回: 新dict，保留实际存在的所需键；KeyError代表缺失，不补None或零。
    异常: 有字段需求时非Mapping报TypeError；所需键访问和取消错误原样传播。
    无字段的常量触发报文直接返回空dict，不遍历或校验没有用途的原values。
    """
    projected = name = value = None
    try:
        if not names:
            return {}
        if not isinstance(values, Mapping):
            raise TypeError('解码记录需要LegacyRawFrame与数值Mapping')
        projected = {}
        for name in names:
            try:
                value = values[name]
            except KeyError:
                continue
            projected[name] = value
        return projected
    finally:
        # 后续模型负责所需值的类型、诊断浮点和ITEM上限；本层不保留原结果引用。
        values = names = projected = name = value = None


def _encode_fresh_packet(packet):
    """编码本worker刚完成完整检查的记录，省去同一JSON树的再次遍历。

    参数: packet只能是紧邻LegacyDecodedFrame成功构造后由原decoded_to_dict生成的
        私有dict；两者之间没有用户回调或对象交付。不是任意外部JSON的编码入口。
    返回: 与公开encode_packet相同的UTF-8 bytes，不带换行。
    异常: 原JSON/UTF-8编码错误、实际超过65536字节的ValueError或原取消异常。
    完整模型已检查全部帧字段、含ITEM外壳的长度及收到的Mapping两遍，再复制冻结数值；
    原转换只生成固定字段与非有限数值标签。沿用原批许可费用，不保留跨记录状态。
    """
    payload = None
    try:
        # 保持原JSON参数和实际字节复核；复用的是前面的检查，不放宽最终传输上限。
        payload = json.dumps(packet, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(',', ':')).encode('utf-8')
        if len(payload) > MAX_WIRE_BYTES:
            raise ValueError('wire包超过65536字节')
        return payload
    finally:
        # 调用方可保留取消的traceback，本层不再借用记录树或编码缓冲。
        packet = payload = None


def _limits(packet, frames_returned):
    """验证本次批许可及解码后投影，非法许可不能推进旧读取器。

    参数: packet为已检查JSON；frames_returned为已发送的原帧数。
    返回: (原帧上限,字节上限,保留ID集合或None)。异常: TypeError/ValueError。
    """
    worker._exact(packet, ('op', 'request_id', 'rows', 'bytes', 'frame_ids'))
    if type(packet['request_id']) is not int or packet['request_id'] != frames_returned:
        raise ValueError('批次许可必须按原帧序号连续')
    rows, size, ids = packet['rows'], packet['bytes'], packet['frame_ids']
    if (type(rows) is not int or not 1 <= rows <= MAX_BATCH_ROWS
            or type(size) is not int or not MIN_BATCH_BYTES <= size <= MAX_BATCH_BYTES):
        raise ValueError('批次许可条数或字节上限非法')
    if ids is not None and (type(ids) is not list or len(ids) > 4096
            or any(type(value) is not int or not 0 <= value <= 0x1fffffff for value in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('解码后保留ID必须是无重复29位整数列表或None')
    return rows, size, None if ids is None else frozenset(ids)


def batch_worker_main(connection, *, decode_frame_ids=None, input_check='full', time_scope='source',
                      input_paths=None, decode_policy='legacy', cycle_fields=(), metadata_fields=()):
    """处理一次独立批次会话，沿用原INIT、元数据和有限远端错误格式。

    参数: connection为spawn交付的独立连接；decode_frame_ids=None沿用全解码，
        原生tuple明确本次固定解码ID，允许空集合；input_check默认full保持旧行为，
        auto必须固定解码ID；time_scope为source/selected/none，full必须source。
        input_paths为原序路径文本tuple或None；decode_policy为legacy/strict/partial。
        cycle_fields显式请求同次DBC周期，metadata_fields仅取候选；不改变request.fields或原parse调用集合。
        新政策只核有字段需求的帧长度，非数据帧不解码；解码空值不继承前值。
    返回: 正常STOP或真实EOF时None。
    异常: 失败发送有限事实并以SystemExit(1)退出；清理副错不替代原错误。
    副作用: 子进程内一次load_file，每个声明文件一次iter_frames；每原帧顺序next，默认全部parse，
        显式按需只对固定集合内有字段需求的帧调用parse，并立即投影所需字段。未解码帧不产生或检查
        解码值，仍检查原帧；原始帧保留范围不扩大解码范围。
        只关闭自己连接和原生成器；不声称原reader已有可靠公开close实现。
    """
    iterator = failure = request_id = None
    phase, frames_returned, pulls_received, parse_calls = 'init', 0, 0, 0
    timestamps = encoded = record = frame = msg = values = payload = None
    decode_ids = projected_fields = ready = None
    try:
        request = worker._request(worker._receive(connection))
        from .decode_policy import validate_decode_policy, check_decode_length
        validate_decode_policy(decode_policy)
        paths = (str(request.input_path),) if input_paths is None else input_paths
        if (type(paths) is not tuple or not 1 <= len(paths) <= 4096
                or any(type(p) is not str or not p or len(p) > 4096 for p in paths)
                or paths[0] != str(request.input_path)):
            raise ValueError('连续文件声明须与INIT首路径一致')
        input_index = 0
        envelope_size = FILE_HEADER.size if len(paths) > 1 else 0
        if (input_check not in ('auto', 'full') or time_scope not in ('none', 'selected', 'source')
                or input_check == 'full' and time_scope != 'source'
                or input_check == 'auto' and decode_frame_ids is None):
            raise ValueError('输入检查与时间范围必须匹配固定按需解码策略')
        if decode_frame_ids is not None:
            # 策略来自启动实参，不能由后续PULL更改；无策略时保持原INIT和执行先后。
            if (type(decode_frame_ids) is not tuple or len(decode_frame_ids) > 4096
                    or any(type(value) is not int or not 0 <= value <= 0x1fffffff
                           for value in decode_frame_ids)
                    or len(set(decode_frame_ids)) != len(decode_frame_ids)):
                raise ValueError('按需解码ID必须是无重复29位整数tuple')
            decode_ids = frozenset(decode_frame_ids)
            projected_fields = _requested_fields(request.fields, decode_ids)
        phase = 'vendor'
        files, processor, vendor = worker._load_vendor()
        # 仅取旧模块已加载的真实类，不提前导入CAN库；测试替身没有此类时沿用原字段路径。
        native_message_type = getattr(getattr(files, 'can', None), 'Message', None)
        phase = 'dbc'
        db = processor.cantools.database.load_file(str(request.dbc_path))
        phase = 'metadata'
        from .binding import FrameBindingResolver
        resolver = FrameBindingResolver(db, request.fields)
        duplicate_ids = {frame_id for frame_id, count in Counter(message.frame_id for message in db.messages).items()
                         if count > 1}
        phase = 'metadata'
        if cycle_fields or metadata_fields:
            from .dbc_cycles import require_cycle_fields
            require_cycle_fields(cycle_fields)
            require_cycle_fields(metadata_fields)
            all_fields = tuple(dict.fromkeys((*request.fields,*cycle_fields,*metadata_fields)))
            fields = worker._field_metadata(db,all_fields,cycle_fields=cycle_fields)
        else:
            fields = worker._field_metadata(db, request.fields)
        # 长度表只在新政策且字段确有需求时建立，旧调用不增加DBC查询。
        if (input_paths is not None or decode_policy != 'legacy') and os.path.isdir(paths[0]):
            raise ValueError('新原始报文入口需要文件，不能隐式扫描目录')
        iterator = files.iter_frames(paths[0])
        versions = {'python': platform.python_version(), 'python-can': metadata.version('python-can'),
                    'cantools': metadata.version('cantools'), 'natsort': metadata.version('natsort')}
        ready = {'op': 'ready', 'version': 1, 'profile': PROFILE_ID,
            'worker_pid': os.getpid(), 'fields': fields, 'dependency_versions': versions,
            'vendor_sha256': vendor}
        if decode_ids is not None:
            ready.update(version=3, decode_scope='requested', decode_frame_ids=list(decode_frame_ids),
                         decoded_values_policy=REQUESTED_VALUES_POLICY)
        if input_check == 'auto':
            ready.update(version=4, input_check=input_check, time_scope=time_scope)
        if input_paths is not None or decode_policy != 'legacy' or cycle_fields or metadata_fields:
            ready.update(base_version=ready['version'], version=5, input_paths=list(paths),
                         decode_policy=decode_policy)
        if cycle_fields:
            ready['cycle_fields'] = [worker.field_to_dict(f) for f in cycle_fields]
        if metadata_fields:
            ready['metadata_fields'] = [worker.field_to_dict(f) for f in metadata_fields]
        worker._send(connection, ready)
        ready = None
        while True:
            phase, request_id = 'control', None
            packet = worker._receive(connection)
            if packet.get('op') == 'stop':
                worker._exact(packet, ('op',))
                break
            if packet.get('op') == 'status':
                worker._exact(packet, ('op',))
                worker._send(connection, {'op': 'status', 'pulls_received': pulls_received,
                    'frames_returned': frames_returned, 'parse_calls': parse_calls})
                continue
            if packet.get('op') != 'pull_batch':
                raise ValueError('未知批次控制操作')
            rows, byte_limit, selected = _limits(packet, frames_returned)
            byte_limit -= envelope_size
            if byte_limit < MIN_BATCH_BYTES:
                raise ValueError('连续批次字节许可不足')
            if (input_check == 'auto' and time_scope == 'source'
                    and byte_limit < MIN_BATCH_BYTES+DEMAND_HEADER.size-HEADER.size):
                raise ValueError('全来源按需批次字节许可不足以容纳一条最大记录')
            request_id = frames_returned
            pulls_received += 1
            timestamps, encoded = [], []
            raw_count, full_checks = 0, 0
            encoded_size, eof = (DEMAND_HEADER.size if input_check == 'auto' else HEADER.size), False
            while raw_count < rows:
                # 预留最坏单条空间后才授权next；未知是否匹配时不能先读再丢掉。
                if encoded_size + (8 if time_scope == 'source' else 0) + LENGTH.size + MAX_WIRE_BYTES > byte_limit:
                    break
                phase = 'next'
                if iterator is None:
                    input_index += 1
                    if os.path.isdir(paths[input_index]):
                        raise ValueError('连续原始报文需要文件，不能隐式扫描目录')
                    iterator = files.iter_frames(paths[input_index])
                try:
                    msg = next(iterator)
                except StopIteration:
                    if input_index == len(paths)-1:
                        # 最后输入保持原收尾顺序：发EOF后在finally关闭。
                        eof = True
                        break
                    iterator.close()
                    iterator = None
                    if raw_count:
                        # 一批只来自一个文件；下次许可才开始下个文件。
                        break
                    continue
                sequence = frames_returned + raw_count
                raw_count += 1
                if input_check == 'auto':
                    # 先读取ID；精确原生消息的不相关帧在此跳过，不能碰时间或其他属性。
                    frame_id = msg.arbitration_id
                    retained = selected is None or frame_id in selected
                    needed = frame_id in decode_ids
                    native = native_message_type is not None and type(msg) is native_message_type
                    if not native:
                        # 自定义消息可能有属性副作用，沿完整旧帧检查；实际回退数写入新包。
                        frame = worker._frame(msg)
                        full_checks += 1
                    if time_scope == 'source':
                        timestamp = msg.timestamp if native else frame.timestamp
                        if type(timestamp) is not float or not isfinite(timestamp):
                            raise ValueError('原报文timestamp需要有限float秒')
                        timestamps.append(timestamp)
                        encoded_size += 8
                    if not retained and not needed:
                        if not native:
                            # _frame只核类型/字符数，旧完整检查还核UTF-8与ITEM总字节。
                            # 复用同次快照，不为此再次读取自定义消息的属性或调用解码。
                            _item_base_size(frame, sequence)
                        msg = frame = None
                        continue
                    phase = 'parse'
                    if (projected_fields.get(frame_id) and (decode_policy == 'legacy'
                            or not (msg.is_remote_frame or msg.is_error_frame))):
                        active = resolver.fields_for(msg)
                        message = resolver.message_for(msg, active)
                        if message is None:
                            values = {}
                        else:
                            check_decode_length(msg, message.length, decode_policy)
                            parse_calls += 1
                            values = _parse_selected(processor, db, msg, message, duplicate_ids)
                    else:
                        values = {}
                    phase = 'batch'
                    values = _project_values(values, projected_fields.get(frame_id, ()))
                    if not native:
                        # 非原生完整回退按旧原帧外壳计算所需值余量；不能用较小的
                        # Required外壳放过原ITEM已超限的输入，也不能重复构造_frame。
                        available = MAX_WIRE_BYTES-_item_base_size(frame, sequence)+2
                        _decoded_values_size(values, available)
                    if time_scope == 'source':
                        # source仍需完整原记录承载现有时序/导出消费者；只处理真正所需ID。
                        record = LegacyDecodedFrame(sequence, worker._frame(msg) if native else frame, values)
                        packet_tree = decoded_to_dict(record)
                    else:
                        # none不读取目标时间；selected仅读取目标时间。没有载荷/DLC副本。
                        frame = RequiredCANFrame(None if time_scope == 'none' else msg.timestamp,
                            frame_id, msg.channel, msg.is_extended_id, msg.is_fd,
                            msg.is_remote_frame, msg.is_error_frame)
                        record = RequiredDecodedFrame(sequence, frame, values)
                        packet_tree = required_to_dict(record)
                    if retained:
                        payload = _encode_fresh_packet(packet_tree)
                        encoded.append(payload)
                        encoded_size += LENGTH.size + len(payload)
                        if time_scope == 'selected':
                            timestamps.append(record.frame.timestamp)
                    msg = values = record = frame = payload = packet_tree = None
                    continue
                phase = 'parse'
                if ((decode_ids is None or projected_fields.get(msg.arbitration_id))
                        and (decode_policy == 'legacy' or not (msg.is_remote_frame or msg.is_error_frame))):
                    active = resolver.fields_for(msg)
                    message = resolver.message_for(msg, active)
                    if message is not None:
                        check_decode_length(msg, message.length, decode_policy)
                    if message is not None or decode_ids is None:
                        parse_calls += 1
                        values = _parse_selected(processor, db, msg, message, duplicate_ids)
                    else:
                        values = {}
                else:
                    values = {}
                phase = 'batch'
                timestamp = msg.timestamp
                if type(timestamp) is not float or not isfinite(timestamp):
                    raise ValueError('原报文timestamp需要有限float秒')
                timestamps.append(timestamp)
                encoded_size += 8
                retained = selected is None or msg.arbitration_id in selected
                if projected_fields is not None and (retained or msg.arbitration_id in decode_ids):
                    # 先保原时间/帧字段错误，再投影解码值；不能让Mapping访问抢先失败。
                    # 所需ID即使本批不保留，仍完整检查需要的值；原始导出额外帧只含空值。
                    frame = worker._frame(msg)
                    values = _project_values(values, projected_fields.get(msg.arbitration_id, ()))
                    record = LegacyDecodedFrame(sequence, frame, values)
                if retained:
                    # all仍逐项检查完整原values；requested使用刚核过的投影记录。
                    if projected_fields is None:
                        record = LegacyDecodedFrame(sequence, worker._frame(msg), values)
                    payload = _encode_fresh_packet(decoded_to_dict(record))
                    encoded.append(payload)
                    encoded_size += LENGTH.size + len(payload)
                elif record is None:
                    # 默认核全部原值；按需跳过解码时只存在空values，原帧检查仍执行。
                    validate_discarded(msg, values, sequence, native_message_type=native_message_type)
                msg = values = record = frame = payload = None
            phase = 'send_batch'
            payload = encode_batch(frames_returned, timestamps, encoded, eof, byte_limit,
                raw_count=raw_count, time_scope=time_scope, input_check=input_check,
                full_check_count=full_checks)
            if envelope_size:
                payload = FILE_HEADER.pack(FILE_MAGIC,input_index) + payload
            connection.send_bytes(payload)
            frames_returned += raw_count
            timestamps = encoded = payload = None
            if eof:
                break
    except BaseException as exc:
        failure = exc
        worker._report_error(connection, exc, phase, request_id)
    finally:
        # 父等待实际退出才能释放资源责任；不窥原generator局部变量来关未知句柄。
        timestamps = encoded = record = frame = msg = values = payload = None
        packet_tree = None
        decode_ids = decode_frame_ids = projected_fields = ready = None
        if iterator is not None:
            try:
                iterator.close()
            except BaseException as cleanup:
                if failure is None:
                    failure = cleanup
                    worker._report_error(connection, cleanup, 'generator_close', request_id)
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
