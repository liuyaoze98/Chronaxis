"""用二分索引和质量掩码查询信号的最新观测，按有效期判断能否使用。

输入为已校验SignalSeries及shape=(N,)、dtype=int64的查询时间轴；输出等长的
值、valid、uint16质量、原样本索引和实际更新列。构造SignalArray只进行存储
编码，保持查询通过批量searchsorted和掩码执行，不调用参考对齐函数。
值保持声明类型，无效位置只是存储占位；原诊断保留在series.samples。
本模块依赖NumPy和核心模型，没有来源读取或文件操作；列数组复制后由本层
持有并标为只读，不修改调用者输入。
"""

# dataclass保存数组布局元数据，不把所有dtype提升成float或object宽表。
from dataclasses import dataclass
# 存储dtype表固定，不能被其他调用者原地修改已验证布局。
from types import MappingProxyType

# 数组依赖仅在显式导入本模块时加载，标准库core入口仍独立。
import numpy as np

# 两后端仅共享已校验输入模型，数值对齐内核独立。
from .state import SignalSeries
# typed质量位和信号类型决定列布局及可计算掩码。
from .types import QualityFlag, SignalDType

# 列存储严格使用声明dtype，enum的固定整数编码在标签元数据中解释。
DTYPE_TABLE = MappingProxyType({SignalDType.INT64: np.dtype("int64"), SignalDType.UINT64: np.dtype("uint64"),
               SignalDType.FLOAT64: np.dtype("float64"), SignalDType.BOOL: np.dtype("bool"),
               SignalDType.ENUM: np.dtype("int64")})


def _require_axis(times_ns: np.ndarray) -> None:
    """检查完整一维int64非递减时间列，不做隐式cast或排序。

    参数: times_ns为ndarray，形状(N,)，dtype=int64，单位纳秒；空轴允许。
    返回: None；不修改输入所有权、writeable或内容。
    异常: TypeError为类型/dtype/masked数组；ValueError为形状/回退。
    """
    # 缺失坐标不能参加时间索引，masked subclass也不放行。
    if not isinstance(times_ns, np.ndarray) or isinstance(times_ns, np.ma.MaskedArray) or times_ns.dtype != np.dtype("int64"):
        # 不将大整数/float时间先截断为合法坐标。
        raise TypeError("时间轴必须为完整int64 ndarray")
    # 禁止二维广播轴或时间回退，直接比较避免diff溢出。
    if times_ns.ndim != 1 or np.any(times_ns[1:] < times_ns[:-1]):
        # 不排序隐藏上游执行顺序错误。
        raise ValueError("时间轴必须为一维非递减")


def _readonly(values: np.ndarray) -> np.ndarray:
    """复制局部列并标为只读，不修改调用者共享输入。

    参数: values为ndarray列；允许非连续输入视图。
    返回: 本层持有的独立只读连续副本。
    异常: NumPy分配错误传播；不宣称整体执行器内存有界。
    """
    # 明确所有权，调用者后续修改原数组不会污染结果。
    result = values.copy()
    # 只读约定防止其他规则普通原地写入共享历史。
    result.flags.writeable = False
    # 返回本层副本，不更改调用者原writeable标志。
    return result


