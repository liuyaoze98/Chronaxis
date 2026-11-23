"""time_order直接积分的读取段：文件工作进程产出组点，主进程谁先就绪先收并写入暂存。

PERF-P5-ORDER-01 A2-4、A2-5。输入是一个time_order连续来源的全部文件和已验证的数值声明；
输出是每个文件一个`<文件序号>.points`暂存文件（原样保存P5G1组点包）和各文件的最终事实
（观测首末、原帧数、解码次数、帧型兼容提示、实际帧型）。

流程：
1. 复用ParallelIntegralPool启动有限工作槽、核对READY与DBC元数据、下发points模式任务；
2. 轮询全部槽，哪个槽的包先到就先收：只用decode_points_prefix读到事实为止，核对文件号与块号后
   原样追加到该文件的暂存，再许可下一块；事件部分不在这里解码；
3. 文件EOF并收到finished确认后，该槽领取下一个文件；
4. 读取段错误报文件序号最小者：序号更小的文件继续读完或出错，更大的文件不再推进。

所有进程、管道和预算归本池；暂存文件归PointSpool。关闭不删除输入、用户文件或其他目录。
"""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import struct
from time import perf_counter
from uuid import uuid4

from .._control_wire import ControlProtocolError
from ..results.budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..sources.protocol import SourceReadError
from .file_group_points import file_points_cost, file_points_minimum_cost
from .history import _metadata_bytes
from .integral_blocks import BLOCK_RAM, WIRE_LIMIT, decode_points, decode_points_prefix, pack_task
from .parallel_integral_pool import ParallelIntegralPool, _configuration_rows, _task_bytes, _TASK_BASE_COST


