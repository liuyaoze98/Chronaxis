"""对一列纳秒时间执行固定偏移或计算相邻时间差，返回独立的新数组。

输入必须是shape=(N,)、dtype=int64的ndarray，不接受浮点、uint64、object或
MaskedArray。先通过比较和布尔掩码证明加减安全，再执行NumPy数组运算，
保留同时间的零差值，允许空输入。输入只读使用，不排序或去重。
本模块只共享时间常量和标量偏移校验，不调用Python参考数值内核。输出和
临时掩码占用O(N)空间；没有文件操作、CAN访问或全局状态。这里只实现时间
运算，不能据此认定全部分析均已有数组实现。
"""

# NumPy仅在显式选择本模块时导入；核心时间入口本身不依赖它。
import numpy as np

# 共享已经校验的整数协议；不导入参考加减函数。
from .conversion import INT64_MAX, INT64_MIN, TimeOverflowError, require_int64_ns


def _require_time_array(times: np.ndarray) -> None:
    """检查数组形状和定宽dtype，不以转换/广播修补错误输入。

    参数:
        times (ndarray): shape=(N,)、dtype=int64的纳秒列。
    返回:
        None: 只读验证，不转换或复制输入。
    异常:
        TypeError: 非ndarray、MaskedArray或dtype不为原生int64。
        ValueError: 不是一维列数组。
    """
    # 检查真实数组，禁止把Python循环包装为隐式批量转换。
    if not isinstance(times, np.ndarray) or np.ma.isMaskedArray(times) or times.dtype != np.dtype("int64"):
        # 时间坐标不能缺失；拒绝整个MaskedArray协议，不能偷偷丢掩码或强制转换数据类型。
        raise TypeError("时间数组必须为无MaskedArray掩码、dtype=int64的ndarray")
    # 核心是单列时间轴，不允许维度广播掩盖调用错误。
    if times.ndim != 1:
        # 同样拒绝标量、矩阵或多维输入。
        raise ValueError("时间数组形状必须为(N,)")


def shift_times_numpy(times: np.ndarray, offset_ns: int) -> np.ndarray:
    """给全部时间坐标添加固定纳秒偏移，运算前先检查每项结果的范围。

    参数:
        times (ndarray[int64], shape=(N,)): 纳秒坐标，允许负值和未排序输入。
        offset_ns (Integral): int64范围内的固定偏移，单位为纳秒。
    返回:
        ndarray[int64], shape=(N,): 独立的新数组；输入不修改，空输入返回空数组。
    异常:
        TypeError或ValueError: 输入类型、数据类型或形状不符合要求。
        TimeOverflowError: 偏移本身或任一偏移后坐标超出int64范围。
    副作用:
        只分配输出和比较掩码，不调用参考相加函数或读取文件。
    """
    # 验证数组形状和数据类型，不先做可能有损的转换。
    _require_time_array(times)
    # 标量协议可以共享，数值批量算法独立实现。
    offset = require_int64_ns(offset_ns, "offset_ns")
    # 正偏移的上界MAX-offset在Python整数域计算，没有中间wrap。
    if offset > 0 and np.any(times > INT64_MAX - offset):
        # 任一位置失败则整次时间映射拒绝，不填0丢弃数据。
        raise TimeOverflowError("固定偏移导致时间上溢")
    # 负偏移用MIN-offset为安全下界，包含MIN等于合法。
    if offset < 0 and np.any(times < INT64_MIN - offset):
        # 该检查在ufunc之前，保证不执行下溢。
        raise TimeOverflowError("固定偏移导致时间下溢")
    # 所有位置安全后执行一次int64数组运算，返回O(N)独立新数组。
    return np.add(times, np.int64(offset))


def time_deltas_numpy(times: np.ndarray) -> np.ndarray:
    """计算非递减时间轴的相邻纳秒差，先检查顺序及跨度再做数组减法。

    参数:
        times (ndarray[int64], shape=(N,)): 非递减纳秒轴，允许相同时间。
    返回:
        ndarray[int64], shape=(max(N-1, 0),): 独立的新数组，保存非负相邻跨度。
    异常:
        TypeError或ValueError: 输入类型、数据类型或形状错误，或者时间严格回退。
        TimeOverflowError: 两端坐标均合法，但相邻跨度超过int64上限。
    处理流程:
        对负左端计算MAX+left作为安全右端阈值，右端严格超出阈值时拒绝。
        全部检查通过后再减法，不先计算可能回绕的差值。
    副作用:
        输入只读使用；输出、阈值和掩码需要与输入长度成比例的空间。
    """
    # 验证真实时间列，禁止浮点绝对时间参与差值。
    _require_time_array(times)
    # 两个shape=(N-1,)只读视图，无永久共同矩阵或输入复制。
    left, right = times[:-1], times[1:]
    # 比较原整数即可判断回退，不会在差值中间发生溢出。
    if np.any(right < left):
        # 相等合法，来源内乱序不排序或忽略。
        raise ValueError("时间序列必须非递减")
    # 只有负left会产生跨符号大跨度风险，掩码shape=(N-1,)。
    negative_left = left < 0
    # 阈值数组独立分配；非负left位置初始化0但不会参与溢出判定。
    safe_right_limit = np.zeros_like(left)
    # 负left+MAX总在int64范围内；where防止非负位置执行溢出加法。
    np.add(left, np.int64(INT64_MAX), out=safe_right_limit, where=negative_left)
    # 等于阈值的MAX跨度合法，严格超过才拒绝。
    if np.any(negative_left & (right > safe_right_limit)):
        # 在subtract前失败，不保留wrap值或转float回避问题。
        raise TimeOverflowError("相邻时间跨度超出int64范围")
    # 经过所有检查后，合法结果由真实数组减法一次计算。
    return np.subtract(right, left)
