"""在独立进程中逐次请求旧CAN函数，确认退出后才交付完整EOF。

输入是冻结的单BLF请求和借用ResourceBudget，输出原函数已经返回的
LegacyDecodedFrame。构造不启动进程；start只初始化旧DBC和公开元数据；
每次next只授权一个PULL，不预取下一帧，也不改变原读取或解码参数。
原reader没有公开的可靠关闭接口，因此本层关闭自己的管道并等待或终止
自己启动的进程。只有确认退出才释放进程责任；这没有修复旧reader。

固定状态、IPC最大包、元数据和当前记录分别计入新层保守RAM费用。
旧DBC、旧reader和解释器的整进程RSS未测，不能由本账本上限代替。
本层不写源文件、不导出BLF、不关闭借用账本或其他read。失败时保留原父
异常；清理仍失败时以can_process_read_cleanup_owner暴露同一真实owner。
跨进程只能保留远端异常事实，不能承诺远端异常对象与父对象相同。
"""

# 进程和传输对象仅在start中建立，普通导入不加载CAN库或DBC。
from collections.abc import Mapping
import multiprocessing
import platform
from sys import getsizeof
from types import MappingProxyType

# 原样数据模型和有界JSON协议由worker与父进程共用，不接任意pickle对象。
from .records import (MAX_WIRE_BYTES, LegacyCANRequest, decode_packet,
                      decoded_from_dict, encode_packet, field_from_dict, field_to_dict)
from .worker import VENDOR_SHA256, worker_main
from ..results.budget import ResourceBudget
from ..results.errors import AnalysisError, ResultClosedError
from ..results.spool import _cleanup_owner, _release_owned_ram, _reserve_owned_ram
from ..sources.protocol import SourceReadError


def _wire_metadata_bytes(value):
    """估算已通过有界wire检查的JSON树，复制冻结前先预约保留费用。

    参数: value为decode_packet得到的dict/list/原生标量。返回: 基础字节估算。
    异常: TypeError为内部未校验类型；不借用只接受冻结tuple的历史元数据估算器。
    """
    # wire的深度与总字节已校验；按原容器计数即可，不先复制成冻结树。
    if type(value) is dict:
        return getsizeof(value) + sum(128 + _wire_metadata_bytes(key)
            + _wire_metadata_bytes(item) for key, item in value.items())
    if type(value) is list:
        return getsizeof(value) + sum(32 + _wire_metadata_bytes(item) for item in value)
    if value is None or type(value) in (str, int, bool, float):
        return getsizeof(value) + 64
    raise TypeError('旧CAN元数据只接受已校验JSON树')


def _freeze(value):
    """复制一份已经通过JSON边界检查的元数据，拒绝后续原地修改。

    参数: value为有界协议JSON树。返回: 只读映射、tuple或原标量。
    异常: 原分配错误传播；本函数不读取文件或保留进程对象。
    """
    # 映射和数组逐层冻结，外部消费者不能修改下一次读取的合同。
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


class RemoteLegacyError(RuntimeError):
    """保存远端错误的有限事实，明确区别于父进程中的原异常对象。"""

    def __init__(self, facts, phase, request_id):
        """将有界错误包保存为供SourceReadError引用的cause。

        参数: facts为错误字段映射；phase和request_id为原协议位置。
        返回: 新远端事实异常。异常: 原分配/格式错误，不执行清理。
        """
        # 不动态import远端异常类型，也不根据类型名执行任意代码。
        self.facts = _freeze(facts)
        self.phase, self.request_id = phase, request_id
        module = facts.get('module', 'unknown')
        error_type = facts.get('type', 'unknown')
        message = facts.get('message', '')
        super().__init__(f'旧CAN子进程{phase}失败: {module}.{error_type}: {message}')


