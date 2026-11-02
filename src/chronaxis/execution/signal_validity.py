"""从本次已经加载的DBC元数据补全必要信号的有效期。

仅处理尚未确定valid_for的信号，在读取首帧前按所属报文周期乘三。
不加载DBC、不扫描报文、不改变实际时间；返回的新定义交给计算状态使用，
静态配置仍保留缺省声明。无需有效期的无关信号不会额外请求周期。
"""

from dataclasses import replace
from ..legacy.records import field_to_dict
from ..sources.can_spec import can_field_from_key
from ..planning.signal_validity import triple_period


def resolve_signal_validity(definitions, source_cursors):
    """在来源初始化后补全待DBC的有效期，显式有效期原样复用。

    参数: definitions为本次实际需要的SignalDefinition元组；source_cursors为
        来源名到已初始化游标的映射，metadata.fields含本次请求的locator/cycle_ns。
    返回: SignalDefinition元组，全部有效期为正int64纳秒。
    异常: ValueError为缺失或不唯一的周期；PlanValidationError为周期三倍溢出。
    副作用: 无，不修改原声明或游标，不读取文件。
    """
    resolved = []
    for definition in definitions:
        # 已显式填写或由信号period求出的值无需再查询DBC。
        if definition.valid_for_ns is not None:
            resolved.append(definition)
            continue
        # 用完整规范定位找本次事实，不能按同名信号借用另一通道或报文的周期。
        cursor = source_cursors.get(definition.source)
        metadata = None if cursor is None else cursor.metadata
        locator = field_to_dict(can_field_from_key(definition.field))
        entries = (() if metadata is None else
                   tuple(item for item in metadata.get('fields', ()) if item.get('locator') == locator))
        if len(entries) != 1 or 'cycle_ns' not in entries[0]:
            raise ValueError(f'{definition.name}无法取得唯一DBC周期；请填写本信号period或valid_for')
        # 只替换运行所需定义；静态声明保持原样，不把尚未读取的周期写成既定事实。
        validity = triple_period(entries[0]['cycle_ns'], f'信号{definition.name}.valid_for')
        resolved.append(replace(definition, valid_for_ns=validity))
    return tuple(resolved)
