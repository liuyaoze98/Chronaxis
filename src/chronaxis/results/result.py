"""从封口暂存提供流式结果，关闭文件后按时间命名发布，完成清单最后出现。

输入是已排序ResultSpool与运行元数据，输出是行迭代器和OutputManifest。
CSV与JSONL使用同一套平坦摘要字段，不保留旧row_json或结果包装副本。
成功生成表、质量记录及完成清单后才安装目录；已有目标拒绝，失败保留诊断临时目录。
close关闭所有活跃迭代器且幂等；默认清理自有暂存，保留原输入和已发布文件。无旧reader/decoder/writer调用。
当前原子安装通过Windows不覆盖rename实现；其他平台明确拒绝，尚未验收的能力不静默承诺。
元数据、读槽和发布workspace分别记录实际RAM费用，预算更新后取消仍可恢复清账。
读取器真实handle.close失败保留句柄并拒绝继续读；结果close失败可重试，不提前标closed。
上述重试保证只覆盖托管的结果资源，不覆盖任意局部文件句柄的持续关闭失败。
"""

# 发布只新增本次文件；标准库逐行读写，不覆盖已有结果。
import csv
from contextlib import nullcontext
from collections.abc import Iterator
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import time
from .codec import decode_row
from .errors import (AnalysisError, BudgetExceededError, ResultClosedError, ResultFormatError,
                     ContributionsUnavailableError)
from .manifest import RunMetadata, OutputManifest
from .artifact_exports import ArtifactExportStore
from .rows import ResultRow, row_table
from .summary import (SummaryCalculationRow, SummaryEventRow, SummarySequenceRow, SummarySegmentRow,
                      SummaryContributionRow, SummarySelectionRow, SummaryInputRow, SummaryAggregationRow,
                      summary_fields, SUMMARY_MODELS, SUMMARY_COLUMNS)
from .owned_directory import directory_identity, remove_owned_directory
from .spool import ResultSpool, _reserve_owned_ram, _release_owned_ram, _cleanup_owner


def _json(value) -> str:
    """生成标准紧凑JSON文本，拒绝非有限普通数字。

    参数: value为受控JSON结构。返回: str。异常: ValueError为非法数值。
    """
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))
    finally:
        # 原异常/TB和返回值保持；只断本层临时引用，不清调用方帧。
        value = None


def _row_fields(row) -> dict:
    """提取当前平坦结果的CSV字段；数组单元格使用有限JSON文本。

    参数: row为当前登记的结果行。返回: 独立字段字典。异常: 未支持模型或非有限值错误。
    """
    try:
        result = summary_fields(row)
        for name in ('parent_event_ids','group_keys','group_values'):
            if name in result:
                result[name] = _json(result[name])
        return result
    finally:
        row = result = None


class _DigestOutput:
    """借用本次已打开的输出流，同一次写入计算请求的摘要，不拥有关闭责任。"""
    def __init__(self,stream):
        """建立固定状态。参数: 文本或二进制流。返回: owner。异常: 哈希构造错。"""
        self.stream=stream;self.digest=hashlib.sha256();self.size=0

    def write(self,payload):
        """完整写出有限payload后更新摘要。参数: str/bytes。返回: 原长度。异常: 短写/IO。"""
        count=self.stream.write(payload)
        if count!=len(payload): raise OSError('结果写入不完整')
        encoded=payload.encode('utf-8') if isinstance(payload,str) else payload
        self.digest.update(encoded);self.size+=len(encoded)
        return count

    def info(self,name):
        """返回已关闭文件的有限事实。参数: 文件名。返回: dict。异常: 无。"""
        return dict(name=name,bytes=self.size,sha256=self.digest.hexdigest())


