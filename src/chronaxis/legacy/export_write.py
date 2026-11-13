"""在独立进程把原始帧交给共用BLF写入器，真实收尾后才确认完成。

LegacyCANProcessWrite接收共享ResourceBudget和新输出路径，构造只计有限状态、
核路径而不spawn或打开输出。start加载依赖并由共用BLFWrite取得文件和写入器；每次
write只发一个有界PUT，收到同序ACK才承认该帧，FINISH没有额外帧写入许可。
finish须BLFWrite完成收尾、实际exitcode0、所有Pipe/Process及自有RAM清完，并核输出
stat不超过本writer直接预留，才公开finished。提前close、失败或取消不能伪完成。

进程/管道/wire/READY/当前帧分别先付并记真实槽；释放前后取消可重试，最高
can_process_write_cleanup_owner始终指向同一实际owner。磁盘在start前保守预留
65536 bytes、每PUT前4096 bytes，累计保留且不倒扣；不凭共享余额差接管费用。
原BLF压缩、库内部缓存及整进程RSS未测，也不承诺文件与源BLF字节一致。
这里只写控制器新工作根下的新文件，不读取来源CAN或DBC。
"""

# 仅导入标准库和既有轻量协议；CAN依赖留在独立spawn子内。
import multiprocessing
from pathlib import Path
from .export_worker import worker_main
from ..can_dependencies import runtime_dependency_versions
from .process_read import RemoteLegacyError, _freeze, _wire_metadata_bytes
from .records import MAX_WIRE_BYTES, PROFILE_ID, LegacyRawFrame, decode_packet, encode_packet, frame_to_dict
from ..results.budget import ResourceBudget
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner, _release_owned_ram, _reserve_owned_ram


class LegacyCANWriteError(AnalysisError):
    """报告新外部writer协议或原子进程失败；远端原错仅作为明确事实cause。"""


