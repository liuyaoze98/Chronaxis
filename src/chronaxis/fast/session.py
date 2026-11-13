"""一个fast会话的多文件调度和最终累计。

worker只求当前帧贡献；主进程控制统一预算、交付顺序及成功发布前的完整性。
concatenate可暂停可选预读；time_order必要暂存完成后稳定归并。临时目录和
进程均属于本次调用，异常不返回部分结果。内联与batch不经传输协议。
"""
from hashlib import sha256
import heapq
import json
import multiprocessing
from multiprocessing.connection import wait
import os
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter

from ..results.budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..results.errors import BudgetExceededError
from ..dbc_loading import load_dbc_file
from .._control_wire import ControlChannel
from .blocks import RAM, LIMIT, encode, decode, batches
from .compute import _Accumulator, _check_program_spec
from .stream import FileContributions


def effective_spec(spec, process_count=None):
    """取得不修改原声明的执行视图。参数: spec字典，可选正整数覆盖。返回: 新dict。
    异常: 非正原生整数；不接受bool、字符串或浮点数。
    """
    count = spec.get('process_count', 1) if process_count is None else process_count
    if type(count) is not int or count < 1:
        raise ValueError('process_count需要大于等于1的整数，不接受bool')
    return dict(spec, process_count=count)


def _worker_process_limit(process_count: int, file_count: int) -> int:
    """从已验证的进程上限和文件数取得文件工作进程数，不包含主进程。

    参数为正整数。返回至多文件数的工作进程上限；只能并发处理一份时返回0，
    表示在当前进程执行。时间归并的内联暂存不改变这个判定；无输入或输出操作。
    """
    count = min(process_count, file_count)
    return count if count > 1 else 0


def file_specs(spec):
    """展开有限文件声明。参数: 会话spec。返回: 每文件字典列表。异常: 无输入IO。"""
    inputs = spec.get('inputs', [dict(path=spec['path'], offset_ns=spec.get('offset_ns', 0),
                                   asc_options=spec.get('asc_options', {}))])
    common = {key: value for key, value in spec.items() if key not in ('inputs', '_database')}
    return [dict(common, **item) for item in inputs]


def _checked_file_specs(spec, programs_checked):
    """取得实际文件声明，并复用本会话已经检查过的同一组公式。

    参数: 本次独立的spec字典、公共编译器是否已检查顶层公式。
    返回: 文件声明列表；低层inputs覆盖的公式仍检查原文本和指令。
    异常: 非法公式或声明错误；不因顶层已编译就放行另一组覆盖值。
    """
    original = spec['metrics']
    prepared = original if programs_checked else [_check_program_spec(item) for item in original]
    # 缓存只活到准备结束，保留源对象以避免身份复用，不跨会话或按文本猜等价。
    checked = {id(original): (original, prepared), id(prepared): (prepared, prepared)}
    spec['metrics'] = prepared
    specs = file_specs(spec)
    for item in specs:
        actual = item['metrics']
        cached = checked.get(id(actual))
        if cached is None or cached[0] is not actual:
            cached = (actual, [_check_program_spec(metric) for metric in actual])
            checked[id(actual)] = cached
        item['metrics'] = cached[1]
    return specs


