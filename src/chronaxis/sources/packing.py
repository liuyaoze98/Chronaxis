"""把一批已解码标量归一化为可传送的独立信号列。

输入是一个SignalDefinition、整数纳秒时间、原行序号及原值记录，另有
当前来源引用和后端选择。输出SignalSeries包含数值、有效性掩码、质量原因、
时间、序号和逐样本来源；原始值另存为诊断，不依靠无效值占位判断有效性。

reference逐样本调用独立标量归一化函数。numpy先按最多五种原生类型
组织同质数组，再批量归一化，最后按索引放回原输入位置。
分组循环负责布局和身份，不使用object数组进行数值计算。
pack_message_values只返回没有时间轴的NumericArray，供固定周期逐消息累计；
它不构造虚假时间、原序号或来源列。两个入口共享布局及归一化选择，保留
reference与NumPy数值实现独立。输出复制为自身拥有的只读数组；
本模块不读取文件或调用旧解码路径。
"""

# NumPy承担真实定宽存储，数值归一化选择显式后端。
import numpy as np
# 当前转换定义不含全历史，逐批转换不会构造包含全量历史的SignalBindings。
from ..core.binding import SignalDefinition
# 当前完整会话/来源/字段身份来自调用者已校验输入。
from ..core.models import SourceRef
# 参考归一化独立于NumPy实现。
from ..core.numeric import normalize_reference
# 静态dtype和结构布局可共享，参考仍不调用数组数值核。
from ..core.numeric_numpy import DTYPES, NumericArray
# NumPy原生类型组分别经过批量归一化。
from ..core.normalize_numpy import normalize_numpy
# 基础质量与枚举域从公共契约读取。
from ..core.types import QualityFlag, SignalDType
# 非原生/可变值在适配边界拒绝。
from ..core.validation import require_scalar
# 输出是传输列，不是已折叠的全历史保持序列。
from .models import SignalSeries


def _pack_numeric_columns(definition: SignalDefinition, originals: tuple, backend: str) -> tuple:
    """把原值批次归一化为数值、有效性、质量及枚举标签，不建立时间轴。

    参数:
        definition (SignalDefinition): 当前别名的输出类型、单位及显式转换。
        originals (tuple): 原生标量或None的有限批次，位置保持输入顺序。
        backend (str): 'reference'使用标量实现，'numpy'使用数组实现。
    返回:
        tuple: values、valid、quality三个可写独立数组及labels枚举域；
        数组形状为(N,)，后续输出模型负责复制冻结，无效占位不能当正常值。
    异常:
        TypeError或ValueError: 原值不合法；调用者已校验声明、tuple与后端。
        OverflowError或MemoryError: 数值转换或批次数组分配失败。
    副作用:
        分配批次数组，不修改输入原值；不读取时间、来源或原序号。
    """
    # 固定枚举域按声明顺序，空批也保留完整标签。
    labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
    # 所有列按本批N分配，非法占位只有掩码确认后才可使用。
    values, valid, quality = np.zeros(len(originals), dtype=DTYPES[definition.dtype]), np.zeros(len(originals), dtype=bool), np.zeros(len(originals), dtype=np.uint16)
    # 非原生对象禁止进入输入分组，防止隐式object计算。
    for value in originals:
        # None/非有限允许作无效原诊断。
        require_scalar(value)
    # 参考逐样本用独立精确标量契约，装箱仍保持目标dtype。
    if backend == 'reference':
        # N次基线求值不被称为数组实现。
        for index, original in enumerate(originals):
            # 独立参考不调用被测normalize_numpy。
            normalized = normalize_reference(definition, original)
            # 无效值仅保留原因，不参与正常数值存储。
            if normalized.valid:
                # enum以固定域code存储，不生成object列。
                values[index] = labels.index(normalized.value) if labels else normalized.value
            # 基础valid与quality各自完整保存。
            valid[index], quality[index] = normalized.valid, int(normalized.quality)
    else:
        # 原类型分组是布局操作，不是逐样本数值归一化。
        groups = {}
        # 每行登记原物理类型/输出位置和已有错误占位。
        for index, original in enumerate(originals):
            # 缺失必须带MISSING，不把0占位变成正常输入。
            if original is None:
                # 缺失打包成带原因的int64占位，内核不使用它。
                key, packed, flag = 'i', 0, QualityFlag.MISSING
            # 原整数宽度保持，不能先转float。
            elif type(original) is int:
                # 超64位协议的原值作为OVERFLOW诊断保留。
                flag = QualityFlag.NONE if -(2 ** 63) <= original <= 2 ** 64 - 1 else QualityFlag.OVERFLOW
                # 合法unsigned高端与signed分组，非法值仅存0占位。
                key, packed = ('i' if original <= 2 ** 63 - 1 else 'u'), original if flag == QualityFlag.NONE else 0
            else:
                # bool/str/float各自物理域，不使用隐式promotion。
                key, packed, flag = {float: 'f', bool: 'b', str: 'U'}[type(original)], original, QualityFlag.NONE
            # 每组保存原索引，用于将归一化结果放回原输入位置。
            groups.setdefault(key, []).append((index, packed, int(flag)))
        # 循环次数至多五，整个数值组实际批量归一化。
        for key, items in groups.items():
            # 物理类型由原值契约确定而非目标类型倒推。
            raw_dtype = {'i': np.int64, 'u': np.uint64, 'f': np.float64, 'b': bool, 'U': str}[key]
            # 每组原值和质量原因都组成长度为该组样本数的一维数组，类型明确。
            raw, reasons = np.array([value for _, value, _ in items], dtype=raw_dtype), np.array([flag for _, _, flag in items], dtype=np.uint16)
            # 数值转换用已验独立NumPy核，没有逐样本reference回调。
            normalized = normalize_numpy(definition, raw, reasons)
            # 放回索引只恢复原批次布局，不重排原文件或时间。
            positions = np.array([index for index, _, _ in items], dtype=np.int64)
            # 数值、有效性和质量三列放回相同位置；无效占位仍携带掩码与原因。
            values[positions], valid[positions], quality[positions] = normalized.values, normalized.valid, normalized.quality
    # 两种输出只共享无时间的数值列，避免逐消息路径装箱无用身份列。
    return values, valid, quality, labels