class _RowIterator:
    """独立文件位置的有限行迭代器，实际读槽与文件关闭完成后才closed。

    _reader_cost为实际已付槽位，_held_cost仅含本迭代器费用。关闭中的迭代器仍在
    owner登记中，成功关handle后再抵销费用、解除登记；失败可由本对象或父close重试。
    handle及内部发布模式的_index_handle保留真实文件，所有实际FD关闭后才抵销读槽。
    """

    def __init__(self, owner, table: str):
        """先预留解码槽位，再打开只读暂存并登记活跃资源。

        参数: owner为AnalysisResult，table为固定表名；publication只供内部legacy JSONL发布。
        返回: 公共typed行迭代器，内部发布模式返回已核完整原行对应的有限质量字段。
        异常: 预算/IO/取消原样传播；持续清理失败附row_iterator_cleanup_owner，父登记仍可达。
        """
        owner._require_open()
        self.owner, self.table, self.closed = owner, table, False
        # 在首次预约前准备可清理字段；父元数据覆盖这个尚无读槽的小登记引用。
        self._budget, self._held_cost, self._reader_cost = owner.spool.budget, 0, 0
        self.handle, self._handle_closed, self._closing = None, True, False
        self._payload = None
        if table not in owner.spool.tables:
            if table not in SUMMARY_COLUMNS:
                raise ValueError('未注册结果表')
            # 未配置legacy是实际无文件的空游标；不登记FD、不申请读槽，但保close接口。
            self.closed = True
            return
        try:
            owner._iterators.add(self)
            # 所有表都按成功追加实长付款；原编码硬限和读前长度检查继续保留。
            self.max_row_bytes = owner.spool.row_limit(table)
            _reserve_owned_ram(self, owner.spool.reader_cost_for(table), '_reader_cost')
            self.handle = owner.spool.files[table].open('rb', buffering=8192)
            self._handle_closed = False
        except BaseException as exc:
            _cleanup_owner(self, exc, 'row_iterator_cleanup_owner', '结果读取器构造')
            raise

    def __iter__(self):
        """保持当前读取位置，不重读输入。

        参数: 无。返回: self。异常: 无。
        """
        return self

    def __next__(self) -> ResultRow | dict:
        """读取一条有限行，EOF或异常关闭资源。

        参数: 无。返回: 公共typed行或内部认证发布的质量字段。异常: StopIteration/关闭/格式/IO错误。
        """
        self.owner._require_open()
        # 只借出当前严格解码过的一行原字节；下一次推进前释放，不建立结果缓存。
        self._payload = None
        if self.closed:
            raise StopIteration
        # 真实关闭失败或读槽未抵销时禁止继续借出半关闭输入。
        if self._closing:
            raise ResultClosedError('结果读取器正在清理')
        try:
            payload = self.handle.readline(self.max_row_bytes + 1)
            if not payload:
                self.close()
                raise StopIteration
            if (len(payload) > self.max_row_bytes or len(payload) > self.owner.spool.max_row_bytes
                    or not payload.endswith(b'\n')):
                raise ResultFormatError('结果行超限或未完整结束')
            row = decode_row(payload, self.max_row_bytes)
            if row_table(row) != self.table:
                raise ResultFormatError('结果暂存表与行类型不一致')
            self._payload = payload
            return row
        except BaseException as exc:
            # 解码/读取原异常优先；清理仍失败时父登记和恢复属性保存实际读取器。
            payload = row = entry = None
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note(f'结果读取器异常清理附加失败: {type(cleanup).__name__}')
                if not self.closed:
                    exc.row_iterator_cleanup_owner = self
            raise
        finally:
            # return已先求值；原TB不额外持有本层行和读取bytes。
            payload = row = entry = None

    def close(self) -> None:
        """抵销槽位、取消登记并关闭句柄；重复调用安全。

        参数: 无。返回: None。异常: 原文件关闭/预算取消传播；失败句柄与未付清费用留待重试。
        """
        if self.closed:
            return
        self._closing = True
        self._payload = None
        try:
            # FD尚未关完时保留handle及读槽；关闭后抛取消也根据真实handle.closed记录状态。
            if self.handle is not None and not self._handle_closed:
                try:
                    self.handle.close()
                finally:
                    if self.handle.closed:
                        self._handle_closed = True
            _release_owned_ram(self, self._reader_cost, '_reader_cost')
            # 未关闭资源的迭代器不能先从父登记消失；解除登记失败可由父再次close。
            self.owner._iterators.discard(self)
        finally:
            if self._handle_closed and self._held_cost == 0 and self not in self.owner._iterators:
                self.closed = True


