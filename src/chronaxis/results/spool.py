"""用有限缓冲暂存当前平坦结果，再按稳定业务键完成有界外部归并。

只为请求的表创建文件，每个缓冲先付编码与排序所需费用，再写JSONL。
活动/片段须已形成最终事实；此模块不读取原日志或调用解码器。
归并每次处理两路且只持当前行，路径按层次和计数生成，不保存全部run列表。
失败关闭句柄并清理自有RAM，保留原错误和可重试的最高所有者。
文件生命周期由结果所有者管理；本层不删除用户文件或仍有消费者的暂存。
"""

# 归并只使用标准库文件和固定模型；文件名根据常量表名/层次/计数构造。
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from .budget import ResourceBudget, _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from .codec import decode_row, encode_row, estimate_row_bytes
from .rows import ResultRow, row_table, row_sort_key
from .summary import SUMMARY_MODELS
from .owned_directory import directory_identity
from .errors import AnalysisError, BudgetExceededError, ResultClosedError, ResultFormatError

TABLES = ('events', 'segments', 'calculations')


def _buffer_key(item):
    """取已缓存排序键，避免sort期间生成无界的新对象树。

    参数: item为键/bytes/已付金额的tuple。返回: tuple键。
    异常: 内部结构错误直接传播。
    """
    return item[0]