@dataclass(frozen=True)
class SignalArray:
    """保存一个信号的规范历史，将值、时间、有效性和质量分列存储。

    所有列shape=(Ni,)，时间int64且严格递增。values保持声明dtype，enum使用
    int64代码及固定标签域；valid为bool，quality为uint16。无效值只作占位，
    原诊断仍可从series.samples获取。构造时独立复制列并设只读；这是NumPy
    写保护约定，不能作为防恶意内存改写保证。
    """

    series: SignalSeries  # 原规范样本/来源/绑定，提供完整身份。
    times_ns: np.ndarray  # (Ni,) int64纳秒。
    values: np.ndarray  # (Ni,) 声明数值/bool或enum int64编码。
    valid: np.ndarray  # (Ni,) bool，invalid占位不参加计算。
    quality: np.ndarray  # (Ni,) uint16，最高质量位256。
    labels: tuple[str, ...] = ()  # enum代码对应标签，其他dtype为空。

    def __post_init__(self) -> None:
        """校验列布局，再复制持有只读数组。

        参数: 无；读取series及Ni等长typed列/labels。
        返回: None；调用者数组保持原状，本对象列独立。
        异常: TypeError/ValueError为dtype/形状/质量矛盾或不匹配历史。
        """
        # 当前模型需要真实规范序列。
        if not isinstance(self.series, SignalSeries):
            # 不接只有名字的列声明。
            raise TypeError("SignalArray需要SignalSeries")
        # 时间完整且非递减，下面进一步要求规范后严格递增。
        _require_axis(self.times_ns)
        # 声明dtype由当前冻结定义提供，不根据NumPy自动类型提升猜测。
        dtype = self.series.bindings.resolve(self.series.name).dtype
        # 值/有效性/质量必须都是完整列，不接mask subclass。
        if any(not isinstance(column, np.ndarray) or isinstance(column, np.ma.MaskedArray)
               for column in (self.values, self.valid, self.quality)):
            # 质量不能靠masked数组隐藏缺项。
            raise TypeError("signal列必须为完整ndarray")
        # 单列形状和实际样本数量必须一致。
        if any(column.shape != self.times_ns.shape for column in (self.values, self.valid, self.quality)) or len(self.times_ns) != len(self.series.samples):
            # 禁止广播补齐短列。
            raise ValueError("signal列形状/样本数量不一致")
        # 64位整数不为拼表而转换浮点，质量16位足够全部标志。
        if self.values.dtype != DTYPE_TABLE[dtype] or self.valid.dtype != np.dtype("bool") or self.quality.dtype != np.dtype("uint16"):
            # 不隐式cast错误布局。
            raise TypeError("signal列dtype不匹配声明")
        # 规范后的历史每时刻最多一次信号提交。
        if np.any(self.times_ns[1:] <= self.times_ns[:-1]):
            # 同时间候选须先在SignalSeries执行政策。
            raise ValueError("规范历史时间必须严格递增")
        # 数组质量位需为已知非负组合，有效掩码不能与原因矛盾。
        if np.any(self.quality > 511) or np.any(self.valid & (self.quality != 0)) or np.any(~self.valid & (self.quality == 0)):
            # 质量不能被有效性布尔掩码隐藏。
            raise ValueError("signal有效性与质量矛盾或有未知位")
        # 标签元数据只接冻结tuple。
        if not isinstance(self.labels, tuple) or (dtype is not SignalDType.ENUM and self.labels):
            # 业务展示不把主数值列变成object。
            raise TypeError("labels必须为enum tuple域")
        # enum标签必须与当前定义完全一致，不能更换业务编码含义。
        expected_labels = tuple(dict.fromkeys(label for _, label in self.series.bindings.resolve(self.series.name).choices)) if dtype is SignalDType.ENUM else ()
        # 仅名字相同不足以证明相同业务域。
        if self.labels != expected_labels:
            # 拒绝空域或顺序/标签不匹配的数组声明。
            raise ValueError("enum标签与当前定义不符")
        # 布局构造入口再次关联实际历史坐标/掩码，防止伪装另一序列。
        if not np.array_equal(self.times_ns, np.array([item.time_ns for item in self.series.samples], dtype=np.int64)):
            # 不允许数组时间覆盖原身份。
            raise ValueError("数组时间与原规范观测不符")
        # 当前标志和valid必须来自原观测，不把invalid改为0/有效。
        if not np.array_equal(self.valid, [item.valid for item in self.series.samples]) or not np.array_equal(self.quality, [int(item.quality) for item in self.series.samples]):
            # 原质量在存储转换过程中不能丢失。
            raise ValueError("数组valid/quality与原观测不符")
        # 逻辑有效值同样关联原样本，不能用另一列数值冒充。
        expected_values = [self.labels.index(item.value) if self.labels else item.value for item in self.series.samples if item.valid]
        # 无效占位可不同，但任何有效值必须保持声明和原观测事实。
        if not np.array_equal(self.values[self.valid], np.array(expected_values, dtype=DTYPE_TABLE[dtype])):
            # 不允许存储转换篡改正常观测。
            raise ValueError("数组有效值与规范观测不符")
        # 每列独立复制并只读，调用者原对象不被更改。
        for name in ("times_ns", "values", "valid", "quality"):
            # 只访问本dataclass已声明列，不是表达式对象反射。
            object.__setattr__(self, name, _readonly(getattr(self, name)))


