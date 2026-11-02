"""在固定内存和文件句柄数量内归并多份已排序结果，减少中间文件重复写入。

输入为同一ResultSpool持有的1至64份run及一个全新目标路径；输出保留原JSONL
的全部JSONL字节。每路只保留当前一行，按原排序键及输入路序稳定归并。
读取与写入沿用owner的严格校验和累计磁盘配额，RAM先预约到owner._merge_cost。
本模块不删除输入、不修改结果模型，也不持有全量run清单或独立预算。ExitStack
逐个关闭实际文件，未关闭句柄和未退费用仍保留在owner._merge_run_resources，
调用方可通过同一owner.close重试；关闭失败不能被当成归并成功或资源已经释放。
"""

from contextlib import ExitStack
from heapq import heappop, heappush
from pathlib import Path

from .budget import _reserve_owned_ram, _release_owned_ram
from .errors import AnalysisError, ResultFormatError


_MAX_ROUTES = 64  # 仅限制本次打开的输入数，不按全部run数量建立路径列表。
_OUTPUT_WORK_BYTES = 65536  # 两个8KiB输出缓冲、输出FD和有限临时状态的余量。
_ROUTE_WORK_BYTES = 1024  # 每路Path/heap节点/ExitStack登记的保守有限描述费用。


class _MergeResources:
    """保存本次所有实际文件与已付归并费，持续关闭失败也不丢真实责任。

    handles每槽只持一个实际FD或None；pending先安装新开FD再扩展登记列表。
    ExitStack完成首轮关闭，失败后按仍存活的槽重试；只有全部FD与费用均清理才closed。
    """

    def __init__(self, owner):
        """建立已预付的有限责任对象。参数: owner为真实暂存。返回: None；初始化实例状态。异常: 分配错误。"""
        self.owner = owner
        self.handles, self.pending, self.stack = [], None, ExitStack()
        self.drained = self.closed = False

    def open(self, path, mode, buffering):
        """把新FD先安装到真实槽，再登记ExitStack回调，覆盖登记时取消。

        参数: path/mode/buffering为原文件参数。返回: 本对象实际持有的句柄。
        异常: 原打开/登记/取消错误；已打开的FD仍由pending或handles持有。
        """
        self.pending = path.open(mode, buffering=buffering)
        self.handles.append(self.pending)
        position = len(self.handles) - 1
        handle, self.pending = self.pending, None
        self.stack.callback(self._close_slot, position)
        return handle

    def _close_slot(self, position):
        """实际关闭一个已登记FD，关闭后取消仍记录真实关闭事实。

        参数: position为有限句柄槽。返回: None。异常: 原close错误；未关对象保原槽。
        """
        handle = self.handles[position]
        if handle is None:
            return
        try:
            handle.close()
        finally:
            if handle.closed:
                self.handles[position] = None
            handle = None

    def close(self):
        """先关闭所有实际FD再退自有费用；失败后同一责任对象可重复关闭。

        参数: 无。返回: None；closed后幂等。异常: 首个清理错误为主，其他错误附note；
            存活FD或未抵销费用时保owner._merge_run_resources，绝不释放借用余额。
        """
        if self.closed:
            return
        failure = handle = None
        try:
            # 新FD尚未完成列表登记时仍由pending持有，也必须先关闭才可归还费用。
            if self.pending is not None:
                try:
                    self.pending.close()
                except BaseException as exc:
                    failure = exc
                finally:
                    if self.pending.closed:
                        self.pending = None
            if not self.drained:
                try:
                    self.stack.close()
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                    else:
                        failure.add_note(f'归并ExitStack关闭附加失败: {type(exc).__name__}')
                finally:
                    # ExitStack虽会耗尽回调，失败FD仍在handles真实槽，不从回调是否存在猜关闭。
                    self.drained = True
            # 包括callback登记之前取消的FD；首轮有关闭故障时留待显式下一次close重试。
            if failure is None:
                for position, handle in enumerate(self.handles):
                    if handle is not None:
                        try:
                            self._close_slot(position)
                        except BaseException as exc:
                            if failure is None:
                                failure = exc
                            else:
                                failure.add_note(f'归并FD关闭附加失败: {type(exc).__name__}')
                handle = None
            unclosed = self.pending is not None or any(handle is not None for handle in self.handles)
            if not unclosed:
                try:
                    _release_owned_ram(self.owner, self.owner._merge_cost, '_merge_cost')
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                    else:
                        failure.add_note(f'归并费用清理附加失败: {type(exc).__name__}')
                finally:
                    # 释放回调可能已更新账本再取消；按实际槽值确认，不重复抵销其他人的钱。
                    if self.owner._merge_cost == 0:
                        self.closed = True
                        self.owner._merge_run_resources = None
                        self.handles.clear()
                        self.stack = None
            elif failure is None:
                failure = AnalysisError('归并文件尚未确认关闭，保留实际责任与费用')
            if failure is not None:
                if not self.closed:
                    failure.result_merge_cleanup_owner = self
                raise failure
        finally:
            handle = None