def pack_message_values(definition: SignalDefinition, originals: tuple, backend: str) -> NumericArray:
    """归一化逐消息原值，供无需时间轴的固定周期累计复用现有数值核。

    参数:
        definition (SignalDefinition): 别名的显式dtype、单位与转换规则。
        originals (tuple): 原生不可变标量或None，顺序为实际求值顺序。
        backend (str): reference逐样本独立归一化，numpy按原生类型批量归一化。
    返回:
        NumericArray: 形状(N,)的只读values、valid、quality以及固定枚举标签；
        空批次合法，不包含时间、来源、序号或虚假SignalSeries。
    异常:
        TypeError或ValueError: 声明、后端、tuple或原值不合法。
        OverflowError或MemoryError: 转换或数组分配失败，原输入不变。
    副作用:
        仅分配并冻结输出数组，不读写文件，不建立跨批缓存。
    """
    # 无时间入口也维持明确声明与后端，不接受隐式fallback或任意迭代器。
    if not isinstance(definition, SignalDefinition) or not isinstance(originals, tuple) or backend not in ('reference', 'numpy'):
        raise TypeError('pack_message_values需要typed声明/tuple原值及明确后端')
    # 数值列与原有pack_decoded走同一布局，未借助SignalSeries或假时间归一化。
    values, valid, quality, labels = _pack_numeric_columns(definition, originals, backend)
    from ..core.enum_codes import code_column
    return NumericArray(definition.dtype, values, valid, quality, labels, code_column(definition, originals))


def pack_decoded(definition: SignalDefinition, records: tuple[tuple[int, int, int | float | bool | str | None], ...], source_ref: SourceRef | tuple[SourceRef, ...], backend: str, *, retain_original=True, clock_only=False) -> SignalSeries:
    """归一化当前有限批次，保留同时间的不同观测及原始诊断。

    参数:
        definition (SignalDefinition): 当前别名的输出类型、单位及显式转换。
        records (tuple): 每项为(time_ns, sequence, 原值)，时间为纳秒。
        source_ref (SourceRef | tuple[SourceRef, ...]): 共用引用或等长逐样本引用。
        backend (str): reference为独立标量实现，numpy为原生类型分组数组实现。
        retain_original (bool): 默认保留原值；新按需路径关闭时不把原值传入结果列。
        clock_only (bool): 只传更新时间，跳过取值、归一化和原值保留；无效占位不参与计算。
    返回:
        SignalSeries: (N,)数值、有效性、质量、时间、序号及逐样本来源；
        原值仅在请求时保留，空批保留声明的类型与枚举域。
    异常:
        TypeError或ValueError: 输入结构、后端、原值、列布局或身份不合法。
        OverflowError或MemoryError: 转换、时间装箱或批次数组分配失败。
    副作用:
        分配独立只读批次，不修改输入；有效期保持由后续时间驱动层执行。
    """
    # 原接口先检查声明、行、来源与后端，继续保留原有拒绝边界。
    if not isinstance(definition, SignalDefinition) or not isinstance(records, tuple) or not (isinstance(source_ref, SourceRef) or isinstance(source_ref, tuple) and len(source_ref) == len(records) and all(isinstance(ref, SourceRef) for ref in source_ref)) or backend not in ('reference', 'numpy'):
        raise TypeError('pack_decoded需要typed声明/原行/ref及明确后端')
    # 原始诊断仍由SignalSeries保存，归一化列不会改变原顺序或原值。
    if type(retain_original) is not bool or type(clock_only) is not bool:
        raise TypeError('原值保留与纯时钟选项需要bool')
    originals=None
    if clock_only:
        # 列协议的无效占位不参与计算；不读取、转换或核验用户的无关数值。
        values=np.zeros(len(records),dtype=DTYPES[definition.dtype])
        valid=np.zeros(len(records),dtype=bool)
        quality=np.full(len(records),int(QualityFlag.MISSING),dtype=np.uint16)
        labels=tuple(dict.fromkeys(label for _,label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
    else:
        originals = tuple(item[2] for item in records)
        values, valid, quality, labels = _pack_numeric_columns(definition, originals, backend)
    # 精确时间与原序号分别int64，公共模型随后验证非递减/唯一。
    times, sequences = np.array([item[0] for item in records], dtype=np.int64), np.array([item[1] for item in records], dtype=np.int64)
    # 每行保持实际SourceRef，不从别名或semantic_id猜定位。
    from ..core.enum_codes import code_column
    code = None if clock_only else code_column(definition, originals)
    return SignalSeries(definition.name, definition.dtype, definition.unit, times, values, valid, quality, sequences, (source_ref,) * len(records) if isinstance(source_ref, SourceRef) else source_ref, labels, originals if retain_original else None, code)
