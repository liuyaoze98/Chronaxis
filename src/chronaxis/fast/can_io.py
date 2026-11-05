"""修复版 ChrgInfo 文件循环：先选 ID，再解码一次并更新该帧的全部公式。"""

from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from types import SimpleNamespace

import can
import cantools

from ..legacy.binding import dbc_candidates, select_message
from ..legacy.decode_policy import check_decode_length
from ..timebase.conversion import convert_time, checked_add_ns
from .compute import prepare_metric


@dataclass
class _Group:
    """同一实际报文类型共享一次解码。只有已请求的公式进入该组。"""

    message: object
    entries: list = field(default_factory=list)


_UNSUPPORTED_FD = object()


def _prepare(spec, db):
    """按选择器预建 ID 索引并为每项新建累计器。缺字段或歧义在开日志之前报告。"""
    groups = {}
    metrics = {}
    for item in spec['metrics']:
        name = item['name']
        if name in metrics:
            raise ValueError(f'重复的计算项 {name}')
        identifier = item['frame_id']
        if type(identifier) is not int or not 0 <= identifier <= 0x1fffffff:
            raise ValueError(f'{name} 的 frame_id 超出 CAN 范围')
        required = {signal['signal'] for signal in item['signals'].values()}
        if item.get('direction'):
            required.add(item['direction']['signal'])
        ide, fd = item.get('is_extended'), item.get('is_fd')
        if any(flag is not None and type(flag) is not bool for flag in (ide,fd)):
            raise ValueError(f'{name} 的帧型选择需要布尔值')
        choices = dbc_candidates(db,identifier,required,ide,fd)
        metric = metrics[name] = prepare_metric(item)
        # 未指定帧型时，只允许实际数据出现一种匹配身份。
        observed = set() if None in (ide,fd) else None
        by_kind = groups.setdefault(identifier,{})
        for extended in ((False,True) if ide is None else (ide,)):
            for actual_fd in ((False,True) if fd is None else (fd,)):
                kind = extended,actual_fd
                message = select_message(choices,SimpleNamespace(is_extended_id=extended,is_fd=actual_fd))
                if message is None:
                    if fd is None and actual_fd and any(m.is_extended_frame == extended for m in choices):
                        by_kind.setdefault(kind,_UNSUPPORTED_FD)
                    continue
                if message.is_container or message.is_multiplexed():
                    raise ValueError(f'{name} 的目标报文使用 container 或 multiplex')
                if by_kind.get(kind) is _UNSUPPORTED_FD:
                    raise ValueError(f'同 ID {identifier:#x} 的计算项对 FD 定义有冲突')
                group = by_kind.setdefault(kind,_Group(message))
                if group.message is not message:
                    raise ValueError(f'ID {identifier:#x} 在同一实际帧型中对应多个 DBC 定义')
                group.entries.append((name,metric,observed))
    if not metrics:
        raise ValueError('至少需要一个逐消息计算项')
    return groups,metrics


def _read_all(reader, cancel_event):
    """完整读入本文件；批量任务每 4096 帧检查一次取消，reader 由调用方关闭。"""
    if cancel_event is None:
        return list(reader)
    frames = []
    stream = iter(reader)
    while not cancel_event.is_set():
        block = list(islice(stream,4096))
        frames.extend(block)
        if len(block) < 4096:
            return frames
    raise InterruptedError('读取报文时取消')


def _read(path, groups, spec, cancel_event):
    """与 base 一样按文件读入并确定关闭。ASC 保留文本解析所得的精确纳秒。"""
    if path.suffix.lower() == '.blf':
        with can.BLFReader(path) as reader:
            return _read_all(reader,cancel_event), False
    if path.suffix.lower() == '.asc':
        from ..results.budget import ResourceBudget
        from ..sources.asc import ASCRead, ASCSpec
        channel = spec['channel'] - 1

        def selected_time(frame):
            """只比较实际进入时间筛选的帧，其他通道或远程帧不改变前一时刻。"""
            return (spec.get('domain_ns') is not None and frame.channel == channel
                    and not frame.is_error_frame and not frame.is_remote_frame
                    and (frame.is_extended_id,frame.is_fd) in groups.get(frame.arbitration_id,{}))

        with ASCRead(ASCSpec(path, **spec.get('asc_options', {})),ResourceBudget(),
                     retain_original=False,retain_source_time=False,
                     time_selector=selected_time) as reader:
            return _read_all(reader,cancel_event), True
    raise ValueError(f'仅支持 ASC 或 BLF：{path}')


def run_one(spec, database=None, *, cancel_event=None):
    """执行一份已准备的任务并返回汇总行及兼容提示。任何文件错误均不返回部分指标。"""
    path = Path(spec['path'])
    channel = spec['channel']
    if type(channel) is not int or channel < 1:
        raise ValueError('配置通道从 1 开始')
    domain = spec.get('domain_ns')
    if domain is not None and (len(domain) != 2 or any(type(t) is not int for t in domain)
                               or domain[0] >= domain[1]):
        raise ValueError('domain_ns 需要递增的两个整数纳秒')
    db = database if database is not None else cantools.database.load_file(spec['dbc'])
    groups,metrics = _prepare(spec,db)
    records, text = _read(path, groups, spec, cancel_event)
    before_domain = set()
    compatible = set()
    for index, record in enumerate(records):
        if cancel_event is not None and not (index & 4095) and cancel_event.is_set():
            raise InterruptedError('计算报文时取消')
        frame = record.frame if text else record
        candidates = groups.get(frame.arbitration_id)
        if candidates is None or frame.channel != channel-1 or frame.is_error_frame or frame.is_remote_frame:
            continue
        kind = frame.is_extended_id,frame.is_fd
        group = candidates.get(kind)
        if group is None:
            continue
        if domain is not None:
            timestamp = record.time_ns if text else checked_add_ns(
                convert_time(frame.timestamp,'s').time_ns,spec.get('offset_ns',0))
            if not domain[0] <= timestamp < domain[1]:
                if group is not _UNSUPPORTED_FD:
                    before_domain.update(name for name,_,_ in group.entries)
                continue
        try:
            if group is _UNSUPPORTED_FD:
                raise ValueError('实录为 FD 但 DBC 只定义经典 CAN')
            if not frame.is_fd and frame.dlc > 8:
                raise ValueError('经典 CAN 载荷不能超过 8 字节')
            check_decode_length(frame,group.message.length,'strict')
            values = group.message.decode(frame.data,decode_choices=False,scaling=True,
                                          allow_truncated=False,allow_excess=False)
            if group.message.is_fd and not frame.is_fd:
                compatible.add(frame.arbitration_id)
            for name,metric,observed in group.entries:
                if observed is not None:
                    observed.add(kind)
                    if len(observed) != 1:
                        raise ValueError(f'{name} 匹配多种实际帧型，请明确 is_extended 或 is_fd')
                metric.consume(values)
        except (ArithmeticError,ValueError,TypeError,KeyError,cantools.database.DecodeError) as error:
            raise ValueError(f'{path.name} 第 {index+1} 条记录，ID {frame.arbitration_id:#x}：{error}') from error
    rows = []
    for name,metric in metrics.items():
        row = metric.result()
        if row['value'] is None:
            if not records:
                row['reason'] = 'empty_file'
            elif name in before_domain:
                row['reason'] = 'no_target_in_domain'
        rows.append(row)
    return rows, [f'{identifier:#x} 按经典 CAN 实录解码 DBC 的 FD 声明' for identifier in sorted(compatible)]