class SessionAccumulator:
    """只有主会话持有的标量累计器。计数、目标缺失和帧身份按计算项分别核验。"""

    def __init__(self, spec):
        """准备纯累计状态。参数: 已核验声明。返回: 新对象。异常: 名称或单位字段缺失。"""
        self.metrics = [_Accumulator(item) for item in spec['metrics']]
        self.raw = 0
        self.targets = [0] * len(self.metrics)
        self.valid = [0] * len(self.metrics)
        self.selected = [0] * len(self.metrics)
        self.kinds = [0] * len(self.metrics)
        self.compatible = set()
        self.profile = spec.get('_profile', False)
        self.accumulate_seconds = 0.0

    def consume(self, record):
        """按输入顺序逐项相加。参数: 一帧贡献。返回: None。异常: 累计溢出。"""
        started = perf_counter() if self.profile else 0
        for index, value, keep in record[2]:
            self.metrics[index].add(value, keep)
        if self.profile:
            self.accumulate_seconds += perf_counter() - started

    def finish_file(self, facts):
        """合并已关闭文件的事实。参数: 文件summary。返回: None。异常: 计数或身份非法。"""
        if type(facts['raw']) is not int or facts['raw'] < 0:
            raise ValueError('文件原始记录计数非法')
        self.raw += facts['raw']
        for field in ('targets', 'valid', 'selected', 'kinds'):
            values = facts[field]
            if len(values) != len(self.metrics) or any(type(v) is not int or v < 0 for v in values):
                raise ValueError('文件计算项计数非法')
        for i in range(len(self.metrics)):
            if not facts['selected'][i] <= facts['valid'][i] <= facts['targets'][i] <= facts['raw']:
                raise ValueError('文件目标/有效/入选计数矛盾')
            self.targets[i] += facts['targets'][i]
            self.valid[i] += facts['valid'][i]
            self.selected[i] += facts['selected'][i]
            self.kinds[i] |= facts['kinds'][i]
            if self.kinds[i].bit_count() > 1:
                raise ValueError(self.metrics[i].name + '跨文件匹配多种实际帧型，请明确选择')
        self.compatible.update(facts['compatible'])

    def result(self):
        """核完整消费后生成业务行。参数: 无。返回: (行list, 提示list)。异常: 贡献计数不符。"""
        rows = []
        for i, metric in enumerate(self.metrics):
            if (metric.matched, metric.selected) != (self.valid[i], self.selected[i]):
                raise ValueError(metric.name + '贡献未完整且唯一消费')
            row = metric.result()
            if row['value'] is None:
                row['reason'] = ('empty_file' if not self.raw else
                                 'no_target_in_domain' if self.targets[i] else 'no_target_frames')
            rows.append(row)
        warnings = [f'{identifier:#x} 按经典 CAN 实录解码 DBC 的 FD 声明' for identifier in sorted(self.compatible)]
        return rows, warnings


