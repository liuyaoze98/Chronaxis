"""一个fast会话的多文件调度和最终累计。

worker只求当前帧贡献；主进程控制统一预算、交付顺序及成功发布前的完整性。
concatenate可暂停可选预读；time_order必要暂存完成后稳定归并。临时目录和
进程均属于本次调用，异常不返回部分结果。内联与batch不经传输协议。
"""
from hashlib import sha256
from contextlib import ExitStack
import heapq
import json
import multiprocessing
from multiprocessing.connection import wait
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from ..results.budget import ResourceBudget
from ..results.errors import BudgetExceededError
from .blocks import RAM, LIMIT, encode, decode, batches
from .compute import prepare_metric
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


class SessionAccumulator:
    """只有主会话持有的标量累计器。计数、目标缺失和帧身份按计算项分别核验。"""

    def __init__(self, spec):
        """准备累计器。参数: 编译声明。返回: 新对象。异常: 公式声明错误。"""
        self.metrics = [prepare_metric(item) for item in spec['metrics']]
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

    def __init__(self, specs, budget, directory, cancel, statistics):
        """初始化但不启动。参数: 文件spec列表、共享账本、暂存目录、外部取消、统计dict。
        返回: 新调度器。异常: 无；start安装进程资源的关闭责任。
        """
        self.specs, self.budget, self.directory = specs, budget, Path(directory)
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
            self.stop.set()
            raise InterruptedError('fast会话取消')

    def start(self, count):
        """预付全部工作槽后启动spawn。参数: 实际工作数。返回: None。异常: 预算/启动/归属失败。"""
        from .session_worker import worker_main
        per_worker = 3 * RAM + Path(self.specs[0]['dbc']).stat().st_size * 64
        self.budget.reserve_ram(per_worker * count)
        self.worker_cost = per_worker * count
        for _ in range(count):
            self.check_cancel()
            control, child_control = self.context.Pipe()
            data, child_data = self.context.Pipe(duplex=False)
            slot = dict(control=control, data=data, process=None, tree=None, phase='idle', file=None)
            self.slots.append(slot)
            try:
                process = self.context.Process(target=worker_main, args=(child_control, child_data, self.stop))
                slot['process'] = process
                process.start()
                if os.name == 'nt':
                    from ..batch.process_tree import ProcessTree
                    slot['tree'] = ProcessTree(process.pid)
                self.stats['worker_pids'].append(process.pid)
            finally:
                child_control.close()
                child_data.close()
            self.assign(slot)

    def assign(self, slot):
        """按文件声明顺序派发下一文件。参数: 空闲槽。返回: None。异常: 断管。"""
        slot['phase'] = 'idle'
        if self.next_file < len(self.specs):
            index = self.next_file
            self.next_file += 1
            slot.update(file=index, phase='computing')
            slot['control'].send(('file', index, self.specs[index], str(self.directory), self.digest))

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
            if process.exitcode is not None:
                raise RuntimeError(f'fast工作进程意外退出：{process.pid}，{process.exitcode}')
            if slot['control'] in ready:
                message = slot['control'].recv()
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
        """关闭自有工作树。参数: success要求正常退出。返回: None。异常: 关闭/异常退出错误。
        失败时先取消再终止；不等待仍被背压阻塞的worker自行退出。
        """
        errors = []
        if not success:
            self.stop.set()
        for slot in self.slots:
            process = slot['process']
            try:
                if process is not None and process.pid is not None:
                    if success:
                        slot['control'].send(('close',))
                        process.join(5)
                    if process.is_alive():
                        process.terminate()
                        process.join(5)
                        if success:
                            raise RuntimeError('fast工作进程未正常关闭')
                    if success and process.exitcode != 0:
                        raise RuntimeError('fast工作进程关闭失败')
            except BaseException as error:
                errors.append(error)
            finally:
                if slot['tree'] is not None:
                    try:
                        slot['tree'].close()
                    except BaseException as error:
                        errors.append(error)
                slot['control'].close()
                slot['data'].close()
        self.slots.clear()
        if self.worker_cost:
            self.budget.release_ram(self.worker_cost)
            self.worker_cost = 0
        if errors:
            raise RuntimeError('fast进程资源关闭失败') from errors[0]


def run_session(spec, database=None, *, work_dir=None, cancel_event=None, statistics=None):
    """运行一个连续fast任务。参数: 编译spec、可复用DBC、临时目录、取消事件、可选统计dict。
    返回: (业务行list, 提示list)。异常: 配置/读取/公式/资源/协议/取消；不返回部分结果。
    """
    import cantools
    spec = effective_spec(spec)
    specs = file_specs(spec)
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
    budget.reserve_ram(cost)
    accumulator = SessionAccumulator(spec)
    pool = None
    try:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError('fast会话启动前取消')
        if '_dbc_digest' in spec and sha256(Path(spec['dbc']).read_bytes()).hexdigest() != spec['_dbc_digest']:
            raise ValueError('编译后DBC内容变化')
        if database is None:
            database = cantools.database.load_file(spec['dbc'])
        # 单进程拼接及单文件直接执行，不支付序列化成本。
        if count == 0 and (len(specs) == 1 or spec.get('file_merge', 'concatenate') == 'concatenate'):
            for item in specs:
                reader = FileContributions(item, database, cancel_event, budget)
                try:
                    for record in reader:
                        accumulator.consume(record)
                    accumulator.finish_file(reader.summary())
                    if spec.get('_profile', False):
                        stats['files'].append(dict(path=item['path'], **reader.timings))
                finally:
                    reader.close()
        else:
            if work_dir is not None:
                Path(work_dir).mkdir(parents=True, exist_ok=True)
            with ExitStack() as cleanup:
                directory = cleanup.enter_context(TemporaryDirectory(prefix='fast-session-', dir=work_dir))
                pool = FilePool(specs, budget, directory, cancel_event, stats)
                # 先停止写入者，再删除本次目录；异常时也保持同一关闭顺序。
                cleanup.callback(pool.close)
                if count == 0:
                    # time_order内联仍需暂存，但没有子进程和IPC。
                    for index, item in enumerate(specs):
                        reader = FileContributions(item, database, cancel_event, budget)
                        try:
                            number = 0
                            for records in batches(reader):
                                packet = encode(index, number, records)
                                budget.reserve_spool(len(packet))
                                (Path(directory)/f'{index}-{number}.block').write_bytes(packet)
                                stats['spool_written_bytes'] += len(packet)
                                stats['spool_live_bytes'] += len(packet)
                                stats['spool_peak_bytes'] = max(stats['spool_peak_bytes'], stats['spool_live_bytes'])
                                number += 1
                            pool.files[index].update(produced=number, spool=number, eof=reader.summary())
                        finally:
                            reader.close()
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
            valid=accumulator.valid[i], selected=accumulator.selected[i]) for i,metric in enumerate(accumulator.metrics)]
        return result
    finally:
        try:
            if pool is not None:
                pool.close()
        finally:
            budget.release_ram(cost)
            stats.update(budget.snapshot())
            if accumulator.profile:
                stats['main_accumulate_seconds'] = accumulator.accumulate_seconds