class ParallelPointPool(ParallelIntegralPool):
    """一个time_order来源的组点工作槽池；不归并、不累计，只负责读取段与文件事实。"""

    _FILE_MERGE = 'time_order'  # 组点池只服务time_order来源。

    def __init__(self, spec, budget, signals, *, process_count, **options):
        """登记来源并预约固定声明空间，不读原文件。

        参数: spec为file_merge为time_order的CANTextSpec；budget为共享预算；signals为原信号定义；
            process_count为正整数进程上限；options为与现有time_order读取相同的读取选项。
        返回: None，构造新的池owner。
        异常: 进程数或合并方式非法、空文件列表、原帧上下文时ValueError；预算不足时BudgetExceededError，
            清理失败附parallel_integral_pool_cleanup_owner。
        """
        super().__init__(spec, budget, signals, process_count=process_count, **options)
        self.timings.update(spool_write_seconds=0.0, read_spool_seconds=0.0)

    @staticmethod
    def points_minimum_cost(signal_count: int, *, process_count: int, file_count: int) -> int:
        """查询全部工作槽组点任务的必要费用下界，用于创建进程前排除必然不足的预算。

        参数: signal_count为非负信号定义数；process_count和file_count为正整数进程上限与文件数。
        返回: int字节数，含父任务与每个工作槽的固定重建和组点状态；不含DBC和声明图。
        异常: 非法数量时ValueError；不创建进程或修改预算。
        """
        if any(type(value) is not int or value < 1 for value in (process_count, file_count)):
            raise ValueError('组点进程数和文件数需要正整数')
        worker = _TASK_BASE_COST + file_points_minimum_cost(signal_count)
        return _TASK_BASE_COST + min(process_count, file_count) * worker

    def _dispatch(self, slot, index):
        """给空槽派发下一文件，文件命令同时声明points模式。参数: slot为空闲工作槽；index为文件序号。返回: None。异常: 发送失败。

        与父类相同地重置槽状态；第7个参数使工作进程在READY前出错时也不附加notes（A2-4）。
        """
        slot.update(file=index, number=0, ready=False, metadata=None, packet=None, error=None, configured=False,
                    requested=False, idle=False, await_finish=False, finished=False)
        spec = replace(self.spec, inputs=(self.spec.inputs[index],), file_merge='concatenate')
        slot['control'].send(('file', index, spec, self.signals, self._options, self._worker_limit, None, 'points'))
        self._file_slots[index] = slot

    def _configuration(self, definitions, expressions, specs, binding, session_id, derived, domain, batch_intervals,
                       step_ns=None):
        """构造points模式任务并计算配置需要的额外预约费用。

        参数: definitions、expressions、specs、binding、session_id、derived、domain为已验证数值声明，与父类相同；
            batch_intervals为用户正整数区间批上限；step_ns为None（实际间隔）或固定间隔正纳秒。
        返回: tuple[dict, int, int]，依次为固定task、父任务字节费和每子额外字节费（组点状态而非面积缓冲）。
        异常: 批上限非法时ValueError；声明展开或静态费用原错误继续传播。
        """
        rows = _configuration_rows(batch_intervals, len(specs))
        declared = _metadata_bytes((definitions, expressions[0].bindings,
            tuple((item.text, item.root.unit) for item in expressions), specs, binding, derived, domain))
        task = pack_task(definitions, expressions, specs, binding, session_id, derived=derived, domain=domain,
                         batch_intervals=rows, step_ns=step_ns, mode='points')
        task_size = _task_bytes(task)
        parent = _TASK_BASE_COST + 32 * max(declared, task_size)
        worker = _TASK_BASE_COST + 32 * task_size + file_points_cost(definitions, expressions, derived)
        return task, parent, worker

    def _accept_point_facts(self, index, facts):
        """更新一个文件截至本包的累计事实，不做concatenate的文件边界时间检查。

        参数: index为文件序号；facts为decode_points_prefix得到的dict。
        返回: None。
        异常: 计数回退或已记录的实际帧型改变时ControlProtocolError。
        """
        from ..sources.can_spec import can_field_from_key
        previous = self.file_facts.get(index)
        if previous is not None and (facts['count'] < previous['count'] or facts['decode_calls'] < previous['decode_calls']):
            raise ControlProtocolError('组点文件计数回退')
        if (previous is not None and previous['frame_identity'] is not None
                and facts['frame_identity'] != previous['frame_identity']):
            raise ControlProtocolError('组点文件的实际帧型改变')
        self.file_facts[index] = facts
        self.count += facts['count'] - (0 if previous is None else previous['count'])
        self.decode_calls += facts['decode_calls'] - (0 if previous is None else previous['decode_calls'])
        # 观测首末取全部文件的最小首点和最大末点，与现有time_order读取器相同。
        if facts['first_ns'] is not None:
            self.first_ns = facts['first_ns'] if self.first_ns is None else min(self.first_ns, facts['first_ns'])
        if facts['last_ns'] is not None:
            self.last_ns = facts['last_ns'] if self.last_ns is None else max(self.last_ns, facts['last_ns'])
        for key, extended in facts['compatibility_fields']:
            self.compatibility_fields[can_field_from_key(key)] = extended

    def _store(self, slot, index, spool):
        """把槽中已收到的一个组点包写入暂存并许可下一块。

        参数: slot为当前文件槽；index为文件序号；spool为PointSpool。
        返回: None。
        异常: 包内身份或块号不符时ControlProtocolError；前缀非法时IntegralBlockError；暂存配额或磁盘错误原样传播。
        """
        raw = slot.pop('packet')
        slot['packet'] = None
        file_index, number, eof, facts = decode_points_prefix(raw)
        if file_index != index or number != slot['number']:
            raise ControlProtocolError('组点包内身份或块号不符')
        slot['number'] += 1
        self._accept_point_facts(index, facts)
        started = perf_counter()
        spool.append(index, raw)
        self.timings['spool_write_seconds'] += perf_counter() - started
        raw = None
        # EOF包之后等待finished确认资源释放；否则立即许可下一块，保持每槽至多一个在途包。
        if eof:
            slot['await_finish'] = True
        else:
            self._request(slot)

    def _exit_error(self, error):
        """把管道断开转成指明文件和退出码的工作进程退出错误。

        参数: error为轮询或发送许可时遇到的BrokenPipeError、EOFError或ConnectionError。
        返回: SourceReadError；找不到已退出的工作进程时返回原error，由调用方原样抛出。
        异常: 无；只等待各进程最多0.5秒以取得真实退出码。
        """
        for slot in self._slots:
            process = slot.get('process')
            if process is None or slot.get('idle'):
                continue
            process.join(0.5)
            if process.exitcode is not None:
                return SourceReadError(f"积分工作进程意外退出：{self.spec.inputs[slot['file']].path}，"
                                       f"退出码{process.exitcode}")
        return error

    def spool_all(self, spool):
        """执行读取段：收齐全部文件的组点包写入暂存，或报出文件序号最小的读取段错误。

        参数: spool为本次PointSpool，负责暂存文件与配额。
        返回: None；成功后file_facts含每个文件的最终事实，可关闭本池再归并。
        异常: 读取段错误时SourceReadError('{路径}: {类型}: {信息}')；工作进程退出、协议或暂存错误原样传播；
            任何失败都清理本池的进程与费用（附parallel_integral_pool_cleanup_owner）。
        """
        if self._closed or not self._configured or self._iterating:
            raise ValueError('组点读取段只能在配置完成后执行一次')
        self._iterating = True
        started = perf_counter()
        failures, done = {}, set()
        total = len(self.spec.inputs)
        try:
            while True:
                # 已有失败时只需等待序号更小的文件；它们可能报出更早的读取错误。
                limit = min(failures) if failures else total
                if all(index in done for index in range(limit)):
                    break
                progressed = False
                for index, slot in sorted(list(self._file_slots.items())):
                    if index >= limit or index in failures:
                        continue
                    if slot.get('error') is not None:
                        failures[index] = slot['error']
                        progressed = True
                        continue
                    if slot.get('ready') and slot.get('metadata') is not None:
                        self._accept_metadata(slot)
                        progressed = True
                    if slot.get('packet') is not None:
                        self._store(slot, index, spool)
                        progressed = True
                    if slot.get('finished'):
                        done.add(index)
                        self._file_slots.pop(index)
                        progressed = True
                        # 出现失败后不再派发新文件：新文件的序号都更大，其错误不可能被报告。
                        if not failures and self._next_file < total:
                            self._dispatch(slot, self._next_file)
                            self._next_file += 1
                        else:
                            slot['idle'] = True
                if not progressed and not self._poll_controls():
                    waiting = next((slot for index, slot in self._file_slots.items()
                                    if index < limit and index not in failures), None)
                    if waiting is not None:
                        waiting['control'].poll(0.05)
            if failures:
                index = min(failures)
                _, name, message = failures[index]
                raise SourceReadError(f'{self.spec.inputs[index].path}: {name}: {message}')
            self._current = total
        except (BrokenPipeError, EOFError, ConnectionError) as error:
            # 工作进程崩溃时管道先断开；报出哪个文件的进程以什么退出码结束，而不是裸管道错误。
            failure = self._exit_error(error)
            _cleanup_owner(self, failure, 'parallel_integral_pool_cleanup_owner', '组点读取段')
            if failure is error:
                raise
            raise failure from error
        except BaseException as error:
            _cleanup_owner(self, error, 'parallel_integral_pool_cleanup_owner', '组点读取段')
            raise
        finally:
            self.timings['read_spool_seconds'] += perf_counter() - started
            self._iterating = False