class FilePool:
    """管理有限工作槽及每文件连续块前缀；不在内存保存所有暂存块描述。"""

    def __init__(self, specs, budget, directory, cancel, statistics, *, _programs_checked=False):
        """初始化但不启动。参数: 文件spec列表、共享账本、暂存目录、外部取消、统计dict。
        返回: 新调度器。异常: 无；start安装进程资源的关闭责任。
        _programs_checked只来自父会话的实际准备结果，不读取配置中的标志。
        """
        self.specs, self.budget, self.directory = specs, budget, Path(directory)
        self._budget, self._held_cost = budget, 0
        self._started = self._closing = self._closed = False
        self._programs_checked = _programs_checked
        self.cancel, self.stats = cancel, statistics
        self.context = multiprocessing.get_context('spawn')
        self.stop = self.context.Event()
        self.slots = []
        self.files = [dict(produced=0, consumed=0, spool=0, eof=None, packet=None,
                           last_sequence=-1, last_time=None) for _ in specs]
        self.current = 0
        self.next_file = 0
        self.ordered = specs[0].get('file_merge', 'concatenate') == 'time_order'
        self.worker_cost = 0
        self.digest = sha256(Path(specs[0]['dbc']).read_bytes()).hexdigest()
        if self.digest != specs[0].get('_dbc_digest', self.digest):
            raise ValueError('编译后DBC内容变化')

    def check_cancel(self):
        """传递外部取消。参数: 无。返回: None。异常: InterruptedError。"""
        if self.cancel is not None and self.cancel.is_set():
            if self.stop is not None:
                self.stop.set()
            raise InterruptedError('fast会话取消')


    def start(self, count):
        """预付真实工作槽后启动；任何部分构造失败仍由本池关闭已登记资源。

        参数: count实际工作数。返回: None。异常: 原预算/启动/归属错误；
        持续清理失败在原异常的fast_pool_cleanup_owner保留内部恢复入口。
        """
        from .session_worker import worker_main
        if self._started or self._closing or self._closed:
            raise RuntimeError('fast工作池已经启动或关闭，不能重复启动')
        self._started = True
        try:
            per_worker = 3 * RAM + Path(self.specs[0]['dbc']).stat().st_size * 64
            _reserve_owned_ram(self, per_worker * count, 'worker_cost')
            for _ in range(count):
                self.check_cancel()
                # 先安装槽，再创建管道；第二根管道或启动失败时，第一根仍有关闭责任。
                slot = dict(control=None, data=None, child_control=None, child_data=None,
                            process=None, tree=None, startup=None, phase='idle', file=None, stop_requested=False)
                self.slots.append(slot)
                slot['control'], slot['child_control'] = self.context.Pipe()
                slot['control'] = ControlChannel(slot['control'],'fast',parent=True,max_bytes=self.budget.memory_budget_bytes)
                slot['child_control'] = ControlChannel(slot['child_control'],'fast',parent=False,max_bytes=self.budget.memory_budget_bytes)
                slot['data'], slot['child_data'] = self.context.Pipe(duplex=False)
                from .._process_start import spawn_entry
                try:
                    target,args,slot['startup']=spawn_entry(self.context,worker_main,
                        (slot['child_control'],slot['child_data'],self.stop))
                except BaseException as error:
                    slot['startup']=getattr(error,'process_start_cleanup_owner',None)
                    raise
                process = self.context.Process(target=target,args=args)
                slot['process'] = process
                process.start()
                from ..batch.process_tree import ProcessTree
                try:
                    slot['tree'] = (ProcessTree(process.pid) if slot['startup'] is None else
                        ProcessTree(process.pid,registration=slot['startup'],process=process))
                except BaseException as error:
                    slot['tree'] = getattr(error,'process_tree_cleanup_owner',None)
                    raise
                if slot['startup'] is not None:
                    slot['startup'].close();slot['startup']=None
                self.stats['worker_pids'].append(process.pid)
                # 子进程已取得自己的端点，父进程关闭副本；失败端点留在同一槽供重试。
                for key in ('child_control', 'child_data'):
                    connection = slot[key]
                    try:
                        connection.close()
                    finally:
                        if connection.closed:
                            slot[key] = None
                self.assign(slot)
        except BaseException as error:
            _cleanup_owner(self, error, 'fast_pool_cleanup_owner', 'fast工作池启动')
            raise

    def assign(self, slot):
        """按文件声明顺序派发下一文件。参数: 空闲槽。返回: None。异常: 断管。"""
        slot['phase'] = 'idle'
        if self.next_file < len(self.specs):
            index = self.next_file
            self.next_file += 1
            slot.update(file=index, phase='computing')
            operation = 'program_file' if self._programs_checked else 'file'
            slot['control'].send((operation, index, self.specs[index], str(self.directory), self.digest))

    def grant(self, slot):
        """授权一个完整块的唯一交付路径。参数: 已报价工作槽。返回: None。异常: 必要暂存超额。"""
        if slot['phase'] != 'offered':
            return
        if not self.ordered and slot['file'] == self.current:
            slot.update(phase='direct', delivered=False, received=None)
            slot['control'].send(('direct',))
            return
        size = slot['size']
        quota = self.budget.spool_quota_bytes
        if quota is not None and self.budget.spool_bytes + size > quota:
            if self.ordered:
                raise BudgetExceededError('time_order必要暂存超过spool_quota_bytes')
            if not slot.get('paused', False):
                self.stats['prefetch_pauses'] += 1
                slot['paused'] = True
            return
        self.budget.reserve_spool(size)
        slot['phase'] = 'spooling'
        slot['control'].send(('spool',))

    def pump(self, blocking=True):
        """推进有限控制和数据消息，优先响应所有worker错误。参数: 是否最多等50ms。
        返回: None。异常: 协议、worker退出、取消或IO错误。
        """
        self.check_cancel()
        for slot in self.slots:
            self.grant(slot)
        connections = [s['control'] for s in self.slots]
        connections += [s['data'] for s in self.slots if s['phase'] == 'direct' and s['received'] is None]
        started = perf_counter()
        ready = wait(connections, timeout=0.05 if blocking else 0)
        self.stats['main_wait_seconds'] += perf_counter() - started
        for slot in self.slots:
            process = slot['process']
            message = None
            pipe_error = None
            if slot['control'] in ready:
                try:
                    message = slot['control'].recv()
                except (EOFError, BrokenPipeError) as error:
                    pipe_error = error
                # 子进程可在发送error后正常退出，完整业务错误必须先于退出状态报告。
                if message is not None and message[0] == 'error':
                    self.message(slot, message)
            if process.exitcode is not None:
                raise RuntimeError(f'fast工作进程意外退出：{process.pid}，{process.exitcode}') from pipe_error
            if pipe_error is not None:
                raise pipe_error
            if message is not None:
                self.message(slot, message)
            if slot['phase'] == 'direct' and slot['received'] is None and slot['data'] in ready:
                packet = slot['data'].recv_bytes(LIMIT)
                if len(packet) != slot['size']:
                    raise ValueError('直传贡献长度不符')
                slot['received'] = packet
                self.stats['received_bytes'] += len(packet)
            if slot['phase'] == 'direct' and slot['received'] is not None and slot['delivered']:
                state = self.files[slot['file']]
                state['packet'] = slot['received']
                state['produced'] += 1
                slot.update(phase='consuming', received=None)
            self.grant(slot)

    def message(self, slot, message):
        """核验工作槽状态及块序号。参数: 槽/控制tuple。返回: None。异常: 错误或协议不符。"""
        tag = message[0]
        if tag == 'error':
            raise RuntimeError(f"{self.specs[slot['file']]['path']}：{message[1]}：{message[2]}")
        if len(message) < 3 or message[1] != slot['file']:
            raise ValueError('工作进程文件身份不符')
        state = self.files[slot['file']]
        number = message[2]
        if type(number) is not int or number != state['produced']:
            raise ValueError('贡献块缺失、重复或顺序错误')
        if tag == 'offer' and slot['phase'] == 'computing':
            size = message[3]
            if type(size) is not int or not 0 < size <= LIMIT:
                raise ValueError('贡献块报价长度非法')
            slot.update(phase='offered', size=size, paused=False)
        elif tag == 'stored' and slot['phase'] == 'spooling':
            if message[3] != slot['size'] or state['spool'] != number:
                raise ValueError('暂存提交长度或前缀不符')
            state['spool'] += 1
            state['produced'] += 1
            self.stats['spool_written_bytes'] += message[3]
            self.stats['spool_live_bytes'] += message[3]
            self.stats['spool_peak_bytes'] = max(self.stats['spool_peak_bytes'], self.stats['spool_live_bytes'])
            slot['phase'] = 'computing'
            slot['control'].send(('next',))
        elif tag == 'delivered' and slot['phase'] == 'direct' and not slot['delivered']:
            if message[3] != slot['size']:
                raise ValueError('直传提交长度不符')
            slot['delivered'] = True
        elif tag == 'eof' and slot['phase'] == 'computing':
            if state['eof'] is not None:
                raise ValueError('重复文件EOF')
            state['eof'] = message[3]
            self.stats['files'].append(dict(file_index=slot['file'], pid=message[5], **message[4]))
            self.assign(slot)
        else:
            raise ValueError('贡献交付状态与消息不符')

    def packet_records(self, index, number, packet):
        """验证块间顺序并展开一块。参数: 文件/块号/bytes。返回: 贡献生成器。异常: 顺序或协议错误。"""
        state = self.files[index]
        records = decode(packet, index, number, len(self.specs[index]['metrics']))
        if self.specs[index].get('_profile', False):
            started = perf_counter()
            records = list(records)
            self.stats['main_decode_seconds'] += perf_counter() - started
        for record in records:
            timestamp, sequence, _ = record
            if sequence <= state['last_sequence']:
                raise ValueError('贡献记录跨块重复或回退')
            if self.ordered and state['last_time'] is not None and timestamp < state['last_time']:
                raise ValueError('贡献时间跨块回退')
            state['last_sequence'], state['last_time'] = sequence, timestamp
            yield record

    def read_spool(self, index, number):
        """读取并删除一个已提交块。参数: 文件/块号。返回: bytes。异常: 缺失、超长、IO。
        删除仅减少当前占用，不返还累计预约额度。
        """
        path = self.directory / f'{index}-{number}.block'
        started = perf_counter()
        with path.open('rb') as stream:
            packet = stream.read(LIMIT + 1)
        if len(packet) > LIMIT:
            raise ValueError('暂存块过大')
        path.unlink()
        self.stats['spool_live_bytes'] -= len(packet)
        self.stats['main_spool_read_seconds'] += perf_counter() - started
        return packet

    def concatenate(self, accumulator):
        """消费当前文件，后续文件同时预读。参数: 会话累计器。返回: None。异常: 运行或累计错误。"""
        for index, state in enumerate(self.files):
            self.current = index
            while True:
                self.pump(False)
                number = state['consumed']
                direct = False
                if number < state['spool']:
                    packet = self.read_spool(index, number)
                elif state['packet'] is not None:
                    packet, state['packet'] = state['packet'], None
                    direct = True
                elif state['eof'] is not None:
                    if number != state['produced']:
                        raise ValueError('文件EOF前贡献未完整消费')
                    accumulator.finish_file(state['eof'])
                    break
                else:
                    self.pump()
                    continue
                for record in self.packet_records(index, number, packet):
                    accumulator.consume(record)
                packet = None
                state['consumed'] += 1
                if direct:
                    slot = next(s for s in self.slots if s['file'] == index)
                    slot['phase'] = 'computing'
                    slot['control'].send(('next',))

    def file_records(self, index):
        """逐块读取一个已完整暂存文件。参数: 文件号。返回: 贡献生成器。异常: 缺块/完整性错。"""
        state = self.files[index]
        while state['consumed'] < state['produced']:
            self.check_cancel()
            number = state['consumed']
            packet = self.read_spool(index, number)
            yield from self.packet_records(index, number, packet)
            state['consumed'] += 1

    def time_order(self, accumulator):
        """完成必要暂存后k路稳定归并。参数: 累计器。返回: None。异常: 输入/资源/计算错误。"""
        while any(state['eof'] is None for state in self.files):
            self.pump()
        self.close(True)
        started = perf_counter()
        streams = [iter(self.file_records(i)) for i in range(len(self.files))]
        heap = []
        for index, stream in enumerate(streams):
            record = next(stream, None)
            if record is not None:
                heapq.heappush(heap, (record[0], index, record[1], record))
        while heap:
            _, index, _, record = heapq.heappop(heap)
            accumulator.consume(record)
            following = next(streams[index], None)
            if following is not None:
                heapq.heappush(heap, (following[0], index, following[1], following))
        for state in self.files:
            if state['consumed'] != state['produced']:
                raise ValueError('归并结束后仍缺少贡献块')
            accumulator.finish_file(state['eof'])
        self.stats['main_merge_and_consume_seconds'] += perf_counter() - started


    def close(self, success=False):
        """先结束实际写入者，再关闭句柄和自有费用；失败槽保留到后续重试。

        参数: success要求正常退出。返回: None。异常: 原取消或汇总关闭错误；
        不删除任何暂存目录，未关闭资源仍由本池持有。
        """
        if self._closed:
            return
        self._closing = True
        errors = []
        if not success:
            try:
                self.stop.set()
            except BaseException as error:
                errors.append(error)
        for slot in tuple(self.slots):
            process = slot['process']
            try:
                if process is not None and not getattr(process, '_closed', False) and process.pid is not None:
                    if success and not slot['stop_requested']:
                        slot['control'].send(('close',))
                        slot['stop_requested'] = True
                        process.join(5)
                    if process.is_alive():
                        process.terminate()
                        process.join(5)
                        if success:
                            raise RuntimeError('fast工作进程未正常关闭')
                    if process.is_alive():
                        raise RuntimeError('fast工作进程仍在运行')
                    if success and process.exitcode != 0:
                        raise RuntimeError('fast工作进程关闭失败')
            except BaseException as error:
                errors.append(error)
            tree = slot['tree']
            if tree is not None:
                try:
                    tree.close()
                except BaseException as error:
                    errors.append(error)
                finally:
                    # 构造失败可能只剩OpenProcess句柄，不能只检查作业_handle。
                    if tree._closed:
                        slot['tree'] = None
            if process is not None:
                try:
                    if not getattr(process, '_closed', False):
                        if process.pid is not None:
                            process.join(0)
                            if process.is_alive():
                                raise RuntimeError('fast写入进程未结束，保留资源责任')
                        process.close()
                except BaseException as error:
                    errors.append(error)
                finally:
                    if getattr(process, '_closed', False):
                        slot['process'] = None
            for key in ('control', 'data', 'child_control', 'child_data', 'startup'):
                connection = slot.get(key)
                if connection is not None:
                    try:
                        connection.close()
                    except BaseException as error:
                        errors.append(error)
                    finally:
                        if connection.closed:
                            slot[key] = None
            if all(slot.get(key) is None for key in ('process', 'tree', 'control', 'data', 'child_control', 'child_data', 'startup')):
                self.slots.remove(slot)
        if not self.slots:
            try:
                _release_owned_ram(self, self.worker_cost, 'worker_cost')
            except BaseException as error:
                errors.append(error)
        self._closed = not self.slots and self._held_cost == 0
        if self._closed:
            # 所有子进程已结束后解除本池对自有同步事件的引用；不改调用方的cancel。
            self.stop = None
        if errors:
            first = errors[0]
            for other in errors[1:]:
                first.add_note('fast工作池另有清理失败: ' + type(other).__name__)
            if isinstance(first, (KeyboardInterrupt, SystemExit)):
                raise first
            raise RuntimeError('fast进程资源关闭失败') from first



