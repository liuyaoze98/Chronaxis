"""估算冻结指标实体的继续保留费用，独立于JSON编解码工作副本。

输入只含已校验dataclass、tuple、枚举、原生标量及原协议支持的Mapping；输出含实体、实例字段字典、
引用槽及长文本的保守bytes。只递归计数，不复制对象、不按对象身份建立seen表；
同一对象出现在多处仍重复计费，因此跨owner共享无需隐式转移费用。

CPython实例字典以256字节头及每字段256字节覆盖字典索引、键/值槽和容量余量，
不读取__dict__以免在估算前物化managed dict。字段名/类定义由调用方已有模型拥有；
每个字段值仍完整递归计数。tuple的getsizeof已含引用槽，每项另留32字节容器余量。
此费用不承担_pack的新字典树、JSON文本/UTF8或解码副本，原codec估算另行预约。
只依赖标准库和轻量错误类型，没有文件、数组或来源读取副作用；不是RSS估计。
"""

# fields创建仅含实际字段的小tuple，大小取决于模型字段数，finally清members；
# 与原元数据协议一致，ClassVar/InitVar不属于实例实体，不读取实例__dict__。
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from sys import getsizeof
from ..results.errors import ResultFormatError


def retained_metadata_bytes(value, depth=0):
    """核算冻结对象实体及其字段，不把共享引用解释成深复制。

    参数: value为上述有限模型树；depth为内部深度计数。
    返回: 保守整数bytes，重复引用也独立计数，不需要无界身份集合。
    异常: ResultFormatError为超过32层或含未支持可变/数组类型。
    """
    members = field = item = key = None
    try:
        # 深度与已有元数据协议一致；不执行repr、复制实例字典或序列化方法。
        if depth > 32:
            raise ResultFormatError('保留元数据超过32层')
        if is_dataclass(value) and not isinstance(value, type):
            members = fields(value)
            amount = getsizeof(value) + 256 + 256 * len(members)
            for field in members:
                amount += retained_metadata_bytes(getattr(value, field.name), depth + 1)
            return amount
        # 自定义SourceRef原本可带Mapping；保留其原类型支持，不构造新字典或seen。
        if isinstance(value, Mapping):
            amount = getsizeof(value)
            for key, item in value.items():
                amount += 128 + retained_metadata_bytes(key, depth + 1) + retained_metadata_bytes(item, depth + 1)
            return amount
        # 已有tuple不复制；不用生成器让失败TB额外保留上一次大item。
        if type(value) is tuple:
            amount = getsizeof(value) + 32 * len(value)
            for item in value:
                amount += retained_metadata_bytes(item, depth + 1)
            return amount
        if isinstance(value, Enum):
            return 512 + getsizeof(value)
        if value is None or type(value) in (str, int, bool, float):
            return getsizeof(value) + 64
        raise ResultFormatError('保留元数据类型无法估算')
    finally:
        # 只断自身参数/局部；保原异常、TB节点和调用方输入，不清任何外部帧。
        value = members = field = item = key = None


def reference_workspace(existing_count, incoming_count):
    """预付去重期间新list及返回tuple的指针空间，不重复支付旧ref实体。

    参数: 两个count为已校验tuple长度。返回: 保守bytes。
    异常: 无主动异常；内部调用者保证非负原生int。
    """
    # 每项32字节覆盖64位list最多双容量的16字节及tuple8字节，另留8字节余量；
    # 2048覆盖两个容器头、迭代器和固定候选对象，不随payload文本长度失真。
    return 2048 + 32 * (existing_count + incoming_count)