class ResultSpool:
    """保存building/analysis_complete/failed/cancelled状态及本次固定启用表计数。

    序号必须严格递增；每个缓冲排序后写run，seal完成预算内有界归并。
    不接受已有工作目录，不删除任何暂存；close取消未完成构建。
    路径记录只含有限请求表的当前层和run数量，不随结果数保留Python路径列表。
    _fixed_cost/_pending_cost/_buffer_cost/_merge_cost合计为_held_cost，仅含自有RAM。
    _closing拒绝半关闭继续构建；_closed只有全部自有费用实际释放后才成立。
    """

    def __init__(self, budget: ResourceBudget, work_dir=None, result_buffer_rows: int = 4096, *, enable_sequences: bool = False, requested_tables=None, failure_diagnostics=True, enable_contributions=False, enable_trace=False,enable_selections=False):
        """创建唯一工作目录并预留固定状态成本。

        参数: budget为共享账本；work_dir为全新目录或None；result_buffer_rows为行上限；
            enable_sequences为原生bool，按需增加独立配对结果表；requested_tables可明确取其子集，未请求表不创建；failure_diagnostics决定是否另写失败文件。
            enable_contributions/enable_trace/enable_selections按请求增加对应表。
        返回: ResultSpool。异常: ValueError/TypeError为配置；预算/目录/取消原样传播；
            持续清理失败附result_spool_cleanup_owner。已有目录保持原样，不写失败诊断。
        """
        if not isinstance(budget, ResourceBudget) or type(result_buffer_rows) is not int or result_buffer_rows <= 0:
            raise ValueError('暂存需ResourceBudget和正原生缓冲行数')
        if type(enable_sequences) is not bool:
            raise TypeError('enable_sequences需要原生bool')
        if type(failure_diagnostics) is not bool:
            raise TypeError('失败诊断开关需要bool')
        if type(enable_contributions) is not bool or type(enable_trace) is not bool or type(enable_selections) is not bool:
            raise TypeError('精简贡献/输入追溯开关需要bool')
        available = (TABLES + (('sequences',) if enable_sequences else ())
                     + (('contributions',) if enable_contributions else ()) + (('input_trace',) if enable_trace else ())
                     + (('selections',) if enable_selections else ()))
        if requested_tables is not None and (type(requested_tables) is not tuple
                or any(type(table) is not str or table not in available for table in requested_tables)
                or len(set(requested_tables)) != len(requested_tables)):
            raise ValueError('请求结果表需已启用白名单中的不重复tuple')
        # 所有可清理字段先于首次预算调用，未返回的对象也能保存真实申请归属。
        self.budget = self._budget = budget
        self.path = None
        self._directory_identity = None
        self._failure_diagnostics = failure_diagnostics
        self._buffer = []
        self._row_limits = None
        self._merge_run_resources = None
        self._fixed_cost = self._pending_cost = self._buffer_cost = self._merge_cost = self._held_cost = 0
        self._identity_cost = 0
        self._closed = self._closing = False
        self._summary_row_count = 0  # 仅已实际写入的精简行计数，不重扫文件判断格式。
        self._summary_versions = {}  # 有限schema版本集合，随成功append登记，不扫描结果。
        self.identity_summary = None  # 三个共同身份；出现多个值时该位置为None，不保留所有身份。
        self.state = 'building'
        self.tables = available if requested_tables is None else requested_tables
        try:
            # 固定描述与可选配对表状态先预付后创建。
            _reserve_owned_ram(self, 4096 + (4096 if enable_sequences else 0), '_fixed_cost')
            # 只在成功新建后记录自有目录；已有路径拒绝时不向它写入或删除任何文件。
            if work_dir is None:
                path = Path(tempfile.mkdtemp(prefix='chronaxis-result-'))
            else:
                path = Path(work_dir).absolute()
                path.mkdir(parents=True, exist_ok=False)
            self.path = path
            if requested_tables is not None:
                self._directory_identity = directory_identity(path)
            self.result_buffer_rows = result_buffer_rows
            # 原行上限与两路读取余量保持；这些是需求值，实际已付费用另在槽位中。
            self.max_row_bytes = max(1, budget.memory_budget_bytes // 256)
            self.reader_cost = self.max_row_bytes * 64 + 8192
            self._runs = dict.fromkeys(self.tables, 0)
            self.counts = dict.fromkeys(self.tables, 0)
            # 启用表的固定小字典包含在原固定状态费；只记成功追加的编码行长，
            # 不保存每run/每行索引，也不改变任何表的编码硬上界。
            self._row_limits = dict.fromkeys(self.tables, 0)
            self.files = {}
            self._last_sequence = -1
            self.peak_buffer_rows = 0
        except BaseException as exc:
            _cleanup_owner(self, exc, 'result_spool_cleanup_owner', '结果暂存构造')
            raise

    def _require_building(self) -> None:
        """拒绝关闭或已封口后的追加，保持最终结果不变。

        参数: 无。返回: None。异常: ResultClosedError/AnalysisError为状态不符。
        """
        if self._closed or self._closing:
            raise ResultClosedError('结果暂存已关闭或正在清理')
        if self.state != 'building':
            raise AnalysisError(f'不能追加到{self.state}暂存')

    def row_limit(self, table: str) -> int:
        """提供本表成功追加的实际最大行长，所有表仍受原编码硬限约束。

        参数: table为本次启用的固定表名。返回: 正bytes上界，空表为1。
        异常: ResultFormatError为未知表或内部行长越界；不读取文件猜大小。
        """
        # 此界仅来自成功encode；损坏文件不能用stat扩容后继续解码。
        if table not in self.tables:
            raise ResultFormatError('未启用的结果表')
        maximum = max(1, self._row_limits[table])
        if type(maximum) is not int or not 1 <= maximum <= self.max_row_bytes:
            raise ResultFormatError('结果表已知最大行长非法')
        return maximum

    def reader_cost_for(self, table: str) -> int:
        """按已知表上界预付解析及FD空间，原64倍工作费不降低。

        参数: table为固定表名。返回: 整数bytes。
        异常: 沿row_limit的类型/上界检查；不创建reader或分配数组。
        """
        # 按本表最大已编码行预付解码工作区及一个实际文件缓冲。
        cost = self.row_limit(table) * 64 + 8192
        return max(16384, cost)

    def append(self, row: ResultRow) -> None:
        """预算检查后编码并暂存一行，必要时先释放已有缓冲。

        参数: row为最终typed行且sequence严格递增。返回: None。
        异常: AnalysisError/预算/格式错误；失败后不再接受追加。
        """
        try:
            # 公共入口始终使用原模型检查；内部复用不会让调用者提交私有事实。
            self._append_core(row)
        finally:
            row = None

    def _append_core(self, row) -> None:
        """预算先于编码，成功登记后再按有限行数落盘。

        参数: row为当前冻结行。返回: None。异常: 原预算/格式/IO/取消错误。
        pending金额在安装时转入buffer槽；失败只清本对象费用和借入引用。
        """
        try:
            self._require_building()
        except BaseException:
            row = None
            raise
        try:
            table = row_table(row)
            if table not in self.tables:
                raise ResultFormatError('本次结果暂存未启用该表')
            if table in self.files:
                raise ResultFormatError('该结果表已完成，不能继续追加')
            if row.sequence <= self._last_sequence:
                raise ResultFormatError('结果sequence必须严格递增且不重复')
            cost = estimate_row_bytes(row)
            if self._buffer and self.budget.ram_bytes + cost > self.budget.memory_budget_bytes:
                self._flush()
            _reserve_owned_ram(self, cost, '_pending_cost')
            payload = encode_row(row, self.max_row_bytes)
            key = (table, row_sort_key(row))
            self._buffer.append((key, payload, cost))
            # 同一owner内转移实际已付费用，不重复申请或提前释放缓冲的归属。
            self._buffer_cost += self._pending_cost
            self._pending_cost = 0
            self._last_sequence = row.sequence
            self.counts[table] += 1
            self._summary_row_count += 1
            self._summary_versions.setdefault(table, set()).add(SUMMARY_MODELS[type(row)][2])
            # 同次已计算行顺带维护固定大小身份摘要，导出无需为省略重复身份再扫描明细。
            identity = (row.dataset_id, row.entity_id, row.session_id)
            if self.identity_summary is None:
                _reserve_owned_ram(self, 256 + 8 * sum(len(value) for value in identity), '_identity_cost')
                self.identity_summary = identity
            else:
                self.identity_summary = tuple(old if old == new else None
                                              for old, new in zip(self.identity_summary, identity))
            self._row_limits[table] = max(self._row_limits[table], len(payload))
            self.peak_buffer_rows = max(self.peak_buffer_rows, len(self._buffer))
            row = payload = key = None
            if len(self._buffer) >= self.result_buffer_rows:
                self._flush()
        except BaseException as exc:
            row = payload = key = None
            self._fail(exc)
            raise
        finally:
            row = payload = key = None

    def _run_path(self, table: str, level: int, index: int) -> Path:
        """以受控常量和计数生成run路径，不接受用户行中的路径。

        参数: table为固定表名，level/index为内部整数。返回: Path。
        异常: 无；只生成路径，不创建文件。
        """
        return self.path / f'{table}-L{level}-{index:012d}.jsonl'

    def _write_bytes(self, handle, payload: bytes) -> None:
        """配额预留后完整写bytes，短写继续，零写明确失败。

        参数: handle为有限缓冲或无缓冲二进制输出；payload为有限行。返回: None。
        异常: BudgetExceededError/OSError为配额、磁盘满或短写失败。
        """
        view = None
        try:
            self.budget.reserve_spool(len(payload))
            view = memoryview(payload)
            while view:
                # FileIO可能短写；不能把部分写入当成成功结果。
                written = handle.write(view)
                if not written:
                    raise OSError('结果暂存写入未推进')
                view = view[written:]
        finally:
            # 不调用可能再抛错的view.release；只断本层借入引用和真实memoryview。
            view = payload = handle = self = None

    def _clear_buffer(self) -> None:
        """抵销所有缓冲申请并释放对象，不删除已写文件。

        参数: 无。返回: None。异常: 原释放/取消传播，真实未抵销费用可由close重试。
        """
        # 先丢本层缓冲引用，再一次抵销实际缓冲总费，避免逐条释放后仍留旧费用tuple。
        self._buffer.clear()
        _release_owned_ram(self, self._buffer_cost, '_buffer_cost')

    def _flush(self) -> None:
        """将有限缓冲排序并按表依次写run，异常也释放RAM。

        参数: 无。返回: None。异常: 文件或预算错误原样传播。
        """
        # Timsort键/临时指针已包含每行保守估算；同时只开一个输出句柄。
        failure = None
        try:
            self._buffer.sort(key=_buffer_key)
            with ExitStack() as stack:
                table = None
                handle = None
                for key, payload, _ in self._buffer:
                    if key[0] != table:
                        if handle is not None:
                            handle.close()
                        table = key[0]
                        run_path = self._run_path(table, 0, self._runs[table])
                        handle = stack.enter_context(run_path.open('xb', buffering=0))
                        self._runs[table] += 1
                    self._write_bytes(handle, payload)
        except BaseException as exc:
            failure = exc
            raise
        finally:
            # 清理取消不能替代写入原错误；未成功清账的buffer费用仍保留在当前owner。
            key = payload = None
            try:
                self._clear_buffer()
            except BaseException as cleanup:
                if failure is None:
                    raise
                failure.add_note(f'暂存缓冲清理附加失败: {type(cleanup).__name__}')

    def _read_entry(self, handle, maximum=None):
        """有界读取一行，按当前格式重建稳定键。

        参数: handle为实际二进制文件；maximum是已付行上界，省略时用硬限。
        返回: (排序键, 原bytes)，EOF返回None。异常: 超限、缺换行、格式或IO原错。
        """
        maximum = self.max_row_bytes if maximum is None else maximum
        payload = row = None
        try:
            payload = handle.readline(maximum + 1)
            if not payload:
                return None
            if len(payload) > maximum or len(payload) > self.max_row_bytes or not payload.endswith(b'\n'):
                raise ResultFormatError('暂存行超限或缺少完整换行')
            row = decode_row(payload, maximum)
            return row_sort_key(row), payload
        finally:
            # 原TB保留，但释放读槽后不继续借持解码对象或大字节串。
            payload = row = None

    def _merge(self, left: Path, right: Path | None, destination: Path, *, table=None) -> None:
        """用双路预算，将真实FD关闭与恢复交给共用归并owner。

        参数: left/right为原有限输入，destination为新run，table为固定表或None（采用全局硬限）。
        返回: None。异常: 原格式、预算、IO或取消；持续关闭失败保实际owner供重试。
        """
        from .merge_runs import merge_runs
        merge_runs(self, (left,) if right is None else (left, right), destination, table=table)

    def seal(self) -> None:
        """落盘并完成有限外部排序，成功后标analysis_complete。

        参数: 无；调用侧应已完成结果生成并交付最终行。
        返回: None，files保存本次固定表的最终排序路径。异常: 失败标failed并关闭资源。
        """
        self._require_building()
        try:
            self._flush()
            for table in self.tables:
                self._seal_table(table)
            self.state = 'analysis_complete'
        except BaseException as exc:
            self._fail(exc)
            raise

    def _seal_table(self,table):
        """完成一个有后续消费者的最终表，其他表仍可追加，不另复制中间阶段。

        参数: 本次已启用表名。返回: 最终有序路径；重复调用复用同一文件。
        异常: 未启用表/写入/排序失败；调用方按原运行资源树清理。
        """
        self._require_building()
        if table not in self.tables:
            raise ResultFormatError('不能封存未启用结果表')
        if table in self.files:
            return self.files[table]
        self._flush()
        count, level = self._runs[table], 0
        if count == 0:
            # 空表仍有真实文件，发布时可验证三表齐全。
            self._run_path(table, 0, 0).touch(exist_ok=False)
            count = 1
        while count > 1:
            # 只保留整数层次/数量，路径按索引生成，RAM不随run数增长。
            for index in range(0, count, 2):
                destination = self._run_path(table, level + 1, index // 2)
                right = self._run_path(table, level, index + 1) if index + 1 < count else None
                self._merge(self._run_path(table, level, index), right, destination, table=table)
            count = (count + 1) // 2
            level += 1
        self.files[table] = self._run_path(table, level, 0)
        return self.files[table]

    def _fail(self, exc: BaseException) -> None:
        """保存明确失败状态，诊断写失败不能掩盖原异常。

        参数: exc为原失败。返回: None。异常: 无正常新增异常。
        """
        self.state = 'cancelled' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failed'
        # 失败状态阻止继续追加，清理错误只作为附注；尚未释放费用由实际owner保留。
        try:
            self._clear_buffer()
        except BaseException as cleanup:
            exc.add_note(f'暂存失败缓冲清理附加失败: {type(cleanup).__name__}')
        if self._merge_run_resources is not None:
            try:
                self._merge_run_resources.close()
            except BaseException as cleanup:
                exc.add_note(f'多路归并真实资源清理附加失败: {type(cleanup).__name__}')
                exc.result_spool_cleanup_owner = self
        self.identity_summary = None
        for slot in ('_pending_cost', '_merge_cost', '_identity_cost'):
            if slot == '_merge_cost' and self._merge_run_resources is not None:
                # helper仍持真实未关FD或未清费用，不能从父层提前抵销同一读槽。
                continue
            try:
                _release_owned_ram(self, getattr(self, slot), slot)
            except BaseException as cleanup:
                exc.add_note(f'暂存失败{slot}清理附加失败: {type(cleanup).__name__}')
        if self._pending_cost or self._buffer_cost or self._merge_cost or self._identity_cost or self._merge_run_resources is not None:
            exc.result_spool_cleanup_owner = self
        if not self._failure_diagnostics:
            return
        try:
            # 小型独立诊断不计作完成清单；磁盘满/配额不足时仅保留对象状态。
            data = json.dumps({'status': self.state, 'error_type': type(exc).__name__,
                               'resources': self.budget.snapshot()}, ensure_ascii=False).encode()
            with (self.path / 'failure.json').open('xb', buffering=0) as handle:
                self._write_bytes(handle, data)
        except BaseException as diagnostic:
            # 原诊断失败也不能覆盖业务错误；磁盘/配额原限制保持，其余错误留下附注。
            if not isinstance(diagnostic, (OSError, BudgetExceededError)):
                exc.add_note(f'暂存失败诊断附加失败: {type(diagnostic).__name__}')

    def close(self) -> None:
        """取消未完成构建，或释放封口对象的固定RAM；重复关闭安全。

        参数: 无。返回: None。异常: 原释放/取消传播，未释放金额保留，重复关闭可重试。
        """
        if self._closed:
            return
        # 开始清理即拒绝新构建；只释放实际自有槽位，不抵销共享账本中的借用余额。
        self._closing = True
        if self._merge_run_resources is not None:
            try:
                self._merge_run_resources.close()
            except BaseException as exc:
                exc.result_spool_cleanup_owner = self
                raise
        self._clear_buffer()
        if self.state == 'building':
            self.state = 'cancelled'
        self.identity_summary = None
        try:
            for slot in ('_pending_cost', '_merge_cost', '_identity_cost', '_fixed_cost'):
                _release_owned_ram(self, getattr(self, slot), slot)
        finally:
            # 释放后取消同样完成最小关闭；释放前取消仍可重试，不能提前closed。
            if self._held_cost == 0 and self._merge_run_resources is None:
                self._closed = True
