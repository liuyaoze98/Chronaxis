"""在独立spawn进程按PUT许可将原报文写入新的BLF文件。

有效INIT后核现有依赖版本，BLFWrite独占取得文件并把同一句柄交给python-can。
每PUT恢复原公开字段并写一次，不读取来源或DBC；FINISH仅在最终写入成功后确认。
关闭失败保留原错误与实际文件owner，第三方stop不重复执行，父侧仍核实际子退出。"""

# 模块导入不加载CAN库或打开输出；只有有效INIT之后才加载CAN依赖。
import os
from pathlib import Path
from .records import PROFILE_ID, frame_from_dict
from .worker import _exact, _load_can_runtime, _receive, _report_error, _send


from ..can_dependencies import runtime_dependency_versions


def _output(packet):
    """检查唯一INIT及新输出路径，不猜格式或覆盖已有文件。

    参数: packet为已通过严格JSON边界的dict。返回: resolved新BLF Path。
    异常: TypeError/ValueError为字段、版本、profile、后缀或受保护路径；
        FileExistsError为已有目标，FileNotFoundError为尚无控制器工作根。
    副作用: 仅检查文件系统；真正独占创建仍在writer建立之前执行。
    """
    _exact(packet, ('op', 'version', 'profile', 'path'))
    if (packet['op'] != 'init' or type(packet['version']) is not int or packet['version'] != 1
            or type(packet['profile']) is not str or packet['profile'] != PROFILE_ID
            or type(packet['path']) is not str):
        raise ValueError('原CAN写出需要init/version1及固定profile路径')
    path = Path(packet['path']).resolve()
    # 先取得实际目标，再检查后缀和存在性；独占创建仍由写入器执行。
    if path.suffix.lower() != '.blf':
        raise ValueError('原CAN写出仅支持新的BLF文件')
    if path.exists():
        raise FileExistsError(path)
    if not path.parent.is_dir():
        raise FileNotFoundError(path.parent)
    return path


def _message(can, frame):
    """把全部原公开写出字段交给原can.Message构造，不添加check或归一化参数。

    参数: can为本次已加载的python-can模块；frame为已校验LegacyRawFrame。
    返回: 新can.Message，timestamp/data/DLC及全部标志保持原参数。
    异常: 原can.Message构造错误；不以新层猜测修正旧格式限制。
    """
    if frame.is_rx is None:
        raise ValueError('BLF写出需要收发方向is_rx')
    return can.Message(timestamp=frame.timestamp, arbitration_id=frame.arbitration_id,
        is_extended_id=frame.is_extended_id, is_remote_frame=frame.is_remote_frame,
        is_error_frame=frame.is_error_frame, channel=frame.channel, dlc=frame.dlc,
        data=frame.data, is_fd=frame.is_fd, is_rx=frame.is_rx,
        bitrate_switch=frame.bitrate_switch, error_state_indicator=frame.error_state_indicator)


def worker_main(connection):
    """作为真实spawn目标，按INIT/单PUT/FINISH顺序调用唯一BLF writer。

    参数: connection为父传来的实际duplex端点。返回: 原stop成功并发送候选后None。
    异常: 原错误尽力发送有限ERROR，最终SystemExit(1)；管道清理也不能伪成正常退出。
    副作用: 独占创建一个新BLF、一次BLFWrite、每许可一次on_message_received，
        至多一次stop；不读取输入CAN/DBC，不调parse或为ACK额外写帧。
    """
    writer = failure = request_id = None
    phase, frame_count, stop_attempted = 'init', 0, False
    try:
        path = _output(_receive(connection))
        phase = 'dependencies'
        can, cantools = _load_can_runtime()
        versions = runtime_dependency_versions()
        # 同一独占文件对象交给python-can，不关闭后按路径重新打开。
        phase = 'build_writer'
        from ..results.blf_writer import BLFWrite
        writer = BLFWrite(path)
        _send(connection, {'op': 'ready', 'version': 1, 'profile': PROFILE_ID,
            'worker_pid': os.getpid(), 'dependency_versions': versions})
        # 仅收到一条PUT后写一帧；下一许可前不保留当前消息或构造额外帧。
        while True:
            phase, request_id = 'control', None
            packet = _receive(connection)
            if packet.get('op') == 'finish':
                _exact(packet, ('op', 'frame_count'))
                if type(packet['frame_count']) is not int or packet['frame_count'] != frame_count:
                    raise ValueError('FINISH帧数与本次原writer确认数量不符')
                phase, stop_attempted = 'stop', True
                writer.finish()
                writer = None
                _send(connection, {'op': 'finished', 'frame_count': frame_count})
                break
            _exact(packet, ('op', 'request_id', 'frame'))
            candidate = packet['request_id']
            request_id = candidate if type(candidate) is int and candidate >= 0 else None
            if packet['op'] != 'put' or request_id is None or request_id != frame_count:
                raise ValueError('PUT许可必须从0严格连续且为原生int')
            phase = 'frame'
            frame = frame_from_dict(packet['frame'])
            message = _message(can, frame)
            phase = 'write'
            writer.write(message)
            frame_count += 1
            _send(connection, {'op': 'ack', 'request_id': request_id, 'frame_count': frame_count})
            frame = message = None
    except BaseException as exc:
        if writer is None:
            writer=getattr(exc,'blf_write_cleanup_owner',None)
        failure = exc
        _report_error(connection, exc, phase, request_id)
    finally:
        # 失败或父提前断管只结束已有writer；不重发PUT，不重试已经失败的原stop。
        if writer is not None:
            try:
                stop_attempted = True
                writer.close()
            except BaseException as cleanup:
                if failure is None:
                    failure = cleanup
                    _report_error(connection, cleanup, 'stop', request_id)
                else:
                    failure.add_note('原writer.stop附加失败: ' + type(cleanup).__name__)
        for resource, label in ((connection, '子连接'),):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as cleanup:
                    if failure is None:
                        failure = cleanup
                    else:
                        failure.add_note(label + '关闭附加失败: ' + type(cleanup).__name__)
    if failure is not None:
        raise SystemExit(1)