class _SessionResources:
    """仅管理一个fast会话的固定费用、读取器、工作池和自有目录。"""

    def __init__(self, budget):
        """建立空责任槽。参数: 本次账本。返回: 新对象。异常: 无资源创建。"""
        self._budget, self._held_cost, self._fixed_cost = budget, 0, 0
        self.reader = self.pool = self.directory = self.directory_identity = None
        self._closed = False

    def open_reader(self, spec, database, cancel):
        """创建并登记本会话读取器，收编构造中未能关闭的真实子所有者。

        参数: 文件声明、DBC、取消。返回: FileContributions。异常: 原构造错误。
        ASC/BLF构造失败均收编实际未关闭的来源owner，直到成功关闭才清槽。
        """
        if self.reader is not None:
            raise RuntimeError('fast前一读取器尚未关闭')
        try:
            self.reader = FileContributions(
                spec, database, cancel, self._budget, _programs_checked=True)
            return self.reader
        except BaseException as error:
            pending = getattr(error, 'fast_reader_cleanup_owner', None)
            if pending is None:
                pending = getattr(error, 'asc_read_cleanup_owner', None)
            if pending is None:
                pending = getattr(error, 'blf_read_cleanup_owner', None)
            self.reader = pending
            raise

    def close_reader(self):
        """关闭实际读取器；仅在真实关闭完成后清槽。参数: 无。返回: None。异常: 原关闭错误。"""
        reader = self.reader
        if reader is None:
            return
        try:
            reader.close()
            if not getattr(reader, 'closed', False):
                raise RuntimeError('fast读取器close返回但未完成关闭')
        finally:
            if getattr(reader, 'closed', False):
                self.reader = None

    def create_directory(self, work_dir):
        """独占创建并登记目录，避免自动终结器在写入者未结束时删除目录。

        参数: 可选工作父目录。返回: Path。异常: 创建或身份登记错误，已有目录不删除。
        """
        from ..results.owned_directory import directory_identity
        if work_dir is not None:
            Path(work_dir).mkdir(parents=True, exist_ok=True)
        self.directory = Path(mkdtemp(prefix='fast-session-', dir=work_dir))
        self.directory_identity = directory_identity(self.directory)
        return self.directory

    def close(self):
        """依次停止工作池、读取器、删除自有目录并退款，任一步失败保留重试责任。

        参数: 无。返回: None。异常: 原清理错误；未确认停止写入者时不删除目录。
        """
        if self._closed:
            return
        try:
            pool = self.pool
            if pool is not None:
                try:
                    pool.close()
                    if not pool._closed:
                        raise RuntimeError('fast工作池close返回但未完成关闭')
                finally:
                    if pool._closed:
                        self.pool = None
            self.close_reader()
            if self.directory is not None:
                from ..results.owned_directory import remove_owned_directory
                remove_owned_directory(self.directory, self.directory_identity)
                self.directory = self.directory_identity = None
            _release_owned_ram(self, self._fixed_cost, '_fixed_cost')
        finally:
            self._closed = (self.pool is None and self.reader is None
                            and self.directory is None and self._held_cost == 0)


