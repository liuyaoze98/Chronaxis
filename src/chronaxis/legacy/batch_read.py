"""在共享预算内按批取得原CAN解码结果，保全量观测时间与需要的完整原记录。

复用逐条read的INIT/READY验证、实际进程关闭和失败恢复，不改变原逐条入口。
父在授予一批许可前预付两端缓冲、解析模型和时间数组的保守费用；同时只一批在途。
每批最多4096原帧且256KiB，预算较小时缩字节上限。默认同步；显式开启预取时，
当前批交付前可再预付并授权一批，使子读取与父计算重叠。取消或当前批处理失败时
可能额外读出这一批；预约/发送失败则当前批也不交付。预算不足时同步读取。
最后数据批可含真实EOF，下一次next完成退出/关闭才finished。
低层默认full/source保旧协议；auto结合固定requested范围使用v4 READY与CXB2，
原帧数独立于时间数量，计数和预取不会因跳过无用时间而丢失读取进度。
"""

from functools import partial
from dataclasses import replace
from pathlib import Path

from .batch_wire import (BATCH_MAGIC, DEMAND_MAGIC, HEADER, DEMAND_HEADER, MAX_BATCH_BYTES, MAX_BATCH_ROWS, MIN_BATCH_BYTES,
                         FILE_HEADER, FILE_MAGIC, decode_batch)
from .batch_worker import REQUESTED_VALUES_POLICY, batch_worker_main
from .process_read import LegacyCANProcessRead
from .records import MAX_WIRE_BYTES, decode_packet
from ..results.budget import _reserve_owned_ram, _release_owned_ram
from ..results.errors import BudgetExceededError
from ..sources.protocol import SourceReadError