class LegacyCANProcessWrite:
    """拥有一个真实writer子进程与独立费用，借用账本但不关闭其他owner。

    _waiting阻止第二个在途控制包；_process_stopped只由实际exitcode确认。
    _closed表示自有责任结束，_finished还须本次FINISH及输出大小验证成功。
    输出路径和累计spool事实在close后保留，READY借引用在close时解除。
    """

    def __init__(self, budget, output_path):
        """预约固定协调状态并检查新路径，不启动进程或创建目标文件。

        参数: budget为借用ResourceBudget；output_path为控制器已有新工作根下的
            str/Path目标，须为.blf后缀，不能已存在。
        返回: 未启动的独立writer。异常: 类型、路径或预算原错；未返回构造的持续
            清理失败附can_process_write_cleanup_owner，同对象恢复后close。
        """
        if not isinstance(budget, ResourceBudget) or not isinstance(output_path, (str, Path)):
            raise TypeError('原CAN写出需要ResourceBudget和新输出路径')
        # 所有真实资源和交易槽先安装；后续任何预算取消都有本owner可达责任。
        self._budget, self._output_path = budget, None
        self._connection = self._child_connection = self._process = None
        self._worker_pid = self._exit_code = self._metadata = self._pending_reply = self._frame = None
        self._fixed_cost = self._wire_cost = self._pipe_cost = self._process_cost = 0
        self._metadata_cost = self._frame_cost = self._held_cost = self._spool_bytes = 0
        self._puts_issued = self._acks_received = self._frames_written = 0
        self._actual_bytes = None
        self._process_stopped = self._waiting = self._started = self._finish_received = False
        self._closed = self._closing = self._failed = self._finished = False
        try:
            _reserve_owned_ram(self, 1048576, '_fixed_cost')
            if len(str(output_path)) > 8192:
                raise ValueError('原CAN输出路径超过本层有限能力')
            self._output_path = Path(output_path).resolve()
            self._check_path()
        except BaseException as exc:
            self._failed = True
            _cleanup_owner(self, exc, 'can_process_write_cleanup_owner', '原CAN writer构造')
            raise

    def _check_path(self):
        """拒绝已有目标及缺少的新工作根，不创建目录或文件。

        参数: 无，使用已保存resolved路径。返回: None。
        异常: ValueError为后缀错误，FileExistsError为已有目标，
            FileNotFoundError为父目录不存在；真正独占创建由child执行。
        """
        path = self._output_path
        if path.suffix.lower() != '.blf':
            raise ValueError('原CAN写出仅支持新的BLF文件')
        if path.exists():
            raise FileExistsError(path)
        if not path.parent.is_dir():
            raise FileNotFoundError(path.parent)

    @property
    def output_path(self):
        """读取实际新目标。参数: 无。返回: resolved Path或构造前失败时None。异常: 无。"""
        return self._output_path

    @property
    def closed(self):
        """读取全部自有责任关闭状态。参数: 无。返回: bool。异常: 无。"""
        return self._closed

    @property
    def finished(self):
        """读取完整FINISH事实。参数: 无。返回: bool，失败/提前close为False。异常: 无。"""
        return self._finished

    @property
    def failed(self):
        """读取失败诊断状态。参数: 无。返回: bool。异常: 无。"""
        return self._failed

    @property
    def worker_pid(self):
        """读取本次真实启动PID。参数: 无。返回: int或None，关闭后保留。异常: 无。"""
        return self._worker_pid

    @property
    def spool_bytes(self):
        """读取本writer直接累计磁盘预留。参数: 无。返回: int bytes，不倒扣。异常: 无。"""
        return self._spool_bytes

    @property
    def counters(self):
        """区分PUT尝试、合法ACK和本父确认帧数，不用断管推断写入成功。

        参数: 无。返回: 新dict，取消时puts_issued仅为许可尝试上界。
        异常: 原小容器分配错误；不向child发送额外控制或写入。
        """
        return {'puts_issued': self._puts_issued, 'acks_received': self._acks_received,
            'frames_written': self._frames_written}

    @property
    def metadata(self):
        """借读同次READY事实，不隐式start。参数: 无。返回: 冻结映射，借用至close。
        异常: ResultClosedError为关闭/失败，RuntimeError为尚无实际READY。
        """
        self._require_open()
        if self._metadata is None:
            raise RuntimeError('原CAN writer尚未READY')
        return self._metadata

    def _require_open(self):
        """阻止关闭或失败后继续许可。参数: 无。返回: None。
        异常: ResultClosedError为不可推进；close仍可重复恢复。
        """
        if self._closed or self._closing or self._failed:
            raise ResultClosedError('原CAN writer已关闭、清理中或失败')

    def _reserve_spool(self, amount):
        """逐笔记录本次直接磁盘预留，回调执行后取消也保留真实归属。

        参数: amount为非负int bytes。返回: None。异常: 原配额/取消，文件及累计值不倒扣。
        """
        before = self._budget.spool_bytes
        try:
            self._budget.reserve_spool(amount)
        finally:
            if self._budget.spool_bytes == before + amount:
                self._spool_bytes += amount

    def _fail(self, exc, phase):
        """以实际父错误为主收尾，普通底层错误包装并保cause及最高恢复owner。

        参数: exc为原异常；phase为有限业务位置。返回: 不返回。
        异常: KI/SystemExit/AnalysisError原对象，其余LegacyCANWriteError保原cause；
            两次有限cleanup副错只附note，绝不伪称写出完成。
        """
        self._failed = True
        failure = exc if isinstance(exc, (KeyboardInterrupt, SystemExit, AnalysisError)) else LegacyCANWriteError(
            '原CAN writer' + phase + '失败')
        _cleanup_owner(self, failure, 'can_process_write_cleanup_owner', '原CAN writer')
        if failure is exc:
            raise failure
        raise failure from exc

    def start(self):
        """实际创建独立spawn及原writer，READY不包含任何帧许可。

        参数: 无。返回: self，重复成功调用不重建或重复预留。
        异常: 路径/依赖/管道/协议/配额/预算或父原取消，最高owner按实际槽可恢复。
        """
        self._require_open()
        if self._started:
            return self
        try:
            self._check_path()
            # 磁盘容量在spawn/原build_writer前预留，空BLF也保65536而非事后认领。
            self._reserve_spool(65536)
            _reserve_owned_ram(self, 128 * MAX_WIRE_BYTES, '_wire_cost')
            _reserve_owned_ram(self, 65536, '_pipe_cost')
            context = multiprocessing.get_context('spawn')
            self._connection, self._child_connection = context.Pipe(duplex=True)
            _reserve_owned_ram(self, 65536, '_process_cost')
            self._process = context.Process(target=worker_main, args=(self._child_connection,),
                name='chronaxis-legacy-can-export')
            try:
                self._process.start()
            finally:
                self._worker_pid = self._process.pid
            self._close_connection('_child_connection')
            reply = self._exchange({'op': 'init', 'version': 1, 'profile': PROFILE_ID,
                'path': str(self._output_path)})
            self._check_ready(reply)
            _reserve_owned_ram(self, 4096 + 16 * _wire_metadata_bytes(reply), '_metadata_cost')
            self._metadata = _freeze(reply)
            self._pending_reply = None
            self._started = True
            return self
        except BaseException as exc:
            self._fail(exc, '初始化')

    def _check_ready(self, packet):
        """核同次实际PID及现有依赖，不接受bool伪版本或自称READY。

        参数: packet为decode_packet得到的dict。返回: None。
        异常: LegacyCANWriteError为结构/类型/profile/PID/版本/摘要不符。
        """
        if (set(packet) != {'op', 'version', 'profile', 'worker_pid', 'dependency_versions'}
                or packet.get('op') != 'ready' or type(packet.get('version')) is not int or packet['version'] != 1
                or type(packet.get('profile')) is not str or packet['profile'] != PROFILE_ID
                or type(packet.get('worker_pid')) is not int or packet['worker_pid'] != self._worker_pid
                or packet['dependency_versions'] != runtime_dependency_versions()):
            raise LegacyCANWriteError('原CAN writer READY身份、版本或实际PID不符')

    def _exchange(self, packet):
        """同步交换唯一控制包，禁止第二个在途PUT或把子退出当成ACK。

        参数: packet为有界控制dict。返回: 严格JSON dict。
        异常: 父原取消/管道/编码错误或LegacyCANWriteError；远端失败以明确
            RemoteLegacyError事实为cause，不能声称跨进程保留异常对象身份。
        """
        if self._connection is None or self._waiting:
            raise LegacyCANWriteError('原CAN writer连接不可用或已有在途许可')
        payload = encode_packet(packet)
        self._waiting = True
        self._connection.send_bytes(payload)
        while not self._connection.poll(0.05):
            if self._process is not None and self._process.exitcode is not None:
                raise LegacyCANWriteError('原CAN writer未交付完整回应便退出')
        self._pending_reply = self._connection.recv_bytes(MAX_WIRE_BYTES)
        reply = decode_packet(self._pending_reply)
        self._waiting = False
        if reply.get('op') == 'error':
            facts = reply.get('error')
            if (set(reply) != {'op', 'request_id', 'phase', 'error'}
                    or type(reply.get('phase')) is not str
                    or reply.get('request_id') is not None and type(reply.get('request_id')) is not int
                    or reply.get('request_id') != packet.get('request_id')
                    or type(facts) is not dict or set(facts) != {'module', 'type', 'message', 'traceback', 'notes'}
                    or any(type(facts[key]) is not str for key in ('module', 'type', 'message', 'traceback'))
                    or type(facts['notes']) is not list or any(type(note) is not str for note in facts['notes'])):
                raise LegacyCANWriteError('原CAN writer远端错误包缺少明确事实或请求不符')
            remote = RemoteLegacyError(facts, reply['phase'], reply['request_id'])
            raise LegacyCANWriteError('原CAN writer子进程失败') from remote
        return reply

    def write(self, frame):
        """完整发送一个原始帧并等唯一ACK，不缓存后继或按ID筛帧。

        参数: frame为原生LegacyRawFrame，保全部公开字段及原浮点timestamp。
        返回: None，合法ACK后counters增加；无额外on_message_received。
        异常: TypeError为非原模型；原预算/磁盘/取消或writer/协议失败，之后只能close。
        """
        self._require_open()
        if type(frame) is not LegacyRawFrame:
            raise TypeError('原CAN writer.write需要LegacyRawFrame')
        if frame.is_rx is None:
            raise ValueError('BLF写出需要收发方向is_rx')
        try:
            self.start()
            # 当前记录、hex和wire容器均在复制前付款；只有本owner持有时才保留该槽。
            _reserve_owned_ram(self, 4259840, '_frame_cost')
            self._frame = frame
            self._reserve_spool(4096)
            request_id = self._frames_written
            self._puts_issued += 1
            reply = self._exchange({'op': 'put', 'request_id': request_id, 'frame': frame_to_dict(frame)})
            if (set(reply) != {'op', 'request_id', 'frame_count'} or reply.get('op') != 'ack'
                    or type(reply.get('request_id')) is not int or reply['request_id'] != request_id
                    or type(reply.get('frame_count')) is not int or reply['frame_count'] != request_id + 1):
                raise LegacyCANWriteError('原CAN writer ACK不属于本次唯一PUT')
            self._acks_received += 1
            self._frames_written += 1
            self._frame = self._pending_reply = None
            _release_owned_ram(self, self._frame_cost, '_frame_cost')
        except BaseException as exc:
            self._fail(exc, '逐帧写出')

    def finish(self):
        """完成原stop、真实正常退出及全部费用，再核实际文件未超过预留。

        参数: 无。返回: self，成功后重复调用不重发FINISH或重写文件。
        异常: 原取消/预算/关闭错误，或LegacyCANWriteError为不完整回应、异常退出
            或实际stat超本writer累计预留；任何失败都不置finished。
        """
        if self._finished:
            return self
        self._require_open()
        try:
            self.start()
            reply = self._exchange({'op': 'finish', 'frame_count': self._frames_written})
            if (set(reply) != {'op', 'frame_count'} or reply.get('op') != 'finished'
                    or type(reply.get('frame_count')) is not int or reply['frame_count'] != self._frames_written):
                raise LegacyCANWriteError('原CAN writer FINISH未确认全部原帧')
            self._finish_received = True
            self.close()
            if self._exit_code != 0:
                raise LegacyCANWriteError('原CAN writer虽发完成候选但未正常退出')
            self._actual_bytes = self._output_path.stat().st_size
            if self._actual_bytes > self._spool_bytes:
                raise LegacyCANWriteError('原BLF实际大小超过本writer保守磁盘预留')
            self._finished = True
            return self
        except BaseException as exc:
            self._fail(exc, '封口')

    def _close_connection(self, slot):
        """实际关闭端点后才撤槽。参数: slot为本owner自有端点名。返回: None。
        异常: 原close/取消；执行后异常也按真实closed确认，不丢未关句柄。
        """
        connection = getattr(self, slot)
        if connection is not None:
            try:
                connection.close()
            finally:
                if connection.closed:
                    setattr(self, slot, None)

    def _close_process(self):
        """有限等待自己实际进程退出再关句柄，绝不以终止请求代替退出证明。

        参数: 无。返回: None。异常: 原join/terminate/kill/close或LegacyCANWriteError；
            未确认时保原进程/费用并附稳定退出诊断。显式join上限为.5/.5/5秒，
            Windows kill仍是TerminateProcess，必须实际exitcode非None。
        """
        process = self._process
        if process is None:
            return
        if not self._process_stopped:
            if process.pid is not None:
                process.join(timeout=.5)
                if process.exitcode is None:
                    process.terminate()
                    process.join(timeout=.5)
                if process.exitcode is None:
                    process.kill()
                    process.join(timeout=5.0)
                code = process.exitcode
                if code is None:
                    failure = LegacyCANWriteError('尚未确认原CAN writer子进程退出')
                    failure.can_process_write_exit_state = {'pid': self._worker_pid, 'exit_code': None,
                        'join_wait_limits_seconds': (.5, .5, 5.0)}
                    raise failure
                self._exit_code = code
            self._process_stopped = True
        # stopped先存，再实际close；close之后取消也不会再次读取已关闭Process属性。
        process.close()
        self._process = None

    def close(self):
        """只关本writer实际IPC/进程和费用，产物与累计磁盘预留保留。

        参数: 无。返回: None，完成后重复调用幂等。
        异常: 原关闭/预算/取消附can_process_write_cleanup_owner，当前槽供持续恢复；
            提前关闭不发送额外帧或FINISH，不设置finished，不修改借用预算的其他费用。
        """
        if self._closed:
            return
        self._closing = True
        try:
            self._close_connection('_child_connection')
            self._close_connection('_connection')
            self._close_process()
            self._metadata = self._frame = self._pending_reply = None
            self._waiting = False
            for slot in ('_frame_cost', '_metadata_cost', '_wire_cost', '_pipe_cost', '_process_cost', '_fixed_cost'):
                _release_owned_ram(self, getattr(self, slot), slot)
            self._closed = True
        except BaseException as exc:
            self._failed = True
            exc.can_process_write_cleanup_owner = self
            raise
