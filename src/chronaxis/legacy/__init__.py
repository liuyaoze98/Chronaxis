"""公开旧CAN记录，以及按需加载的记录仓、逐次模型与贡献累计原语。

输入输出和wire边界由records统一；实际进程由调用方显式创建，worker只在INIT后
加载CAN依赖。包导入无输入/DBC读取、logger配置或子进程副作用；不代表旧reader关闭
缺陷已修复。单BLF公共AnalysisRunner和原始片段已在其任务中验收；独立逐次模型及累计
只接收调用方提供的记录和已求值贡献，不证明表达式、旧ChrgInfo出口或公共
legacy_sum来源已经接通。原语不替输入提供者补缓存、施加TTL或重新解码。
解码记录仓只在显式构造后写入新目录，保存现有合法记录，不扩大原IPC值类型。
"""

# 只公开标准库冻结模型；不能在包入口急切导入worker的运行依赖。
from .records import (LegacyCANField, LegacyCANRequest, LegacyDecodedFrame, LegacyRawFrame,
    StoredRawFrame, MAX_WIRE_BYTES, PROFILE_ID, decoded_from_dict, decoded_to_dict, decode_packet,
    encode_packet, field_from_dict, field_to_dict, frame_from_dict, frame_to_dict)

__all__ = ('LegacyCANField', 'LegacyCANRequest', 'LegacyDecodedFrame', 'LegacyRawFrame',
    'StoredRawFrame', 'MAX_WIRE_BYTES', 'PROFILE_ID', 'decoded_from_dict', 'decoded_to_dict',
    'decode_packet', 'encode_packet', 'field_from_dict', 'field_to_dict', 'frame_from_dict', 'frame_to_dict',
    'LegacyDecodedUpdate', 'LegacyUpdateOrder', 'LegacySkipReason', 'LegacySumContribution',
    'LegacySumSnapshot', 'LegacySumAccumulator', 'StoredDecodedMessage', 'DecodedMessageStore',
    'MAX_DECODED_MESSAGE_ROW_BYTES')


def __getattr__(name):
    """按需公开独立模型、记录仓与累计，保持原CAN worker的轻量导入。

    参数: name为请求的模块属性名。返回: 已实现模型类本身，不创建输入或状态。
    异常: AttributeError为未公开名称；模型模块导入错误原样传播。
    副作用: 仅访问明确名称时导入其模型或累计模块，不读取日志或DBC；
        NumPy仅在调用者实际选择数组累计后加载。
    """
    # 已有CAN记录保持直接导出；未知名称不触发额外导入或提供占位实现。
    if name in ('LegacyDecodedUpdate', 'LegacyUpdateOrder'):
        from .updates import LegacyDecodedUpdate, LegacyUpdateOrder
        return {'LegacyDecodedUpdate': LegacyDecodedUpdate, 'LegacyUpdateOrder': LegacyUpdateOrder}[name]
    # 累计定义只需标准库及已有预算协议，数组内核由实际执行入口另行加载。
    if name in ('LegacySkipReason', 'LegacySumContribution', 'LegacySumSnapshot', 'LegacySumAccumulator'):
        from .sum import LegacySkipReason, LegacySumContribution, LegacySumSnapshot, LegacySumAccumulator
        return {'LegacySkipReason': LegacySkipReason, 'LegacySumContribution': LegacySumContribution,
                'LegacySumSnapshot': LegacySumSnapshot, 'LegacySumAccumulator': LegacySumAccumulator}[name]
    # 请求仓类型只加载定义；目录创建、编码写入和资源预留都由显式实例负责。
    if name in ('StoredDecodedMessage', 'DecodedMessageStore', 'MAX_DECODED_MESSAGE_ROW_BYTES'):
        from .message_store import StoredDecodedMessage, DecodedMessageStore, MAX_DECODED_MESSAGE_ROW_BYTES
        return {'StoredDecodedMessage': StoredDecodedMessage, 'DecodedMessageStore': DecodedMessageStore,
                'MAX_DECODED_MESSAGE_ROW_BYTES': MAX_DECODED_MESSAGE_ROW_BYTES}[name]
    raise AttributeError(f'chronaxis.legacy没有公开属性{name!r}')