class LegacyCANBatchRead(LegacyCANProcessRead):
    """持有当前借用结果及可选下一批许可，全部费用由共享关闭流程归还。

    _current保存已验证批次，_current_cost预付两端全部批次工作空间；
    _prefetch_packet/_prefetch_cost独立持有至多一个下一批许可及其完整费用，
    所有共享账本操作均在父调用线程完成，没有后台线程预约或无界队列。
    _batch_eof仅表示收到EOF候选，实际.finished仍要求子正常退出和父关闭成功。
    """

    def __init__(self, request, budget, *, frame_ids=None, batch_rows=MAX_BATCH_ROWS,
                 consumer_headroom_bytes=0, prefetch=False, decode_scope='all',
                 decode_frame_ids=None, input_check='full', time_scope='source', _worker_target=None,
                 input_paths=None, decode_policy='legacy', cycle_fields=(), metadata_fields=()):
        """保存批次上限与解码后选择，不打开文件或启动子进程。

        参数: request/budget同逐条read；frame_ids=None保全部原记录，tuple仅保这些ID；
            batch_rows为1至4096原帧上限；consumer_headroom_bytes为调用方处理本批时
            仍需预约的工作空间，此处只留余量、不代其付款；prefetch为显式bool，
            True允许额外一个已付批次在途；_worker_target仅供真实spawn故障测试。
            decode_scope='all'沿用原全解码与v1 READY，此时decode_frame_ids须为None；
            'requested'须给固定原生tuple ID，fields只能属于这些ID，使用严格v3 READY；
            此时frame_ids仍可为None或其他ID，保留原始帧不扩大固定解码范围。
            input_paths为原序BLF Path tuple或None；decode_policy默认legacy，strict/partial
            采用新长度政策。两者启用时v5 READY确认文件和政策，多文件批带文件位置。
            cycle_fields为另行请求周期的有限字段tuple；metadata_fields仅取候选。两者不加入值解码，v5确认声明。
            input_check默认full/source保旧行为；auto启用ID优先和v4 READY，
            time_scope为source/selected/none，后两者只传所需身份不能供原始片段导出。
        返回: 尚未启动read。异常: 原配置/预算错误，未返回owner仍可恢复close。
        """
        self._frame_ids, self._batch_rows = frame_ids, batch_rows
        self._consumer_headroom_bytes = consumer_headroom_bytes
        self._batch_limit = MAX_WIRE_BYTES
        self._batch_eof = False
        self._frames_authorized = self._records_returned = 0
        self._prefetch = prefetch
        self._prefetch_packet = None
        self._prefetch_cost = 0
        self._prefetch_headroom_bytes = 0
        # 内部来源证明可借用刚核完的原包；默认无观察者，不复制包或另收取散列费用。
        self._validated_packet_consumer = None
        # 基类构造取消会动态调用本类close，先建立策略引用与独立费用责任槽。
        self._decode_scope, self._decode_frame_ids = decode_scope, decode_frame_ids
        self._input_check, self._time_scope = input_check, time_scope
        self._minimum_batch_bytes = MIN_BATCH_BYTES + (
            DEMAND_HEADER.size-HEADER.size if input_check == 'auto' and time_scope == 'source' else 0)
        self._cycle_fields = cycle_fields
        self._metadata_fields = metadata_fields
        self._input_paths, self._decode_policy = input_paths, decode_policy
        self._input_index_accepted = 0
        self._source_policy_cost = 0
        self._file_envelope = False
        self._full_checks_accepted = 0
        self._decode_policy_cost = 0
        super().__init__(request, budget,
            _worker_target=batch_worker_main if _worker_target is None else _worker_target)
        try:
            if type(prefetch) is not bool:
                raise TypeError('CAN批次预取开关必须是bool')
            if type(batch_rows) is not int or not 1 <= batch_rows <= MAX_BATCH_ROWS:
                raise ValueError('批次需要1至4096条原帧上限')
            if type(consumer_headroom_bytes) is not int or consumer_headroom_bytes < 0:
                raise ValueError('消费批次的后续工作余量必须是非负整数')
            if frame_ids is not None and (type(frame_ids) is not tuple or len(frame_ids) > 4096
                    or any(type(value) is not int or not 0 <= value <= 0x1fffffff for value in frame_ids)
                    or len(set(frame_ids)) != len(frame_ids)):
                raise ValueError('解码后保留ID必须是无重复29位整数tuple或None')
            if type(decode_scope) is not str or decode_scope not in ('all', 'requested'):
                raise ValueError('CAN解码范围需要all或requested')
            if type(input_check) is not str or input_check not in ('auto', 'full'):
                raise ValueError('CAN输入检查需要auto/full')
            if type(time_scope) is not str or time_scope not in ('source', 'selected', 'none'):
                raise ValueError('CAN时间范围需要source/selected/none')
            if input_check == 'full' and time_scope != 'source':
                raise ValueError('完整检查必须保留全来源时间')
            if input_check == 'auto' and decode_scope != 'requested':
                raise ValueError('自动按需检查需要固定requested解码范围')
            if decode_scope == 'all':
                if decode_frame_ids is not None:
                    raise ValueError('全解码模式不能另设固定解码ID')
            else:
                if (type(decode_frame_ids) is not tuple or len(decode_frame_ids) > 4096
                        or any(type(value) is not int or not 0 <= value <= 0x1fffffff
                               for value in decode_frame_ids)):
                    raise ValueError('按需解码ID必须是无重复29位整数tuple')
                # 独立预付父/子tuple、集合、partial及策略元数据；不挪用消费批次余量。
                # 每ID 256B覆盖两侧容器槽，8192B覆盖空容器/函数描述；每字段1024B
                # 另覆盖子侧投影表和构建临时槽，名称借自已付请求，不复制其文本。
                _reserve_owned_ram(self, 8192 + 256 * len(decode_frame_ids)
                                   + 1024 * len(request.fields), '_decode_policy_cost')
                if len(set(decode_frame_ids)) != len(decode_frame_ids):
                    raise ValueError('按需解码ID必须是无重复29位整数tuple')
                if any(field.frame_id not in decode_frame_ids for field in request.fields):
                    raise ValueError('所需字段的报文ID必须属于固定解码集合')
                if _worker_target is None:
                    self._worker_target = partial(batch_worker_main, decode_frame_ids=decode_frame_ids,
                        input_check=input_check, time_scope=time_scope)
            from .decode_policy import validate_decode_policy
            validate_decode_policy(decode_policy)
            from .dbc_cycles import require_cycle_fields
            require_cycle_fields(cycle_fields)
            require_cycle_fields(metadata_fields)
            if input_paths is not None:
                if (type(input_paths) is not tuple or not 1 <= len(input_paths) <= 4096
                        or any(not isinstance(p,Path) or p.suffix.lower() != '.blf'
                               or len(str(p)) > 4096 for p in input_paths)
                        or input_paths[0] != request.input_path):
                    raise ValueError('连续输入需要原序BLF Path tuple，首路径须与INIT一致')
            if input_paths is not None or decode_policy != 'legacy' or cycle_fields or metadata_fields:
                paths = input_paths or (request.input_path,)
                _reserve_owned_ram(self,16384 + sum(512+len(str(p))*32 for p in paths)
                    + len(request.fields)*512
                    + sum(8192+128*len(f.signal) for f in (*cycle_fields,*metadata_fields)),'_source_policy_cost')
                self._file_envelope = len(paths) > 1
                self._minimum_batch_bytes += FILE_HEADER.size if self._file_envelope else 0
                if _worker_target is None:
                    self._worker_target = partial(batch_worker_main,
                        decode_frame_ids=decode_frame_ids,input_check=input_check,time_scope=time_scope,
                        input_paths=None if input_paths is None else tuple(str(p) for p in input_paths),
                        decode_policy=decode_policy,cycle_fields=cycle_fields,metadata_fields=metadata_fields)
        except BaseException as exc:
            self._fail(exc, '批次构造')

    def _check_ready(self, packet):
        """默认沿用原v1验证；requested核v3，auto核v4及检查/时间范围。

        参数: packet为严格wire解码后的READY。返回: None。异常: SourceReadError。
        ID先逐项核原生int再比较tuple，拒绝bool/int混同、缺项、额外字段或顺序改变；
        显式测试worker也必须确认同策略，不能用旧v1/v2应答冒充字段已裁剪。
        """
        if self._input_paths is not None or self._decode_policy != 'legacy' or self._cycle_fields or self._metadata_fields:
            expected_paths = [str(p) for p in (self._input_paths or (self._request.input_path,))]
            base_version = 1 if self._decode_scope == 'all' else (4 if self._input_check == 'auto' else 3)
            if (type(packet.get('version')) is not int or packet['version'] != 5
                    or type(packet.get('base_version')) is not int or packet['base_version'] != base_version
                    or packet.get('input_paths') != expected_paths
                    or packet.get('decode_policy') != self._decode_policy):
                raise SourceReadError('连续CAN READY文件或解码政策不符')
            if self._cycle_fields:
                from .records import field_from_dict
                actual = packet.get('cycle_fields')
                if type(actual) is not list or tuple(field_from_dict(f) for f in actual) != self._cycle_fields:
                    raise SourceReadError('CAN READY周期请求与声明不同')
            if self._metadata_fields:
                from .records import field_from_dict
                actual = packet.get('metadata_fields')
                if type(actual) is not list or tuple(field_from_dict(f) for f in actual) != self._metadata_fields:
                    raise SourceReadError('CAN READY字段候选请求与声明不同')
            packet = dict(packet)
            if self._metadata_fields:
                packet.pop('metadata_fields')
            if self._cycle_fields:
                packet.pop('cycle_fields')
            packet['version'] = packet.pop('base_version')
            packet.pop('input_paths'); packet.pop('decode_policy')
        if self._decode_scope == 'all':
            return super()._check_ready(packet)
        required_keys = {'op', 'version', 'profile', 'worker_pid', 'fields',
                           'dependency_versions', 'vendor_sha256', 'decode_scope', 'decode_frame_ids',
                           'decoded_values_policy'}
        if self._input_check == 'auto':
            required_keys.update(('input_check', 'time_scope'))
        if (set(packet) != required_keys
                or packet.get('op') != 'ready' or type(packet.get('version')) is not int
                or packet.get('version') != (4 if self._input_check == 'auto' else 3)
                or packet.get('profile') != self._request.profile
                or type(packet.get('worker_pid')) is not int
                or packet.get('worker_pid') != self._worker_pid):
            raise SourceReadError('按需CAN READY身份、版本或实际PID不符')
        ids = packet['decode_frame_ids']
        if (type(packet['decode_scope']) is not str or packet['decode_scope'] != 'requested'
                or type(ids) is not list or len(ids) != len(self._decode_frame_ids)
                or any(type(value) is not int for value in ids)
                or tuple(ids) != self._decode_frame_ids
                or type(packet['decoded_values_policy']) is not str
                or packet['decoded_values_policy'] != REQUESTED_VALUES_POLICY):
            raise SourceReadError('按需CAN READY解码策略或固定ID与启动请求不同')
        if self._input_check == 'auto' and (packet['input_check'] != 'auto'
                or packet['time_scope'] != self._time_scope):
            raise SourceReadError('按需CAN READY检查或时间范围与启动请求不同')
        self._check_ready_metadata(packet)

    def _check_ready_metadata(self, packet):
        """周期只为显式请求字段核验；默认维持原元数据契约。

        参数: packet为已核READY。返回: None。异常: 原字段、周期或依赖校验错误。
        """
        return super()._check_ready_metadata(packet,cycle_fields=self._cycle_fields,metadata_fields=self._metadata_fields)

    @property
    def counters(self):
        """区分批次许可上界、收到的原帧与保留记录，不把未消费批次伪称已完成。

        参数: 无。返回: 独立dict；frames_authorized包含许可但可能没读到的余量。
        异常: 原小字典分配错误。边界: items计全部原帧；accepted为接收校验完成，
        returned为已交付，records_returned计已交付的保留记录，预取失败不会虚增交付数。
        """
        # 完整保留历史诊断字典形状，新检查事实通过独立属性与版本化批次发布。
        return dict(super().counters, frames_authorized=self._frames_authorized,
                    records_returned=self._records_returned)

    @property
    def full_check_count(self):
        """读取已验收批次中非原生输入执行完整检查的实际回退数。

        参数: 无。返回: 非负int；不计尚在预取中的包，关闭后仍保留统计。
        异常: 无。此属性不把完整检查默认模式中的原帧数误作按需回退数量。
        """
        return self._full_checks_accepted

    def _receive_reply(self):
        """在已预付的上限内接收批数据或原严格控制JSON，拒绝错误版本和超长包。

        参数: 无。返回: 批次回应dict或原READY/ERROR/STATUS。异常: 原管道/格式/取消错误。
        内部观察者仅在整包严格解码成功后调用一次；只借用本槽中的payload与batch，
        不改变所有权。回调失败沿next的同一read清理，不交付或再次处理该批。
        """
        batch = None
        try:
            self._pending_reply = self._connection.recv_bytes(self._batch_limit)
            if self._pending_reply.startswith((BATCH_MAGIC, DEMAND_MAGIC, FILE_MAGIC)):
                if self._current_cost == 0:
                    raise SourceReadError('未授予/付费的批次数据')
                payload = self._pending_reply
                index, allowance = 0, self._batch_limit
                if self._file_envelope:
                    if len(payload) < FILE_HEADER.size or not payload.startswith(FILE_MAGIC):
                        raise SourceReadError('连续CAN缺少文件位置')
                    _, index = FILE_HEADER.unpack_from(payload)
                    if not self._input_index_accepted <= index < len(self._input_paths):
                        raise SourceReadError('连续CAN文件位置越界或倒退')
                    payload = payload[FILE_HEADER.size:]
                    allowance -= FILE_HEADER.size
                elif payload.startswith(FILE_MAGIC):
                    raise SourceReadError('单文件CAN收到未声明的连续包')
                batch, eof = decode_batch(payload, expected_start=self._items_accepted,
                    row_limit=self._batch_rows, byte_limit=allowance, frame_ids=self._frame_ids,
                    time_scope=self._time_scope, input_check=self._input_check)
                if self._file_envelope:
                    if eof and index != len(self._input_paths)-1:
                        raise SourceReadError('连续CAN在最后文件前报告EOF')
                    batch = replace(batch,input_index=index)
                    self._input_index_accepted = index
                if self._validated_packet_consumer is not None:
                    self._validated_packet_consumer(self, self._pending_reply, batch)
                return {'op': 'batch', 'request_id': batch.start_sequence, 'batch': batch, 'eof': eof}
            # 控制包即使在批读取时也保持原64KiB与严格JSON边界。
            return decode_packet(self._pending_reply)
        finally:
            # 原错误可留在调用方；已结束调用的临时引用不继续占有整批对象。
            batch = payload = None

    def __next__(self):
        """授予一批有界许可并交付原序数据；确认真实EOF及退出后才结束迭代。

        参数: 无。返回: LegacyDecodedBatch，借至下次next或close。
        异常: 真StopIteration、原预算/来源/取消错误；持续清理失败保同一owner。
        """
        if self._finished:
            raise StopIteration
        self._require_open()
        reply = batch = packet = None
        try:
            self.start()
            # 同步入口保持原归还时机；预取入口的最后批费用在实际关闭后归还。
            if not (self._prefetch and self._batch_eof):
                self._current = self._pending_reply = None
                _release_owned_ram(self, self._current_cost, '_current_cost')
            if self._batch_eof:
                self._eof_received = True
                self.close()
                if self._exit_code != 0:
                    raise SourceReadError('旧CAN批次发EOF但没有正常退出')
                self._finished = True
            else:
                if self._prefetch_packet is not None:
                    packet = self._prefetch_packet
                    if packet['request_id'] != self._items_accepted:
                        raise SourceReadError('预取许可与实际已消费位置不符')
                    self._batch_limit = packet['bytes']
                    # 同一owner的两槽之间移交已付责任，没有新的预算回调或线程。
                    self._current_cost, self._prefetch_cost = self._prefetch_cost, 0
                    self._prefetch_packet = None
                    reply = self._receive_response(packet)
                else:
                    self._batch_limit = self._available_limit()
                    if self._batch_limit < self._minimum_batch_bytes:
                        raise BudgetExceededError('CAN批次预算不足以保留一条最大记录及两端工作空间')
                    _reserve_owned_ram(self, 128*self._batch_limit, '_current_cost')
                    packet = self._new_packet(self._batch_limit)
                    self._pulls_issued += 1
                    self._frames_authorized += self._batch_rows
                    reply = self._exchange(packet)
                if reply.get('op') != 'batch' or reply.get('request_id') != packet['request_id']:
                    raise SourceReadError('批次许可未得到对应批次回应')
                batch = reply['batch']
                self._batch_eof = reply['eof']
                self._items_accepted += batch.frame_count
                self._full_checks_accepted += batch.full_check_count
                self._current = batch
                self._pending_reply = None
                if self._prefetch:
                    self._try_prefetch()
                # 预取预约/发送失败时当前批未交付；accepted保接收事实，returned不提前增加。
                self._items_returned += batch.frame_count
                self._records_returned += len(batch.records)
                return batch
        except BaseException as exc:
            # 清掉本frame对大批对象的额外引用；真正持有关系由父_current负责清理。
            reply = batch = packet = None
            self._fail(exc, '批次读取')
        finally:
            reply = batch = packet = None
        raise StopIteration

    def _new_packet(self, byte_limit):
        """为下一原序号建立有限批次许可，不触碰管道。

        参数: 已确定并付费的字节上限。返回: 小dict。异常: 原分配错误。
        """
        return {'op': 'pull_batch', 'request_id': self._items_accepted,
                'rows': self._batch_rows, 'bytes': byte_limit,
                'frame_ids': None if self._frame_ids is None else list(self._frame_ids)}

    def _set_prefetch_headroom(self, extra_bytes):
        """更新仅供下一次额外预取的动态消费余量，不收费且不改变同步许可。

        参数: extra_bytes为调用方证明所需的非负原生int，在每次next前更新。
        返回: None。异常: TypeError/ValueError为非法余量；关闭后拒绝更新。
        边界: 本线程直接设置有限整数，没有后台预算回调；不足时只停预取。
        """
        self._require_open()
        if type(extra_bytes) is not int:
            raise TypeError('预取额外消费余量必须是原生int')
        if extra_bytes < 0:
            raise ValueError('预取额外消费余量不能为负数')
        self._prefetch_headroom_bytes = extra_bytes

    def _available_limit(self, *, additional_headroom=0):
        """在当前共享余额中留下消费者余量，计算完整可付款的批次上限。

        参数: additional_headroom为预取专用额外余量，原同步读取固定为0。
        返回: 不超过MAX_BATCH_BYTES的整数，可能不足一条。
        异常: 原账本读取错误；这里只看余额，不取得额外空间。
        """
        available = (self._budget.memory_budget_bytes - self._budget.ram_bytes
                     - self._consumer_headroom_bytes - additional_headroom)
        return min(MAX_BATCH_BYTES, available // 128)

    def _try_prefetch(self):
        """余量足够时全额预付并发送下一批；否则留到下一次同步读取。

        参数: 无，当前批已完成全部接包校验。返回: None。
        异常: 原预约/发送/取消错误；失败不重发，也不交付当前批，由next统一清理。
        边界: EOF不再发许可；至多一个在途批，消费余量不用于预付。
        """
        if self._batch_eof:
            return
        if self._waiting or self._prefetch_packet is not None or self._prefetch_cost:
            raise SourceReadError('预取已有一个在途请求或费用责任')
        limit = self._available_limit(additional_headroom=self._prefetch_headroom_bytes)
        if limit < self._minimum_batch_bytes:
            return
        # 只有付款前的余额不足可以回退；预约实际入账或发送中断不可猜测成功程度。
        _reserve_owned_ram(self, 128*limit, '_prefetch_cost')
        self._prefetch_packet = self._new_packet(limit)
        self._pulls_issued += 1
        self._frames_authorized += self._batch_rows
        self._send_request(self._prefetch_packet)

    def _release_closed_state(self):
        """共享close确认实际资源全关后清预取责任，再按原槽逐笔归还。

        参数: 无。返回: None。异常: 原退费错误；同一close可从实际剩余槽恢复。
        """
        self._prefetch_packet = self._frame_ids = None
        self._validated_packet_consumer = None
        # 实际进程已结束才清策略与partial；退款失败仍保本owner费用槽供重复close。
        self._decode_frame_ids = None
        self._worker_target = None
        self._input_paths = None
        self._cycle_fields = ()
        self._metadata_fields = ()
        _release_owned_ram(self,self._source_policy_cost,'_source_policy_cost')
        _release_owned_ram(self, self._decode_policy_cost, '_decode_policy_cost')
        _release_owned_ram(self, self._prefetch_cost, '_prefetch_cost')
        super()._release_closed_state()
