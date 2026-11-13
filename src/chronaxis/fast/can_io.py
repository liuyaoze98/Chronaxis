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
from .compute import prepare_metric, _prepare_program_metric


@dataclass
class _Group:
    """同一实际报文类型共享一次解码。只有已请求的公式进入该组。"""

    message: object
    entries: list = field(default_factory=list)


_UNSUPPORTED_FD = object()


def _prepare(spec, db, *, _programs_checked=False):
    """预建 ID 索引及每文件状态；内部已编译路径仅绑定指令，低层默认检查文本。

    参数为声明、DBC及内部准备状态。返回组索引和累计器；字段、歧义或公式错误
    在开日志前抛出。准备状态由调用链传入，不从用户配置或 spec 标志中读取。
    """
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
        factory = _prepare_program_metric if _programs_checked else prepare_metric
        metric = metrics[name] = factory(item)
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


def run_one(spec, database=None, *, cancel_event=None):
    """流式运行单文件低层入口，保留原调用的行及提示返回结构。

    参数: spec编译声明，database可选DBC，cancel_event可选取消事件。
    返回: (汇总行list, 提示list)。异常: 读取/解码/数值/取消错误。
    """
    from .session import run_session
    channel = spec['channel']
    if type(channel) is not int or channel < 1:
        raise ValueError('配置通道从1开始')
    domain = spec.get('domain_ns')
    if domain is not None and (len(domain) != 2 or any(type(t) is not int for t in domain) or domain[0] >= domain[1]):
        raise ValueError('domain_ns需要递增的两个整数纳秒')
    return run_session(spec, database, cancel_event=cancel_event)
