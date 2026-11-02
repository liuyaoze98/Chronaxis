"""以真实NumPy前缀累计实现有限贡献块的独立原序左折叠。

输入是已校验的有限float carry和按原求值顺序排列的有限float tuple；输出为
未舍入候选float。把carry作为第0项，再用add.accumulate逐步相加，保留跨批
左结合顺序，不先求块和，不用np.sum、补偿求和、向量化Python回调或参考内核。
任一中间累计非有限均拒绝整批，后续抵消不能把此前溢出恢复成正常结果。

本纯数值核不保存状态、来源或费用；调用方须在调用前预留当前有限(N+1,)输入、
累计与有限性临时列。本模块仅在明确选择NumPy且本批有贡献时由累计器加载，
不读取日志、DBC或文件，不把库加载和整个进程RSS声称为本层受控内存。
"""

# 数值运算独立于标准库参考路径；仅接受调用方已验证的当前有限块。
import numpy as np


def sum_numpy(carry: float, values: tuple[float, ...]) -> float:
    """从已有carry按原顺序一次生成整列前缀累计并核查所有中间值。

    参数: carry为有限原生float；values为按原序选出的有限原生float tuple，
        本函数由预算owner在完成贡献结构与顺序校验后调用。
    返回: float；无贡献时原carry不变，有贡献时取最后前缀，保持原浮点尾数。
    异常: OverflowError为任何中间累计非有限；NumPy分配、导入或取消原样传播。
        本核不提交累计器状态，费用及异常恢复由调用方管理。
    """
    chain = prefixes = None
    try:
        if not values:
            return carry
        # carry放在第0项而非最终再加块和，使每一项都承接真实前缀与跨批尾数。
        chain = np.empty(len(values) + 1, dtype=np.float64)
        chain[0] = carry
        chain[1:] = values
        with np.errstate(over="ignore", invalid="ignore", under="ignore"):
            prefixes = np.add.accumulate(chain, dtype=np.float64)
        # 全列检查能发现中途溢出，不能只看最终值或允许后续项抵消故障。
        if not np.all(np.isfinite(prefixes)):
            raise OverflowError("legacy_sum中间累计非有限，整批拒绝")
        return float(prefixes[-1])
    finally:
        # 异常被外部保留时也不能经本层frame保活未计费数组或选值tuple；
        # 不改写原输入、不清除异常traceback，只断开本函数的临时引用。
        chain = prefixes = values = None