def run_session(spec, database=None, *, work_dir=None, cancel_event=None, statistics=None,
                _programs_checked=False):
    """运行一个连续fast任务。参数: 编译spec、可复用DBC、临时目录、取消事件、可选统计dict。
    返回: (业务行list, 提示list)。异常: 配置/读取/公式/资源/协议/取消；不返回部分结果。
    _programs_checked由公共编译后的内部入口传入；直接调用默认仍检查文本和指令。
    """
    import cantools
    spec = effective_spec(spec)
    # 原生低层入口仍完整检查文本；同一会话后续文件只绑定已经核过的指令。
    # 公共编译器调用链显式传入准备状态，不信任 spec 中的同名字段。
    specs = _checked_file_specs(spec, _programs_checked)
    count = _worker_process_limit(spec['process_count'], len(specs))
    budget = ResourceBudget(spec.get('memory_budget_bytes', 268435456), spec.get('spool_quota_bytes'))
    stats = statistics if statistics is not None else {}
    stats.update(worker_pids=[], files=[], received_bytes=0, spool_written_bytes=0,
                 spool_live_bytes=0, spool_peak_bytes=0, prefetch_pauses=0,
                 main_wait_seconds=0.0, main_spool_read_seconds=0.0,
                 main_decode_seconds=0.0, main_merge_and_consume_seconds=0.0,
                 detailed_profile=spec.get('_profile', False))
    # 覆盖计划/累计器、内联读取空间与归并各流当前块；不是整个进程RSS承诺。
    cost = RAM * (2 + (len(specs) if spec.get('file_merge') == 'time_order' else 1))
    cost += len(json.dumps({k:v for k,v in spec.items() if k != '_database'}).encode()) * 32
    if count == 0 and all(Path(item['path']).suffix.lower() == '.blf' for item in specs):
        # 内联读取逐文件开关，最多一个BLF owner；从原固定费移交64KiB，避免重复计费。
        # 混合来源/工作进程的既有分摊不变，来源owner仍预约自身实际费用。
        cost -= 65536
    resources = _SessionResources(budget)
    accumulator = primary = None
    try:
        # 首次申请和累计器构造均在责任保护区内，申请完成后取消也有真实费用槽。
        _reserve_owned_ram(resources, cost, '_fixed_cost')
        accumulator = SessionAccumulator(spec)
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError('fast会话启动前取消')
        if '_dbc_digest' in spec and sha256(Path(spec['dbc']).read_bytes()).hexdigest() != spec['_dbc_digest']:
            raise ValueError('编译后DBC内容变化')
        if database is None:
            database = load_dbc_file(spec['dbc'], cantools)
        if count == 0 and (len(specs) == 1 or spec.get('file_merge', 'concatenate') == 'concatenate'):
            for item in specs:
                reader = resources.open_reader(item, database, cancel_event)
                for record in reader:
                    accumulator.consume(record)
                accumulator.finish_file(reader.summary())
                if spec.get('_profile', False):
                    stats['files'].append(dict(path=item['path'], **reader.timings))
                resources.close_reader()
        else:
            directory = resources.create_directory(work_dir)
            pool = FilePool(specs, budget, directory, cancel_event, stats, _programs_checked=True)
            resources.pool = pool
            if count == 0:
                # 内联时间归并仍有必要暂存；读取器和目录均归当前资源所有者。
                for index, item in enumerate(specs):
                    reader = resources.open_reader(item, database, cancel_event)
                    number = 0
                    for records in batches(reader):
                        packet = encode(index, number, records)
                        budget.reserve_spool(len(packet))
                        (directory / f'{index}-{number}.block').write_bytes(packet)
                        stats['spool_written_bytes'] += len(packet)
                        stats['spool_live_bytes'] += len(packet)
                        stats['spool_peak_bytes'] = max(stats['spool_peak_bytes'], stats['spool_live_bytes'])
                        number += 1
                    pool.files[index].update(produced=number, spool=number, eof=reader.summary())
                    resources.close_reader()
            else:
                pool.start(count)
            if pool.ordered:
                pool.time_order(accumulator)
            else:
                pool.concatenate(accumulator)
            pool.close(True)
        result = accumulator.result()
        stats['raw_record_count'] = accumulator.raw
        stats['calculation_counts'] = [dict(name=metric.name, targets=accumulator.targets[i],
            valid=accumulator.valid[i], selected=accumulator.selected[i]) for i, metric in enumerate(accumulator.metrics)]
        resources.close()
        return result
    except BaseException as error:
        primary = error
        _cleanup_owner(resources, error, 'fast_session_cleanup_owner', 'fast会话')
        raise
    finally:
        try:
            stats.update(budget.snapshot())
            if accumulator is not None and accumulator.profile:
                stats['main_accumulate_seconds'] = accumulator.accumulate_seconds
        except BaseException as diagnostic:
            if primary is None:
                raise
            primary.add_note('fast资源统计附加失败: ' + type(diagnostic).__name__)