def build_signal_array(series: SignalSeries) -> SignalArray:
    """将规范逻辑样本存为按声明dtype的只读列，不进行归一化算术。

    参数: series为SignalSeries；有效值已通过dtype/枚举域检查。
    返回: SignalArray；invalid存储占位0/False，仅valid位置可计算。
    异常: TypeError为序列；结构/分配异常传播。
    """
    # 不把自由样本字典直接转数组绕过校验。
    if not isinstance(series, SignalSeries):
        # 先形成真正规范序列再接数组层。
        raise TypeError("build_signal_array需要SignalSeries")
    # 冻结定义提供输出存储dtype。
    definition = series.bindings.resolve(series.name)
    # 标签按明示choices首次出现顺序编码，不推断业务含义。
    labels = tuple(dict.fromkeys(label for _, label in definition.choices)) if definition.dtype is SignalDType.ENUM else ()
    # 稳定固定整数域仅用于逻辑enum存储。
    label_codes = {label: code for code, label in enumerate(labels)}
    # 数据装箱阶段允许Python遍历，实际查询用批量索引，不叫该步骤数值内核。
    values = [label_codes[item.value] if item.valid and labels else item.value if item.valid else 0 for item in series.samples]
    # 规范化无效原值保留series.samples，不强行写到不兼容数值dtype。
    return SignalArray(series, np.array([item.time_ns for item in series.samples], dtype=np.int64),
                       np.array(values, dtype=DTYPE_TABLE[definition.dtype]),
                       np.array([item.valid for item in series.samples], dtype=np.bool_),
                       np.array([int(item.quality) for item in series.samples], dtype=np.uint16), labels)


@dataclass(frozen=True)
class AlignedArray:
    """保存查询轴上的保持结果，以及每个结果所用的原样本索引。

    所有列shape=(N,)并独立只读。sample_indices=-1表示无历史，不能直接
    用来取数组末项；非负索引可从history.series.samples取得原诊断。
    actual_update只在当前会话视图中真实更新时成立。无效values仅为存储占位，
    必须结合valid与quality决定能否计算。
    """

    history: SignalArray  # 原列及完整绑定身份。
    times_ns: np.ndarray  # (N,) 当前查询轴int64。
    values: np.ndarray  # (N,) 与历史相同dtype。
    valid: np.ndarray  # (N,) 可使用掩码。
    quality: np.ndarray  # (N,) uint16原因组合。
    sample_indices: np.ndarray  # (N,) int64，-1为没有历史。
    actual_update: np.ndarray  # (N,) bool，计时器不伪造更新。

    def __post_init__(self) -> None:
        """校验对齐结果形状并复制只读，保持局部所有权。

        参数: 无；各列须为与查询轴等长的一维数组。
        返回: None；所有结果列独立只读副本。
        异常: TypeError/ValueError为内部结果结构或质量矛盾。
        """
        # 结果必须关联真实原列。
        if not isinstance(self.history, SignalArray):
            # 不允许无来源的结果列。
            raise TypeError("aligned需要SignalArray history")
        # 查询轴契约与输入严格一致。
        _require_axis(self.times_ns)
        # 所有输出列与当前查询长度一致。
        columns = (self.values, self.valid, self.quality, self.sample_indices, self.actual_update)
        # 不接广播列或masked结果。
        if any(not isinstance(column, np.ndarray) or isinstance(column, np.ma.MaskedArray) or column.shape != self.times_ns.shape for column in columns):
            # 结果维度不能靠广播补齐。
            raise ValueError("aligned结果列形状不一致")
        # 输出存储dtype保持原信号，索引整数与质量16位独立。
        if tuple(column.dtype for column in columns) != (self.history.values.dtype, np.dtype("bool"), np.dtype("uint16"), np.dtype("int64"), np.dtype("bool")):
            # 不隐藏数据类型提升或缺失索引。
            raise TypeError("aligned结果dtype不匹配")
        # 无历史索引唯一哨兵为-1，其他位置必须能关联原观测。
        if np.any(self.sample_indices < -1) or np.any(self.sample_indices >= len(self.history.times_ns)):
            # 索引不能越界泄漏另一信号输入。
            raise ValueError("aligned原样本索引超界")
        # 有效结果没有禁止质量，无效必须保留原因。
        if np.any(self.quality > 511) or np.any(self.valid & (self.quality != 0)) or np.any(~self.valid & (self.quality == 0)):
            # 不接受只有bool而无质量的UNKNOWN。
            raise ValueError("aligned有效性与质量矛盾")
        # 本结果独立复制，只读历史和调用者轴不被修改。
        for name in ("times_ns", "values", "valid", "quality", "sample_indices", "actual_update"):
            # 访问已声明结构字段，无任意对象执行。
            object.__setattr__(self, name, _readonly(getattr(self, name)))


