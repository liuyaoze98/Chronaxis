"""在独立spawn子进程按单次PUT许可调用冻结的原BLF写出链。

输入为有界INIT/PUT/FINISH JSON bytes，输出同次READY、逐帧ACK和完成候选。
INIT才核三份vendor及锁定依赖，独占取得新输出文件，再原样调用一次
build_writer(str(path),'blf')。每PUT完整恢复同一LegacyRawFrame公开字段并
构造can.Message，原writer.on_message_received只调用一次，不读源CAN或DBC。
FINISH仅在原stop成功后发送完成候选；父仍须核真实子退出、句柄及费用收尾。

本模块复用CAN读取协议的有界JSON、错误摘要和vendor加载函数，不修改或继承其read
生命周期。失败保有限远端事实并非零退出，finally只对尚未尝试stop的writer调用
一次原stop；失败的stop不被静默重试或改写。实际子退出回收未公开旧FD，不能
据父RAM账本声称旧库、压缩缓存或整进程RSS受限。产物保留，不自动删除失败文件。
"""

# 模块导入不加载CAN库或打开输出；只有有效INIT之后才进入原样vendor。
from importlib import metadata
import os
from pathlib import Path
import platform
from .records import PROFILE_ID, frame_from_dict
from .worker import VENDOR_SHA256, _exact, _load_vendor, _receive, _report_error, _send


WRITE_DEPENDENCIES = {'python-can': '4.6.1', 'cantools': '39.4.3', 'natsort': '8.4.0'}


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
    # resolve先于保护检查，不能经目录链接把新产物写进历史快照。
    if path.suffix.lower() != '.blf' or any(part.casefold() == 'refprojects' for part in path.parts):
        raise ValueError('原CAN写出仅支持RefProjects之外的新BLF')
    if path.exists():
        raise FileExistsError(path)
    if not path.parent.is_dir():
        raise FileNotFoundError(path.parent)
    return path


def _message(can, frame):
    """把全部原公开写出字段交给原can.Message构造，不添加check或归一化参数。

    参数: can为原vendor实际导入的模块；frame为已校验LegacyRawFrame。
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
    """作为真实spawn目标，按INIT/单PUT/FINISH顺序调用唯一原writer。

    参数: connection为父传来的实际duplex端点。返回: 原stop成功并发送候选后None。
    异常: 原错误尽力发送有限ERROR，最终SystemExit(1)；管道清理也不能伪成正常退出。
    副作用: 独占创建一个新BLF、一次build_writer、每许可一次on_message_received，
        至多一次stop；不读取输入CAN/DBC，不调parse或为ACK额外写帧。
    """
    writer = claim = failure = request_id = None
    phase, frame_count, stop_attempted = 'init', 0, False
    try:
        path = _output(_receive(connection))
        phase = 'vendor'
        _, processor, hashes = _load_vendor()
        versions = {'python': platform.python_version(),
            **{name: metadata.version(name) for name in WRITE_DEPENDENCIES}}
        if any(versions[name] != expected for name, expected in WRITE_DEPENDENCIES.items()):
            raise ValueError('原CAN writer依赖不符合已验证profile')
        # xb原子拒绝已有文件；原build_writer只重开本child刚取得的自有空产物。
        phase = 'claim'
        claim = path.open('xb')
        claim.close()
        claim = None
        phase = 'build_writer'
        writer, actual_path = processor.build_writer(str(path), 'blf')
        if actual_path != str(path):
            raise ValueError('原build_writer返回的路径与本次目标不一致')
        _send(connection, {'op': 'ready', 'version': 1, 'profile': PROFILE_ID,
            'worker_pid': os.getpid(), 'dependency_versions': versions, 'vendor_sha256': hashes})
        # 仅收到一条PUT后写一帧；下一许可前不保留当前消息或构造额外帧。
        while True:
            phase, request_id = 'control', None
            packet = _receive(connection)
            if packet.get('op') == 'finish':
                _exact(packet, ('op', 'frame_count'))
                if type(packet['frame_count']) is not int or packet['frame_count'] != frame_count:
                    raise ValueError('FINISH帧数与本次原writer确认数量不符')
                phase, stop_attempted = 'stop', True
                writer.stop()
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
            message = _message(processor.can, frame)
            phase = 'write'
            writer.on_message_received(message)
            frame_count += 1
            _send(connection, {'op': 'ack', 'request_id': request_id, 'frame_count': frame_count})
            frame = message = None
    except BaseException as exc:
        failure = exc
        _report_error(connection, exc, phase, request_id)
    finally:
        # 失败或父提前断管只结束已有writer；不重发PUT，不重试已经失败的原stop。
        if writer is not None and not stop_attempted:
            try:
                stop_attempted = True
                writer.stop()
            except BaseException as cleanup:
                if failure is None:
                    failure = cleanup
                    _report_error(connection, cleanup, 'stop', request_id)
                else:
                    failure.add_note('原writer.stop附加失败: ' + type(cleanup).__name__)
        for resource, label in ((claim, '新文件声明句柄'), (connection, '子连接')):
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