def merge_runs(owner, paths_tuple, destination, *, table):
    """将同一暂存的有限有序输入稳定合并到新文件，失败仍保原错误与实际费用。

    参数: owner为当前ResultSpool；paths_tuple为1至64个Path且无重复；destination
        为不存在的Path；table为固定表名或使用全局硬限的None。输入须按原键升序排列。
    返回: None；目标JSONL经真实关闭后才成功返回。
    异常: 配置/预算/行损坏、排序回退、文件错误和原取消；清理副错只附note，
        未退RAM仍留在同一owner._merge_cost，可由owner.close继续处理。
    边界: 相等键按输入路序稳定取出；每次写后先丢旧行再读该路下一行。
    """
    if (type(paths_tuple) is not tuple or not 1 <= len(paths_tuple) <= _MAX_ROUTES
            or any(not isinstance(path, Path) for path in paths_tuple)
            or not isinstance(destination, Path)):
        raise ValueError('多路归并需要1至64个Path组成的tuple及新目标Path')
    if owner._merge_cost or getattr(owner, '_merge_run_resources', None) is not None:
        raise AnalysisError('当前暂存仍持有前次归并费用，必须先完成清理')
    # row_limit只取成功编码事实，不能按损坏文件大小自行放宽读取范围。
    maximum = owner.max_row_bytes if table is None else owner.row_limit(table)
    reader_cost = owner.reader_cost if table is None else owner.reader_cost_for(table)
    # 单路复制及双路保原费用，维持已验证的最低可用预算；多路按统一公式预约。
    cost = (2 * reader_cost if len(paths_tuple) <= 2 else len(paths_tuple) * reader_cost
            + _OUTPUT_WORK_BYTES + _ROUTE_WORK_BYTES * len(paths_tuple))
    failure = resources = heap = inputs = entry = key = previous_key = None
    output = handle = None
    try:
        # 先登记实际费用，再建立路径集合、FD、heap和行；成功后取消仍由原owner负责。
        _reserve_owned_ram(owner, cost, '_merge_cost')
        if len(set(paths_tuple)) != len(paths_tuple) or destination in paths_tuple:
            raise ValueError('多路归并输入不得重复，目标不得复用输入路径')
        resources = _MergeResources(owner)
        owner._merge_run_resources = resources
        heap, inputs = [], []
        for path in paths_tuple:
            handle = resources.open(path, 'rb', buffering=8192)
            inputs.append(handle)
        output = resources.open(destination, 'xb', buffering=0)
        # 每路先取得一条；空run在当前文件EOF处结束。
        for route, handle in enumerate(inputs):
            entry = owner._read_entry(handle, maximum)
            if entry is not None:
                heappush(heap, (entry[0], route, entry))
            entry = None
        while heap:
            key, route, entry = heappop(heap)
            owner._write_bytes(output, entry[1])
            # 清旧payload后再读下一行；只留下比较顺序需要的有限键。
            previous_key, entry, key = key, None, None
            handle = inputs[route]
            entry = owner._read_entry(handle, maximum)
            if entry is not None:
                if entry[0] < previous_key:
                    raise ResultFormatError('多路归并输入run的排序键回退')
                heappush(heap, (entry[0], route, entry))
            entry = previous_key = None
    except BaseException as exc:
        failure = exc
        raise
    finally:
        # 清掉大行与局部引用，实际FD仍在resources槽，持续失败不会因ExitStack耗尽回调而丢失。
        heap = inputs = entry = key = previous_key = None
        output = handle = None
        try:
            if resources is not None:
                resources.close()
            else:
                # 预约后、资源对象建立前的失败尚无FD，费用仍须按真实槽值抵销。
                _release_owned_ram(owner, owner._merge_cost, '_merge_cost')
        except BaseException as cleanup:
            if failure is None:
                raise
            failure.add_note(f'多路归并资源清理附加失败: {type(cleanup).__name__}')
            if resources is not None and not resources.closed:
                failure.result_merge_cleanup_owner = resources
            if owner._merge_cost:
                failure.result_spool_cleanup_owner = owner