class PointSpool:
    """本次组点暂存的唯一owner：一个独占目录、每文件一个暂存文件及归并缓冲预约。

    写入段只追加，读回段每个文件同一时间只展开一个包；关闭时只删除本次登记的文件和目录。
    """

    def __init__(self, budget, work_dir, file_count, *, integrity=False):
        """独占新建暂存目录，不创建文件。

        参数: budget为共享ResourceBudget；work_dir为本次会话自有工作目录；file_count为正整数文件数；
            integrity为True时每包附SHA-256（直接积分计划不开完整性诊断，实际为False）。
        返回: None。
        异常: 文件数非法时ValueError；目录已存在或无法创建时OSError；构造清理失败附point_spool_cleanup_owner。
        """
        self._budget = budget
        self._held_cost = self._merge_cost = 0
        self._closed = False
        self._integrity = integrity
        self._root = None
        self._paths, self._writers, self._readers = {}, {}, {}
        self._numbers, self._eof = {}, {}
        self.bytes_written = 0
        try:
            if type(file_count) is not int or file_count < 1:
                raise ValueError('组点暂存需要正整数文件数')
            self._file_count = file_count
            root = Path(work_dir) / ('group-merge-' + uuid4().hex)
            root.mkdir(parents=True, exist_ok=False)
            self._root = root
        except BaseException as error:
            _cleanup_owner(self, error, 'point_spool_cleanup_owner', '组点暂存构造')
            raise

    def append(self, index, packet):
        """把一个组点包原样追加到该文件的暂存。

        参数: index为文件序号；packet为已核前缀的P5G1 bytes。
        返回: None。
        异常: 已开始读回或已关闭时ValueError；暂存配额不足时BudgetExceededError；独占创建或写入失败时OSError。
        P5G1自带8字节包头分帧，不另存长度；开启integrity时在包头后写SHA-256。
        """
        if self._closed or self._readers:
            raise ValueError('组点暂存已关闭或已开始读回')
        handle = self._writers.get(index)
        if handle is None:
            path = self._root / f'{index}.points'
            handle = path.open('xb')
            # 先登记路径和句柄，后续写入失败时close仍能找到并删除它们。
            self._paths[index] = path
            self._writers[index] = handle
        self._budget.reserve_spool(len(packet) + (32 if self._integrity else 0))
        handle.write(packet[:8])
        if self._integrity:
            handle.write(sha256(packet).digest())
        handle.write(memoryview(packet)[8:])
        self.bytes_written += len(packet)

    def open_readers(self):
        """结束写入并为每个文件打开读回句柄，预约每文件一个块的归并缓冲。

        参数: 无。返回: None。
        异常: 某文件没有任何暂存包时SourceReadError；预算不足时BudgetExceededError；打开失败时OSError。
        """
        for handle in self._writers.values():
            handle.close()
        self._writers.clear()
        _reserve_owned_ram(self, self._file_count * BLOCK_RAM, '_merge_cost')
        for index in range(self._file_count):
            if index not in self._paths:
                raise SourceReadError('组点暂存缺少文件：' + str(index))
            self._readers[index] = self._paths[index].open('rb')
            self._numbers[index] = 0
            self._eof[index] = False

    def next_packet(self, index):
        """读回并完整解码一个文件的下一个组点包。

        参数: index为文件序号。
        返回: PointPacket；该文件已读完时None。
        异常: 截断、长度或标志非法、摘要不符、块号不连续、缺少EOF或EOF后仍有数据时SourceReadError；
            包内容非法时IntegralBlockError。
        """
        handle = self._readers[index]
        header = handle.read(8)
        if not header:
            if not self._eof[index]:
                raise SourceReadError('组点暂存缺少文件EOF')
            return None
        if self._eof[index]:
            raise SourceReadError('组点暂存在EOF后仍有数据')
        if len(header) != 8:
            raise SourceReadError('组点暂存长度头截断')
        magic, size = struct.unpack('!4sI', header)
        if magic != b'P5G1' or not 0 < size <= WIRE_LIMIT - 8:
            raise SourceReadError('组点暂存数据块版本或长度非法')
        expected = handle.read(32) if self._integrity else None
        body = handle.read(size)
        if len(body) != size:
            raise SourceReadError('组点暂存数据块截断')
        packet = header + body
        body = None
        if expected is not None and sha256(packet).digest() != expected:
            raise SourceReadError('组点暂存完整性校验失败')
        # 归并读回是事件唯一一次完整解码（A2-6）。
        decoded = decode_points(packet)
        if decoded.file_index != index or decoded.number != self._numbers[index]:
            raise SourceReadError('组点暂存块序号或文件身份不符')
        self._numbers[index] += 1
        self._eof[index] = decoded.eof
        return decoded

    def close(self):
        """关闭句柄、删除登记的暂存文件和目录并退还归并预约。

        参数: 无。返回: None；成功后幂等。
        异常: 删除或rmdir失败时OSError原样抛出（目录中有未登记文件时rmdir失败，不递归删除），保留owner供重试。
        """
        if self._closed:
            return
        for group in (self._writers, self._readers):
            for handle in group.values():
                handle.close()
            group.clear()
        for index in list(self._paths):
            self._paths[index].unlink(missing_ok=True)
            self._paths.pop(index)
        if self._root is not None:
            self._root.rmdir()
            self._root = None
        _release_owned_ram(self, self._merge_cost, '_merge_cost')
        self._closed = True