class LegacyCANProcessRead:
    """持有一次读取的真实进程、两端连接及各自费用，不与其他read共享。

    _waiting表示已有一个发送尝试尚未取得完整回应，禁止叠加许可。
    _process_stopped只在实际确认退出后置真；关闭失败保留真实对象。
    finished仅表示真实协议EOF、正常退出和本owner关闭均成功。
    """

    def __init__(self, request, budget, *, _worker_target=None):
        """保存请求并预约固定状态，不启动进程或访问DBC。

        参数: request为LegacyCANRequest；budget为借用ResourceBudget；
            _worker_target仅为隔离协议测试的私有spawn目标，生产使用worker_main。
        返回: 尚未启动的独立read。异常: 配置/预算/分配错误；清理持续失败
            在原异常上提供can_process_read_cleanup_owner，不补共享余额差。
        """
        # 限定初始化包的结构规模，超出当前声明能力时明确拒绝。
        if not isinstance(request, LegacyCANRequest) or not isinstance(budget, ResourceBudget):
            raise TypeError('旧CAN读取需要LegacyCANRequest和ResourceBudget')
        if len(request.fields) > 256:
            raise ValueError('当前单CAN来源最多声明256个字段，且初始化包不能超过64KiB')
        # 第一次预算回调前建立全部真实责任槽，覆盖未返回构造的取消。
        self._budget, self._request = budget, request
        self._worker_target = worker_main if _worker_target is None else _worker_target
        self._connection = self._child_connection = self._process = None
        self._worker_pid = self._exit_code = None
        self._process_stopped = self._waiting = self._started = False
        self._closed = self._closing = self._failed = self._finished = False
        self._eof_received = False
        self._metadata = self._current = self._pending_reply = None
        self._fixed_cost = self._pipe_cost = self._process_cost = 0
        self._wire_cost = self._metadata_cost = self._current_cost = self._held_cost = 0
        self._pulls_issued = self._items_returned = self._items_accepted = 0
        try:
            # 有限初始化字段/路径引用和序列化临时结构均由这一固定预约覆盖。
            _reserve_owned_ram(self, 1048576, '_fixed_cost')
        except BaseException as exc:
            self._failed = True
            _cleanup_owner(self, exc, 'can_process_read_cleanup_owner', '旧CAN进程read构造')
            raise

    @property
    def closed(self):
        """返回全部真实责任及费用是否已结束。

        参数: 无。返回: bool。异常: 无，不触碰已关闭Process属性。
        """
        return self._closed

    @property
    def finished(self):
        """返回本次真实协议EOF是否已完整交付。

        参数: 无。返回: bool；提前close或失败永远不伪装EOF。异常: 无。
        """
        return self._finished

    @property
    def worker_pid(self):
        """返回实际启动过的PID，进程对象关闭后仍可用于验证。

        参数: 无。返回: int或None。异常: 无，不重新启动进程。
        """
        return self._worker_pid

    @property
    def counters(self):
        """区分许可发送尝试、已接收ITEM和实际交付记录的有限计数。

        参数: 无。返回: 独立dict；发送中取消时issued是已授予序号的上界，
            不等于已被子进程接收或完成。异常: 原小字典分配错误。
        """
        return {'pulls_issued': self._pulls_issued, 'items_returned': self._items_returned,
                'items_accepted': self._items_accepted}

    @property
    def metadata(self):
        """读取已完成INIT的同次DBC公开元数据，不隐式启动。

        参数: 无。返回: 冻结JSON映射，借用至close；长期保留须由消费者计费。
        异常: ResultClosedError为关闭中/已关闭，RuntimeError为尚未READY。
        """
        self._require_open()
        if self._metadata is None:
            raise RuntimeError('start完成前没有旧CAN运行元数据')
        return self._metadata

    def _require_open(self):
        """阻止失败或半关闭对象再次授权读取。

        参数: 无。返回: None。异常: ResultClosedError为已关/正在关；
            SourceReadError为失败后继续推进；close仍可重试。
        """
        if self._closed or self._closing:
            raise ResultClosedError('旧CAN进程read已关闭或正在关闭')
        if self._failed:
            raise SourceReadError('失败的旧CAN进程read只允许关闭')

    def _fail(self, exc, stage):
        """以原父错误为主关闭实际owner，必要时包装来源位置。

        参数: exc为原错误；stage为有限业务位置。返回: 不返回。
        异常: 父KI/SystemExit、预算及来源错误原对象传播；其他错误作为
            SourceReadError的cause，清理副错只附note/真实恢复owner。
        """
        self._failed = True
        # 先确定对外原错，再把清理证据附在调用者真正会接收到的异常上。
        if isinstance(exc, (KeyboardInterrupt, SystemExit, AnalysisError, SourceReadError)):
            failure = exc
        else:
            failure = SourceReadError(f'旧CAN进程{stage}失败: {exc}')
            failure.__cause__ = exc
        _cleanup_owner(self, failure, 'can_process_read_cleanup_owner', '旧CAN进程read')
        if failure is exc:
            raise failure
        raise failure from exc

    def start(self):
        """实际启动隔离进程并取得READY，不授权任何消息读取。

        参数: 无。返回: self，重复成功调用不重启/重载DBC。
        异常: 启动、协议、远端或预算错误；父取消保原对象和关闭责任。
        """
        self._require_open()
        if self._started:
            return self
        try:
            # 两进程的有界wire和解码临时容器预先计费；旧DBC/RSS另列限制。
            _reserve_owned_ram(self, 128 * MAX_WIRE_BYTES, '_wire_cost')
            _reserve_owned_ram(self, 65536, '_pipe_cost')
            context = multiprocessing.get_context('spawn')
            self._connection, self._child_connection = context.Pipe(duplex=True)
            _reserve_owned_ram(self, 65536, '_process_cost')
            self._process = context.Process(target=self._worker_target,
                args=(self._child_connection,), name='chronaxis-legacy-can')
            try:
                # Process先存真实槽；start成功后取消仍能从同owner回收PID。
                self._process.start()
            finally:
                self._worker_pid = self._process.pid
            self._close_connection('_child_connection')
            packet = {'op': 'init', 'version': 1, 'path': str(self._request.input_path),
                      'dbc_path': str(self._request.dbc_path),
                      'fields': [field_to_dict(field) for field in self._request.fields]}
            ready = self._exchange(packet)
            self._check_ready(ready)
            # 复制冻结元数据前预约实际保留量，wire预约仍覆盖旧解码包。
            _reserve_owned_ram(self, 4096 + 16 * _wire_metadata_bytes(ready), '_metadata_cost')
            self._metadata = _freeze(ready)
            self._pending_reply = None
            self._started = True
            return self
        except BaseException as exc:
            self._fail(exc, '初始化')

    def _check_ready(self, packet):
        """核INIT回应来自同一真实PID和同一字段请求，不猜元数据。

        参数: packet为有界READY dict。返回: None。
        异常: SourceReadError为profile/版本/PID/字段位置不符。
        """
        if (set(packet) != {'op', 'version', 'profile', 'worker_pid', 'fields',
                           'dependency_versions', 'vendor_sha256'}
                or packet.get('op') != 'ready' or type(packet.get('version')) is not int or packet.get('version') != 1
                or packet.get('profile') != self._request.profile
                or type(packet.get('worker_pid')) is not int
                or packet.get('worker_pid') != self._worker_pid):
            raise SourceReadError('旧CAN READY身份、版本或实际PID不符')
        self._check_ready_metadata(packet)

    def _check_ready_metadata(self, packet, *, cycle_fields=(), metadata_fields=()):
        """核两种READY共有的字段定位、单位、依赖与原vendor，不改协议头。

        参数: packet已由对应读取入口核过完整键集、版本、profile和真实PID；
            cycle_fields仅由确认了周期请求的新版批读取器传入，默认不允许cycle_ns；metadata_fields仅增加有限候选声明。
        返回: None。异常: 原SourceReadError；检查顺序和错误文本沿用逐条入口。
        默认v1和显式按需v2分别检查各自头部，不能伪造v1包绕过策略核对。
        """
        expected_fields = tuple(dict.fromkeys((*self._request.fields,*cycle_fields,*metadata_fields)))
        fields = packet.get('fields')
        if not isinstance(fields, list) or len(fields) != len(expected_fields):
            raise SourceReadError('旧CAN READY字段数量不符')
        for actual, expected in zip(fields, expected_fields):
            if (not isinstance(actual, dict)
                    or set(actual) - ({'cycle_ns'} if expected in cycle_fields else set()) - {'dbc_frames'} not in
                       ({'locator', 'unit'}, {'locator', 'unit', 'frame_format_compatibility'})
                    or actual['unit'] is not None and type(actual['unit']) is not str):
                raise SourceReadError('旧CAN READY没有对应原请求的字段定位')
            if expected in cycle_fields and (type(actual.get('cycle_ns')) is not int
                    or not 0 < actual['cycle_ns'] <= (1 << 63)-1):
                raise SourceReadError('DBC周期元数据缺失或不是正int64纳秒')
            # dict相等会把False与0混同；先按原生int/bool合同重建，再比较定位。
            try:
                locator = field_from_dict(actual['locator'])
            except (TypeError, ValueError) as exc:
                raise SourceReadError('旧CAN READY字段定位类型非法') from exc
            if locator != expected:
                raise SourceReadError('旧CAN READY没有对应原请求的字段定位')
            needs_candidates = locator.is_extended is None or locator.is_fd is None
            if ('dbc_frames' in actual) != needs_candidates:
                raise SourceReadError('旧CAN READY候选帧型与省略参数声明不符')
            if 'dbc_frames' in actual:
                pairs = actual['dbc_frames']
                if (type(pairs) is not list or not 1 <= len(pairs) <= 4
                        or any(type(pair) is not list or len(pair) != 2
                               or any(type(flag) is not bool for flag in pair) for pair in pairs)):
                    raise SourceReadError('旧CAN READY候选帧型非法')
                if len({tuple(pair) for pair in pairs}) != len(pairs) or any(
                        locator.is_extended is not None and pair[0] != locator.is_extended
                        or locator.is_fd is True and pair[1] is not True for pair in pairs):
                    raise SourceReadError('旧CAN READY候选帧型与显式参数冲突或重复')
            if 'frame_format_compatibility' in actual:
                # 只承认固定单向提示，不将0/1当bool，也不接受其他兼容或额外字段。
                notice = actual['frame_format_compatibility']
                if (type(notice) is not dict
                        or set(notice) != {'code', 'dbc_is_fd', 'requested_is_fd'}
                        or type(notice['code']) is not str or notice['code'] != 'dbc_fd_classic_selector'
                        or notice['dbc_is_fd'] is not True or notice['requested_is_fd'] is not False
                        or locator.is_fd is not False):
                    raise SourceReadError('旧CAN READY帧型兼容提示非法或与原定位不同')
        # 此profile仅接受声明的依赖版本与读取链；不能静默接受另一条旧链。
        expected_versions = {'python': platform.python_version(), 'python-can': '4.6.1',
                             'cantools': '39.4.3', 'natsort': '8.4.0'}
        if packet['dependency_versions'] != expected_versions:
            raise SourceReadError('旧CAN READY依赖版本不符合已验证profile')
        if packet['vendor_sha256'] != VENDOR_SHA256:
            raise SourceReadError('旧CAN READY原样vendor哈希不符')

    def _exchange(self, packet):
        """完成一个有界请求/回应；STATUS/ACK也不隐含PULL许可。

        参数: packet为协议dict。返回: 有界回应dict。
        异常: 原父取消/管道错误、SourceReadError或明确远端cause。
        边界: 最多一项在途，父每50ms回到Python检查取消；本方法发送后立即等待。
        """
        try:
            self._send_request(packet)
            return self._receive_response(packet)
        finally:
            packet = None

    def _send_request(self, packet):
        """发送唯一在途许可；发送中断时仍保留实际连接和未确认责任。

        参数: packet为调用方已经为相应工作空间付款的协议dict。
        返回: None。异常: 原编码/发送/取消错误；失败不可按未发送重试。
        边界: 原逐条入口立即接收；批次入口可在消费当前批时保留这一项在途请求。
        """
        payload = None
        try:
            if self._connection is None or self._waiting:
                raise SourceReadError('旧CAN连接不可用或已有一个在途请求')
            payload = encode_packet(packet)
            self._waiting = True
            self._connection.send_bytes(payload)
        finally:
            packet = payload = None

    def _receive_response(self, packet):
        """接收先前发送的许可，并严格核对远端错误事实与请求身份。

        参数: packet为同一在途许可，不再次发送。返回: 有界回应dict。
        异常: 原连接/格式/取消错误，或带RemoteLegacyError cause的来源错误。
        边界: 必须已有一个在途请求；没有真实协议EOF的退出仍是错误。
        """
        reply = facts = remote = None
        try:
            if self._connection is None or not self._waiting:
                raise SourceReadError('旧CAN连接没有对应的在途请求')
            # poll不授予读取许可；子进程意外退出也不能当成真实EOF。
            while not self._connection.poll(0.05):
                if self._process is not None and not self._process.is_alive():
                    raise SourceReadError(f'旧CAN进程未交付完整协议回应便退出: {self._process.exitcode}')
            reply = self._receive_reply()
            self._waiting = False
            if reply.get('op') == 'error':
                facts = reply.get('error')
                if (set(reply) != {'op', 'request_id', 'phase', 'error'}
                        or type(reply.get('phase')) is not str
                        or reply.get('request_id') is not None and type(reply.get('request_id')) is not int
                        or not isinstance(facts, dict)
                        or set(facts) != {'module', 'type', 'message', 'traceback', 'notes'}
                        or any(type(facts[key]) is not str for key in ('module', 'type', 'message', 'traceback'))
                        or type(facts['notes']) is not list
                        or any(type(note) is not str for note in facts['notes'])):
                    raise SourceReadError('旧CAN远端错误包缺少明确事实')
                if reply['request_id'] != packet.get('request_id'):
                    raise SourceReadError('旧CAN远端错误不属于当前请求')
                remote = RemoteLegacyError(facts, reply.get('phase'), reply.get('request_id'))
                raise SourceReadError(str(remote)) from remote
            return reply
        finally:
            # 原错误可留在调用方；已结束调用的临时引用不继续占有整批对象。
            packet = reply = facts = remote = None

    def _receive_reply(self):
        """读取本协议的一条严格JSON回应，供批次子类替换物理数据包边界。

        参数: 无，使用本owner的实际Connection。
        返回: 已校验的回应dict。异常: 原管道、长度、JSON或取消错误。
        边界: 原逐条入口仍只接收64KiB；子类不能绕过共享接收流程的在途及远端错误检查。
        """
        self._pending_reply = self._connection.recv_bytes(MAX_WIRE_BYTES)
        return decode_packet(self._pending_reply)

    def __iter__(self):
        """返回本次独立read，不因取得迭代器就启动或读取。

        参数: 无。返回: self。异常: 原错误只在实际next/start时报告。
        """
        return self

    def __next__(self):
        """只授权并返回一帧，真实完整EOF之后才StopIteration。

        参数: 无。返回: LegacyDecodedFrame；调用者保留引用须另计费。
        异常: StopIteration为已确认EOF；源/预算/协议错误或父原取消。
        """
        if self._finished:
            raise StopIteration
        self._require_open()
        try:
            self.start()
            # 上一记录停止由本read持有后才归还其费用，失败不会继续发PULL。
            self._current = None
            _release_owned_ram(self, self._current_cost, '_current_cost')
            self._pending_reply = None
            request_id = self._items_accepted
            self._pulls_issued += 1
            reply = self._exchange({'op': 'pull', 'request_id': request_id})
            if type(reply.get('request_id')) is not int or reply.get('request_id') != request_id:
                raise SourceReadError('旧CAN回应不是本次唯一许可序号')
            if reply.get('op') == 'eof':
                if (set(reply) != {'op', 'request_id', 'frame_count'}
                        or type(reply.get('frame_count')) is not int
                        or reply.get('frame_count') != self._items_accepted):
                    raise SourceReadError('旧CAN EOF原帧计数不符')
                self._eof_received = True
                self.close()
                if self._exit_code != 0:
                    raise SourceReadError('旧CAN虽然发EOF，但没有正常退出')
                self._finished = True
            elif reply.get('op') == 'item':
                if set(reply) != {'op', 'request_id', 'record'}:
                    raise SourceReadError('旧CAN ITEM字段缺失或多余')
                self._items_returned += 1
                raw = reply.get('record')
                _reserve_owned_ram(self, 4096 + 16 * _wire_metadata_bytes(raw), '_current_cost')
                self._current = decoded_from_dict(raw)
                if self._current.sequence != request_id:
                    raise SourceReadError('旧CAN原yield序号不连续，禁止重排或补号')
                self._items_accepted += 1
                self._pending_reply = None
                return self._current
            else:
                raise SourceReadError('旧CAN PULL必须得到ITEM或真实EOF')
        except BaseException as exc:
            self._fail(exc, '逐帧读取')
        # 正常StopIteration不进入失败清理，已关闭read也能重复返回EOF。
        raise StopIteration

    def _close_connection(self, slot):
        """关闭一个真实自有连接，成功后取消也不丢失其实际关闭事实。

        参数: slot为本owner连接字段。返回: None。
        异常: 原close错误；未关闭对象仍在同槽，费用稍后单独归还。
        """
        connection = getattr(self, slot)
        if connection is None:
            return
        try:
            connection.close()
        finally:
            if connection.closed:
                setattr(self, slot, None)

    def _close_process(self):
        """确认自己启动的进程退出后关闭其实际句柄，不动其他read。

        参数: 无。返回: None，实际exitcode保留供EOF判断。
        异常: join/terminate/kill/close错误保原process和停止确认状态以便重试。
        边界: 三次显式join最多约6秒；Windows kill仍是TerminateProcess，
            必须实际取得exitcode，不能把终止请求成功当作进程已经退出。
        """
        process = self._process
        if process is None:
            return
        if not self._process_stopped:
            # start前失败没有PID，仍须关闭Process自身已经建立的描述。
            if process.pid is not None:
                process.join(timeout=0.5)
                if process.exitcode is None:
                    process.terminate()
                    process.join(timeout=0.5)
                if process.exitcode is None:
                    process.kill()
                    # Windows终止后的OS清理可能晚于0.5秒；有限等待真实退出信号。
                    process.join(timeout=5.0)
                exit_code = process.exitcode
                if exit_code is None:
                    failure = SourceReadError('尚未确认旧CAN子进程退出，不能结束关闭责任')
                    failure.can_process_exit_state = {'pid': self._worker_pid,
                        'exit_code': None, 'join_wait_limits_seconds': (0.5, 0.5, 5.0)}
                    raise failure
                self._exit_code = exit_code
            self._process_stopped = True
        # 此确认先于close，覆盖真实close后取消时已关闭Process属性不可再读的情况。
        process.close()
        self._process = None

    def _release_closed_state(self):
        """实际连接和进程全部关闭后清状态、逐槽退费，供批次子类补充责任。

        参数: 无；调用方必须已完成本owner实际资源关闭。返回: None。
        异常: 原预算回调错误；费用槽保留实际入账事实，同一close可继续恢复。
        """
        self._metadata = self._current = self._pending_reply = self._request = None
        self._worker_target = None
        self._waiting = False
        for slot in ('_current_cost', '_metadata_cost', '_wire_cost', '_pipe_cost', '_process_cost', '_fixed_cost'):
            _release_owned_ram(self, getattr(self, slot), slot)

    def close(self):
        """停止授予许可，关闭自有IPC/进程，最后归还各自费用。

        参数: 无。返回: None，完成后重复调用幂等。
        异常: 实际关闭或预算回调错误；对象仍可同owner重试。
        边界: 关管道令等待命令的child退出；在途旧IO不响应时有限等待后终止，
            不为关闭继续next，也不把强制退出当正常分析完成。
        """
        if self._closed:
            return
        self._closing = True
        try:
            # 任一真实资源未关时即保留父责任，不先释放其内存描述或借用余额。
            self._close_connection('_child_connection')
            self._close_connection('_connection')
            self._close_process()
            # 每笔实际申请有独立槽，释放后取消由既有helper确认，不重复抵销别人的费用。
            self._release_closed_state()
            self._closed = True
        except BaseException as exc:
            # 直接close的调用者也能从同一异常找到真实责任，不制造替代owner。
            exc.can_process_read_cleanup_owner = self
            raise