class AnalysisResult:
    """保存一次分析的结果，提供可关闭的逐行迭代器和结果发布方法。

    内部状态初始analysis_complete，发布失败为output_failed/cancelled。
    write可重复导出到同一结果目录；每次只读暂存，不重读旧输入。
    单线程使用；执行输入和旧writer成功关闭的前置条件由AnalysisRunner负责。
    _metadata_cost/_writer_cost为实际已付费用；自有读取器各自持有读槽，spool持有其
    固定/缓冲/归并费用。close进入_closing后拒绝读取或发布，所有层成功关闭才_closed。
    """

    def __init__(self, spool: ResultSpool, metadata: RunMetadata, table_format: str = 'csv', *, artifact_exports=None,
                 owned_work=None):
        """接管已封口暂存并写analysis_complete内部清单。

        参数: spool为已完成暂存，metadata为真实运行事实，table_format为csv/jsonl/readable_csv；
            低层构造器保留csv默认以兼容现有调用，普通配置与AnalysisRunner默认readable_csv。
            artifact_exports为独立信号/报文导出仓；同样接管、按索引复制并校验、关闭。
            owned_work仅为新会话移交的私有根及创建身份，须为spool直接父目录；默认只接管spool目录。
        返回: None；初始化实例状态。异常: 配置拒绝前不接管spool；资源失败保原取消或原
            AnalysisError包装，持续清理失败附analysis_result_cleanup_owner供实际恢复。
        """
        if (not isinstance(spool, ResultSpool) or spool.state != 'analysis_complete'
                or spool._closed or spool._closing):
            raise AnalysisError('AnalysisResult需要已封口且未关闭的暂存')
        if not isinstance(metadata, RunMetadata) or table_format not in ('csv', 'jsonl', 'readable_csv'):
            raise ValueError('结果需RunMetadata和csv/jsonl/readable_csv格式')
        if owned_work is not None:
            if ((type(owned_work) is not tuple) or (len(owned_work) != 2) or (Path(owned_work[0]).resolve() != spool.path.resolve().parent) or (directory_identity(owned_work[0]) != owned_work[1])):
                raise ValueError('结果只能接管同次新会话登记的spool直接父目录')
        if (set(spool.tables) - set(SUMMARY_COLUMNS) or spool._summary_row_count != sum(spool.counts.values())
                or spool._directory_identity is None):
            raise ValueError('当前结果只接受已登记的精简表及对应行，不能混入旧完整结果')
        if artifact_exports is not None and (type(artifact_exports) is not ArtifactExportStore
                or artifact_exports._budget is not spool.budget or artifact_exports.closed or artifact_exports.state!='sealed'
                or artifact_exports.session_id not in (set(metadata.session_ids))):
            raise ValueError('新导出仓需同预算、同会话且封口')
        # 校验通过后才接管spool；首次预约前安装全部清理字段，已付费用从0开始。
        self.spool, self.metadata, self.table_format = spool, metadata, table_format
        self._work_removed = (metadata.retain_work)
        self._owned_work = owned_work or (spool.path, spool._directory_identity)
        self._pending_output_cleanup = None
        self._readable_writer = None  # 发布失败时保留真实索引所有者，供close重试。
        self._published_counts = None
        self._presentation = None
        self._contributions_omitted = 'contributions' not in spool.tables
        self._output_tables = spool.tables
        self._artifact_exports=artifact_exports
        self._budget, self._held_cost, self._metadata_cost, self._writer_cost = spool.budget, 0, 0, 0
        self._iterators = set()
        self._closed = self._closing = False
        self._failure_count = 0
        self.status = 'analysis_complete'
        self.manifest_path = spool.path / 'analysis_manifest.json'
        if (not (metadata.detailed_diagnostics or metadata.retain_work)):
            self.manifest_path = None
        try:
            expected = metadata.estimated_bytes()
            if owned_work is not None:
                expected += 4096 + 64 * len(str(owned_work[0]))
            if artifact_exports is not None:
                expected+=65536+64*len(str(artifact_exports.path))
            _reserve_owned_ram(self, expected, '_metadata_cost')
            self._write_state(self.manifest_path, self.status)
        except BaseException as exc:
            spool._fail(exc)
            _cleanup_owner(self, exc, 'analysis_result_cleanup_owner', '结果对象构造')
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            # 保持原非取消异常包装；未返回owner同时挂在外层，调用方无需猜测异常链。
            error = AnalysisError('结果内部清单写入失败')
            recovery = getattr(exc, 'analysis_result_cleanup_owner', None)
            if recovery is not None:
                error.analysis_result_cleanup_owner = recovery
                error.add_note('释放恢复后调用analysis_result_cleanup_owner.close()')
            raise error from exc

    def _require_open(self) -> None:
        """拒绝关闭后迭代/发布，不自动重新打开已关闭对象。

        参数: 无。返回: None。异常: ResultClosedError。
        """
        if self._closed or self._closing or self.spool._closed or self.spool._closing:
            raise ResultClosedError('AnalysisResult已关闭或正在清理')

    def _manifest(self, status: str, outputs=(), coverage=None) -> dict:
        """构造有界清单副本，分开分析状态与发布状态。

        参数: status为实际状态，outputs为固定文件记录，coverage为固定状态计数。
        返回: dict；元数据转换成本已申请。异常: 无预期异常。
        """
        manifest = {'status': status, 'run': self.metadata.to_dict(), 'python_version': platform.python_version(),
                'ended_at': datetime.now(timezone.utc).isoformat(), 'error_counts': {'output': self._failure_count},
                'row_counts': {table: self.spool.counts[table] for table in self._output_tables},
                'resources': self.spool.budget.snapshot(),
                'result_buffer_rows': self.spool.result_buffer_rows, 'peak_buffer_rows': self.spool.peak_buffer_rows,
                'table_format': self.table_format, 'outputs': list(outputs)}
        if (self.metadata.retain_work):
            manifest['spool_path'] = str(self.spool.path)
            manifest['spool_files'] = {table: str(self.spool.files[table]) for table in self._output_tables}
        if (self.metadata.detailed_diagnostics):
            manifest['coverage'] = coverage or {}
        defaults={table:version for table,_,version in reversed(tuple(SUMMARY_MODELS.values()))}
        versions={table:sorted(self.spool._summary_versions.get(table,{defaults[table]})) for table in self.spool.tables}
        versions={table:values[0] if len(values)==1 else values for table,values in versions.items()}
        if all(type(v) is int for v in versions.values()) and len(set(versions.values())) == 1:
            manifest['row_schema_version'] = next(iter(versions.values()))
        else:
            manifest['row_schema_versions'] = versions
        if self._artifact_exports is not None:
            manifest['exports']={'index_file':'exports.jsonl','directory':'exports',
                'record_count':self._artifact_exports.count,'device_label':self._artifact_exports.device_label}
        if self.table_format == 'readable_csv':
            from .readable_format import seconds, outcome_messages
            # 可读表不是旧行模型的逐行副本；以实际发布行数和专用表示版本为准。
            manifest.pop('row_schema_version', None)
            manifest.pop('row_schema_versions', None)
            if self._published_counts is not None:
                manifest['row_counts'] = dict(self._published_counts)
            if self._presentation is not None:
                manifest['presentation'] = self._presentation
            manifest['result_messages'] = outcome_messages(self.metadata.analysis_outcome)
            run = manifest['run']
            if 'session_boundaries' in run:
                run['session_boundaries_seconds'] = [(name, seconds(start), seconds(end))
                    for name, start, end in run.pop('session_boundaries')]
            # 调试资源仍在显式诊断中提供，普通结果先呈现实际文件和业务概况。
            if not self.metadata.detailed_diagnostics:
                for key in ('python_version', 'resources', 'result_buffer_rows', 'peak_buffer_rows'):
                    manifest.pop(key, None)
        return manifest

    @property
    def run_manifest(self) -> dict:
        """返回当前状态快照，发布失败诊断路径另见manifest_path。

        参数: 无。返回: 独立小型dict。异常: 关闭后仍可查看诊断，不读文件。
        """
        return self._manifest(self.status)

    def _write_state(self, path: Path, status: str) -> None:
        """追加状态清单到暂存，每份保留且计入累计配额。

        参数: path为本任务全新清单路径，status为实际状态。返回: None。
        异常: 配额/IO失败；不能生成虚假completed。
        """
        try:
            if (not (self.metadata.detailed_diagnostics or self.metadata.retain_work)):
                return
            payload = (_json(self._manifest(status)) + '\n').encode('utf-8')
            if len(payload) > self.spool.max_row_bytes:
                raise BudgetExceededError('运行清单超过有限元数据大小')
            with path.open('xb', buffering=0) as handle:
                self.spool._write_bytes(handle, payload)
        finally:
            # 失败状态诊断也只断本层文本/输入，保原IO错误与实际写次数。
            payload = self = path = status = None

    def iter_events(self) -> Iterator[SummaryEventRow]:
        """创建独立事件流，不装入全量列表。

        参数: 无。返回: SummaryEventRow迭代器。异常: ResultClosedError表示结果已关闭或正在关闭；BudgetExceededError表示无法为游标分配预算。
            创建或迭代期间OSError表示暂存文件读取失败，ResultFormatError表示暂存行格式损坏。
        """
        return _RowIterator(self, 'events')

    def iter_sequences(self) -> Iterator[SummarySequenceRow]:
        """逐行读取请求配对结果；未配置配对时返回可关闭空游标。

        参数: 无。返回: SummarySequenceRow迭代器。异常: ResultClosedError表示结果已关闭或正在关闭；BudgetExceededError表示无法为游标分配预算。
            创建或迭代期间OSError表示暂存文件读取失败，ResultFormatError表示暂存行格式损坏。
        """
        return _RowIterator(self, 'sequences')

    def iter_segments(self) -> Iterator[SummarySegmentRow]:
        """创建独立片段流，保留全部父事件关联。

        参数: 无。返回: SummarySegmentRow迭代器。异常: ResultClosedError表示结果已关闭或正在关闭；BudgetExceededError表示无法为游标分配预算。
            创建或迭代期间OSError表示暂存文件读取失败，ResultFormatError表示暂存行格式损坏。
        """
        return _RowIterator(self, 'segments')

    def iter_calculations(self) -> Iterator[SummaryCalculationRow]:
        """创建计算摘要行流；同时检查value、unit、status、reason和quality。

        参数: 无。返回: SummaryCalculationRow迭代器。异常: ResultClosedError表示结果已关闭或正在关闭；BudgetExceededError表示无法为游标分配预算。
            创建或迭代期间OSError表示暂存文件读取失败，ResultFormatError表示暂存行格式损坏。
        """
        return _RowIterator(self, 'calculations')


    def iter_contributions(self) -> Iterator[SummaryContributionRow]:
        """逐行回查真实贡献与skip，原序号和新求值序号分别保留。

        参数: 无。返回: 独立有预算游标；逐行返回SummaryContributionRow。
        异常: ContributionsUnavailableError表示本次明确不生成明细；关闭、预算、
            IO或格式错误仍保留。原输入/解码器/求值器均不再调用。
        """
        self._require_open()
        if self._contributions_omitted:
            raise ContributionsUnavailableError('本次未生成贡献明细；请将outputs.contributions设为full后重新运行')
        return _RowIterator(self, 'contributions')

    def iter_aggregations(self) -> Iterator['SummaryAggregationRow']:
        """按组读取聚合行及总体计数。参数: 无。返回: 受结果生命周期约束的迭代器。异常: 关闭或解码错误。"""
        return _RowIterator(self,'aggregations')

    def iter_selections(self) -> Iterator[SummarySelectionRow]:
        """读取明确请求的真实样本选择行。参数: 无。返回: 有预算游标，未请求为空。异常: ResultClosedError表示结果关闭；BudgetExceededError表示游标预算不足；
            迭代时ResultFormatError表示暂存格式损坏，OSError表示文件读取失败。"""
        return _RowIterator(self,'selections')

    def iter_input_trace(self) -> Iterator[SummaryInputRow]:
        """读取显式请求的所需输入追溯。参数: 无。返回: 按行产生SummaryInputRow的可关闭游标。
        异常: ResultClosedError表示结果已关闭；AnalysisError表示未请求diagnostics.trace。
            迭代期间可能因暂存损坏报告ResultFormatError，或传播OSError及预算错误。"""
        self._require_open()
        if 'input_trace' not in self.spool.tables:
            raise AnalysisError('本次未生成输入追溯；请设置diagnostics.trace后重新运行')
        return _RowIterator(self,'input_trace')

    @property
    def contributions_available(self) -> bool:
        """说明本结果是否允许查询逐消息贡献，不将未生成和零行混为一谈。

        参数: 无。返回: bool；默认未配置逐消息指标仍允许原空游标。
        异常: 无；关闭后可查看这项固定运行事实，但不能重新创建游标。
        """
        return not self._contributions_omitted

    def _write_table(self, table: str, destination: Path, quality_handle, coverage: dict):
        """逐行生成单表和质量记录，异常或EOF关闭读取句柄。

        参数: table为固定表，destination为新文件，quality_handle为质量输出。
        返回: 请求摘要时为文件事实，否则None。异常: 预算/编码/写入错误传播，输出with保证关闭。
        """
        iterator = _RowIterator(self, table)
        count = 0
        failure = None
        digest_output = None
        try:
            mode = 'x' if self.table_format == 'csv' else 'xb'
            options = {'encoding': 'utf-8', 'newline': ''} if mode == 'x' else {}
            with destination.open(mode, **options) as output:
                # 新版只在明确请求时随写摘要；CSV使用newline空串，无平台换行二次转换。
                if (self.metadata.integrity_diagnostics):
                    digest_output=_DigestOutput(output);output=digest_output
                columns = SUMMARY_COLUMNS[table]
                versions=self.spool._summary_versions.get(table,())
                if 16 in versions:
                    columns=columns+('extension_version',)
                if 10 in versions or 16 in versions:
                    columns=columns+('coverage_status',)
                writer = csv.DictWriter(output, fieldnames=columns) if mode == 'x' else None
                if writer is not None:
                    writer.writeheader()
                for row in iterator:
                    # 普通/CSV路径已完整解码；内部legacy发布已核本次完整行证据。
                    # 直接复用原字节，公共iterator仍交付严格模型，全部业务字段原样保留。
                    payload = iterator._payload
                    fields = ((_row_fields(row) if writer is not None else summary_fields(row)) if (writer is not None or quality_handle is not None)
                              else None)
                    if writer is not None:
                        writer.writerow(fields)
                    else:
                        output.write(payload)
                    # 状态/覆盖分布仅使用固定有限键，不按任意signal/rule建立无限dict。
                    if quality_handle is not None:
                        state_field = {'selections': 'selection', 'contributions': 'reason',
                                       'input_trace': 'record_type'}.get(table, 'status')
                        state_key = table + ':' + fields[state_field]
                        coverage[state_key] = coverage.get(state_key, 0) + 1
                        quality_record = {key: fields[key] for key in ('sequence', 'dataset_id', 'entity_id', 'session_id', 'quality', state_field)}
                        quality_record['table'] = table
                        for key in ('selection', 'value_coverage', 'condition_coverage', 'requested_coverage', 'coverage_status'):
                            if key in fields:
                                quality_record[key] = fields[key]
                        quality_handle.write(_json(quality_record) + '\n')
                    count += 1
            if count != self.spool.counts[table]:
                raise ResultFormatError('输出表行数与分析暂存不一致')
            return digest_output.info(destination.name) if digest_output is not None else None
        except BaseException as exc:
            failure = exc
            raise
        finally:
            # 输出/编码原错误不能被读槽收尾取消覆盖，失败读取器仍留父登记供close。
            row = fields = payload = quality_record = None
            try:
                iterator.close()
            except BaseException as cleanup:
                if failure is None:
                    raise
                failure.add_note(f'发布表读取器清理附加失败: {type(cleanup).__name__}')

    def _file_info(self, path: Path) -> dict:
        """以固定读取块计算新输出哈希，不保留全文件内容。

        参数: path为已关闭输出文件。返回: 名称/bytes/SHA256。
        异常: IO错误；调用侧已预留发布临时槽位。
        """
        if (not self.metadata.detailed_diagnostics):
            return {'name': path.name, 'bytes': path.stat().st_size}
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            while chunk := handle.read(65536):
                digest.update(chunk)
        return {'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}

    def _install_directory(self, temporary: Path, destination: Path) -> None:
        """在Windows同文件系统安装单个文件或目录，短暂占用时有限等待且拒绝覆盖。

        参数: temporary为目标父目录临时目录，destination为全新目标。
        返回: None。异常: AnalysisError为未支持平台；FileExistsError/IO错误为安装失败。
        边界: 仅原rename的Win5/32最多尝试六次，五次等待合计0.77秒；
        系统调用本身不受该等待时长约束。其他错误立即传播，最终保留原异常与源目录。
        副作用: 只重试当前路径安装，不重新读取、分析或生成任何输出文件。
        """
        # Windows rename对已存在目录拒绝；POSIX普通rename可覆盖空目录，不能静默复用。
        if os.name != 'nt':
            raise AnalysisError('原子目录安装目前只验收Windows；其他平台需不覆盖安装实现')
        delays = (.02, .05, .1, .2, .4)
        for attempt in range(len(delays) + 1):
            # 每次等待后重新保护新出现的目标；检查之后的竞争仍由Windows rename拒绝。
            if destination.exists():
                raise FileExistsError(destination)
            try:
                os.rename(temporary, destination)
                return
            except PermissionError as exc:
                # 仅恢复短暂访问/共享冲突；权限长期不允许时仍保最后真实OS错误及现场。
                if getattr(exc, 'winerror', None) not in (5, 32):
                    raise
                if attempt == len(delays):
                    exc.add_note('Windows输出安装六次均被拒绝；已等待0.77秒，保留临时目录供诊断')
                    raise
                time.sleep(delays[attempt])

    def write(self, output_dir: str | Path) -> OutputManifest:
        """从暂存发布带时间文件名的结果，完成清单最后安装。

        参数: output_dir为可复用输出目录；格式取本结果table_format。
        返回: 安装成功后的OutputManifest。异常: AnalysisError包含原错误链；关闭异常独立。
        副作用: 成功时创建正式输出目录；失败时按retain_work决定是否保留本次临时目录。
            不覆盖已有目标，不重新读取输入日志；关闭后的结果不能发布。
        """
        self._require_open()
        temporary = None
        temporary_identity = None
        publication = None
        manifest = None
        failure = None
        try:
            destination = Path(output_dir).absolute()
            if (not self.metadata.retain_work) and (destination.resolve().is_relative_to(Path(self._owned_work[0]).resolve())):
                raise ValueError('发布目录不能放在关闭后删除的本次私有工作目录内')
            from .publication import PublicationNames, output_root
            destination = output_root(destination)
            if os.name != 'nt':
                raise AnalysisError('当前未实现该平台的不覆盖原子目录安装')
            # 转换/CSV/质量/hash临时对象也计入账本，不只计算读取数组。
            _reserve_owned_ram(self, self.spool.reader_cost, '_writer_cost')
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=f'.{destination.name}.incomplete-', dir=destination.parent))
            temporary_identity = directory_identity(temporary)
            coverage = {}
            suffix = '.' + self.table_format
            # 仅发布实际请求的表；none不写空贡献文件，也不会打开其内部空暂存。
            paths = tuple(temporary / (table + suffix) for table in self._output_tables)
            quality_path = temporary / 'quality.jsonl'
            detailed = (self.metadata.detailed_diagnostics)
            quality_paths = (quality_path,) if detailed else ()
            written_infos={}
            with (quality_path.open('x', encoding='utf-8', newline='') if detailed else nullcontext(None)) as quality:
                if self.table_format == 'readable_csv':
                    from .readable import ReadableWriter
                    self._readable_writer = ReadableWriter(self, temporary, _RowIterator)
                    paths = self._readable_writer.write(quality, coverage)
                    written_infos.update(self._readable_writer.infos)
                    self._published_counts = dict(self._readable_writer.counts)
                    self._presentation = self._readable_writer.presentation()
                    self._readable_writer.close()
                    self._readable_writer = None
                else:
                    for table, path in zip(self._output_tables, paths):
                        info=self._write_table(table, path, quality, coverage)
                        if info is not None: written_infos[path.name]=info
            # 原writer在run内已关闭；发布只复制并核验现成BLF/索引，无旧I/O调用。
            extra_paths = ()
            if self._artifact_exports is not None:
                extra_paths+=(self._artifact_exports.copy_to(temporary),)
                written_infos['exports.jsonl']=self._artifact_exports.index_info
            # 所有表和质量句柄已成功关闭；清单作为最后写入内容。
            infos = tuple(written_infos[path.name] if path.name in written_infos else self._file_info(path)
                          for path in (*paths, *quality_paths, *extra_paths))
            # 文件全部关闭后分配本次名称；只改清单中的路径，不回读或改写数据行。
            publication = PublicationNames(destination, (*[p.name for p in temporary.iterdir()], 'run_manifest.json'))
            infos = tuple(dict(info, name=publication.names[info['name']]) for info in infos)
            completed = self._manifest('completed', infos, coverage)
            if 'exports' in completed:
                completed['exports'].update(index_file=publication.names['exports.jsonl'], directory=publication.names['exports'])
            completed['manifest_file'] = publication.names['run_manifest.json']
            with (temporary / 'run_manifest.json').open('x', encoding='utf-8', newline='') as handle:
                handle.write((json.dumps(completed, ensure_ascii=False, allow_nan=False, indent=2)
                              if self.table_format == 'readable_csv' else _json(completed)) + '\n')
            # 返回模型也在安装前完成校验；安装成功后仅返回，避免校验错误遗留已发布completed。
            manifest = OutputManifest(self.metadata.run_id, destination, destination / publication.names['run_manifest.json'],
                                      tuple(destination / publication.names[path.name] for path in (*paths, *quality_paths, *extra_paths)),
                                      tuple(self._published_counts.items()) if self.table_format == 'readable_csv'
                                      else tuple((table, self.spool.counts[table]) for table in self._output_tables))
            publication.publish(temporary, 'run_manifest.json', self._install_directory)
            try:
                temporary.rmdir()
            except OSError:
                # 正式清单已发布；空暂存交给已有close责任重试，不将结果谎报为未发布。
                self._pending_output_cleanup = (temporary, temporary_identity)
                self._closing = True
            self.status = 'analysis_complete'
            return manifest
        except BaseException as exc:
            failure = exc
            if publication is not None:
                try:
                    publication.close()
                except BaseException as cleanup:
                    exc.add_note('输出命名锁释放失败：' + str(cleanup))
            published_manifest = manifest if publication is not None and publication.completed else None
            if published_manifest is not None:
                exc.completed_manifest = published_manifest
            if self._readable_writer is not None:
                try:
                    self._readable_writer.close()
                    self._readable_writer = None
                except BaseException as cleanup:
                    self._closing = True
                    exc.analysis_result_cleanup_owner = self
                    exc.add_note('可读关联索引关闭失败：' + type(cleanup).__name__)
            raw_failure = False
            raw_failure=raw_failure or (self._artifact_exports is not None and
                getattr(exc,'artifact_export_store_cleanup_owner',None) is self._artifact_exports)
            if raw_failure:
                # 取消也必须保最高结果owner；不能到普通异常包装后才补这条真实责任。
                exc.analysis_result_cleanup_owner = self
            self.status = ('analysis_complete' if published_manifest is not None else
                           'cancelled' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'output_failed')
            self._failure_count += 1
            # 安装失败时移除临时completed名称，把现存清单改标incomplete；只操作本次新文件。
            if (temporary is not None) and (not self.metadata.retain_work):
                self._pending_output_cleanup = (temporary, temporary_identity)
                try:
                    remove_owned_directory(*self._pending_output_cleanup)
                    self._pending_output_cleanup = None
                except BaseException as cleanup:
                    self._closing = True
                    exc.analysis_result_cleanup_owner = self
                    exc.add_note('输出临时目录清理失败，可重试close：'+type(cleanup).__name__)
            elif temporary is not None:
                marker = temporary / 'run_manifest.json'
                try:
                    if marker.exists():
                        with marker.open('w', encoding='utf-8') as handle:
                            handle.write(_json({'status': self.status, 'run_id': self.metadata.run_id}) + '\n')
                    with (temporary / 'failure.json').open('x', encoding='utf-8') as handle:
                        handle.write(_json({'status': self.status, 'error_type': type(exc).__name__}) + '\n')
                except BaseException as diagnostic:
                    # 诊断写入失败不替换发布原错；原磁盘失败限制及incomplete目录保持。
                    if not isinstance(diagnostic, OSError):
                        exc.add_note(f'发布临时诊断附加失败: {type(diagnostic).__name__}')
            try:
                path = self.spool.path / f'output_failure-{self._failure_count:06d}.json'
                self._write_state(path, self.status)
                self.manifest_path = (None if (not (self.metadata.detailed_diagnostics or self.metadata.retain_work)) else path)
            except BaseException as diagnostic:
                if not isinstance(diagnostic, (OSError, BudgetExceededError)):
                    exc.add_note(f'发布状态诊断附加失败: {type(diagnostic).__name__}')
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            error = AnalysisError(f'结果发布失败，状态{self.status}')
            if published_manifest is not None:
                error.completed_manifest = published_manifest
            if raw_failure or self._pending_output_cleanup is not None or self._readable_writer is not None:
                # 原始复制的实际FD仍由本结果的仓持有；包装不得丢最高恢复入口。
                error.analysis_result_cleanup_owner = self
            failure = error
            raise error from exc
        finally:
            # 局部with已关闭真实输出；发布槽的实际余额由同一owner保存供失败后close。
            try:
                _release_owned_ram(self, self._writer_cost, '_writer_cost')
            except BaseException as cleanup:
                if publication is not None and publication.completed:
                    cleanup.completed_manifest = manifest
                if self._writer_cost:
                    self._closing = True
                    target = cleanup if failure is None else failure
                    target.analysis_result_cleanup_owner = self
                if failure is None:
                    raise
                failure.add_note(f'发布workspace清理附加失败: {type(cleanup).__name__}')

    def close(self) -> None:
        """关闭活跃游标并释放资源；默认清理本次自有暂存，保留原始输入与已发布结果。

        参数: 无。返回: None；重复调用安全。diagnostics.retain_work为True时保留工作现场。
        异常: 关闭失败仍尝试其余句柄，最后抛首个原错误；未完成清理时可重试close。
        """
        if self._closed:
            return
        # 清理中拒绝新读取/发布；尝试全部读取器，但不提前丢失失败句柄或自有费用。
        self._closing = True
        error = None
        for iterator in tuple(self._iterators):
            try:
                iterator.close()
            except BaseException as exc:
                if error is None:
                    error = exc
                else:
                    error.add_note(f'其他结果读取器关闭失败: {type(exc).__name__}')
        if error is not None:
            # 原首错和关闭顺序不变，最高结果仍保留失败的真实游标供恢复。
            error.analysis_result_cleanup_owner = self
            raise error
        try:
            # 各层只释放自己的实际申请，子spool从不抵销本层或调用方的借用余额。
            if self._readable_writer is not None:
                self._readable_writer.close()
                self._readable_writer = None
            if self._artifact_exports is not None:
                self._artifact_exports.close()
                if not self._artifact_exports.closed:
                    raise AnalysisError('新导出仓没有真实关闭')
            _release_owned_ram(self, self._writer_cost, '_writer_cost')
            _release_owned_ram(self, self._metadata_cost, '_metadata_cost')
            self.spool.close()
            if self._pending_output_cleanup is not None:
                remove_owned_directory(*self._pending_output_cleanup)
                self._pending_output_cleanup = None
            if not self._work_removed:
                remove_owned_directory(*self._owned_work)
                self._work_removed = True
        except BaseException as exc:
            # 新原始仓持续关闭失败仍从本结果恢复，不要求调用方绕过其真实父。
            exc.analysis_result_cleanup_owner = self
            raise
        finally:
            if (not self._iterators and self._held_cost == 0 and self.spool._closed
                    and self._work_removed and self._pending_output_cleanup is None
                    and (self._artifact_exports is None or self._artifact_exports.closed)):
                self._closed = True

    def __enter__(self) -> 'AnalysisResult':
        """进入结果上下文，不再次执行输入读取。

        参数: 无。返回: self。异常: ResultClosedError为已关闭。
        """
        self._require_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """退出上下文时释放资源，保留业务原异常。

        参数: exc_type/exc_value/traceback为上下文异常。返回: False，不吞异常。
        异常: 无原业务异常时关闭错误传播，否则原业务异常优先。
        """
        try:
            self.close()
        except BaseException as cleanup:
            if exc_value is None:
                raise
            # 原上下文异常优先，但持续关闭失败仍说明实际恢复入口。
            exc_value.add_note(f'结果上下文清理附加失败: {type(cleanup).__name__}')
            if not self._closed:
                exc_value.analysis_result_cleanup_owner = self
        return False