def align_numpy(history: SignalArray, times_ns: np.ndarray, *, point: bool = False, strict_before: bool = False) -> AlignedArray:
    """批量取最新样本，结合整数有效期及观测范围计算保持结果。

    参数:
        history (SignalArray): 当前信号的已校验只读历史。
        times_ns (ndarray[int64], shape=(N,)): 非递减整数纳秒查询轴。
        point (bool): 默认False，连续范围左闭右开；True包含真实观测末端。
        strict_before (bool): 默认False；True只取sample_time < t的样本，
            在当前t检查有效期和来源范围，不计算可能溢出的t-1。
    返回:
        AlignedArray: 等长值列、有效掩码、质量原因、原索引及实际更新证据。
        值类型保持原声明，最新无效更新仍覆盖旧值；无历史使用索引-1。
    异常:
        TypeError或ValueError: 历史、模式标志、时间列类型、形状或顺序错误。
        MemoryError: 输出或临时数组分配失败。
    处理流程:
        用searchsorted查最新更新，先排除会话外索引，再按整数差计算有效期，
        最后叠加来源缺失原因。有效期始终要求age < valid_for_ns。
    副作用:
        输入只读使用，结果列由模型复制持有；输出和临时列占用O(N)空间。
    """
    # 数组入口不接受参考结果或随意字典。
    if not isinstance(history, SignalArray) or type(point) is not bool or type(strict_before) is not bool:
        # bool与数值开关区分，避免端点契约误用。
        raise TypeError("数组对齐需要SignalArray及bool point")
    # 查询时间不cast，避免大整数精度损失。
    _require_axis(times_ns)
    # 最新历史包含invalid更新，不能先过滤有效点。
    indices = np.searchsorted(history.times_ns, times_ns, side="left" if strict_before else "right").astype(np.int64) - 1
    # 当前会话和来源来自已校验结构，不借另一列延长。
    series, session = history.series, history.series.bindings.session
    # 连续末端排除；点模式显式包含真实末端。
    domain = (times_ns >= session.domain_start_ns) & ((times_ns <= session.domain_end_ns) if point else (times_ns < session.domain_end_ns))
    # 会话外没有输入引用，保持-1哨兵。
    indices[~domain] = -1
    # -1绝不能直接取数组末元素。
    has_sample = indices >= 0
    # 所有输出以明确掩码初始化，不让垃圾占位参加计算。
    values = np.zeros(times_ns.shape, dtype=history.values.dtype)
    # 没有历史时未知，正常数值0不受此初始化影响。
    valid = np.zeros(times_ns.shape, dtype=np.bool_)
    # 原原因不丢失，无历史明确MISSING。
    quality = np.full(times_ns.shape, int(QualityFlag.MISSING), dtype=np.uint16)
    # 计时器/EOF不自动产生实际更新。
    actual = np.zeros(times_ns.shape, dtype=np.bool_)
    # 非空有效索引才进行批量取值，空历史不会访问末项。
    selected = indices[has_sample]
    # 只把可定位样本列赋给对应查询位置。
    values[has_sample] = history.values[selected]
    # 原输入质量/有效性被原样传播。
    quality[has_sample] = history.quality[selected]
    # 最新invalid会覆盖旧valid，不作历史回退。
    valid[has_sample] = history.valid[selected]
    # 实际更新与当前查询精确时间相等，保持整数纳秒比较。
    actual[has_sample] = times_ns[has_sample] == history.times_ns[selected]
    # 查询与被选样本都在同一已校验会话跨度内，int64差已证明安全。
    ages = times_ns[has_sample] - history.times_ns[selected]
    # TTL边界始终排除，批量比较不先把绝对时间转float。
    stale = np.zeros(times_ns.shape, dtype=np.bool_)
    # 仅有历史位置产生到期诊断。
    stale[has_sample] = ages >= series.bindings.resolve(series.name).valid_for_ns
    # STALE叠加而非覆盖上游无效原因。
    quality[stale] |= np.uint16(QualityFlag.STALE)
    # 来源观测域同样区分连续/点模式。
    source = (times_ns >= series.observation_start_ns) & ((times_ns <= series.observation_end_ns) if point else (times_ns < series.observation_end_ns))
    # 来源结束只影响这一信号列，并保留并列质量。
    quality[has_sample & ~source] |= np.uint16(QualityFlag.MISSING)
    # 基础质量策略全部非零禁止，不以isfinite替代整数/状态有效性。
    valid &= quality == 0
    # 原观测索引仍可追溯invalid占位来源，输出列由构造器独立只读。
    return AlignedArray(history, times_ns, values, valid, quality, indices, actual)
