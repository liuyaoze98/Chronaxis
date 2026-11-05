"""对已裁剪的有限保持区间求一个滚动网格值。

权重是实际纳秒或原周期按实际重叠分摊的计量纳秒。独立参考路径使用精确
有理数累计，数组路径对当次窗口执行 NumPy 掩码和缩放加权归约。历史维护、
覆盖门槛、网格原点和事件均由调用者处理；本模块不保存上一个窗口。
"""
from fractions import Fraction
from math import frexp, isfinite, ldexp
from .numeric import ScalarValue
from .types import SignalDType as D, QualityFlag as Q


def rolling_value(operation, backend, values, weights, conversion, dtype):
    """计算选中窗口值。参数: 操作、后端、有效数列、正权重、目标换算、类型。返回: ScalarValue。异常: 配置错误。"""
    if operation in ('rolling_minimum','rolling_maximum'):
        if backend=='reference':
            from .affine import affine_reference
            value=(min if operation=='rolling_minimum' else max)(values)
            return affine_reference(ScalarValue(value,dtype),conversion.factor,conversion.offset,conversion.dtype(dtype))
        import numpy as np
        from .numeric_numpy import DTYPES, NumericArray
        from .affine_numpy import affine_numpy
        col=np.asarray(values,dtype=DTYPES[dtype])
        result=(np.min if operation=='rolling_minimum' else np.max)(col)
        column=NumericArray(dtype,np.array([result],dtype=DTYPES[dtype]),np.ones(1,dtype=bool),np.zeros(1,dtype='uint16'))
        converted=affine_numpy(column,conversion.factor,conversion.offset,conversion.dtype(dtype))
        valid=bool(converted.valid[0])
        return ScalarValue(converted.values[0].item() if valid else None,converted.dtype,valid,Q(int(converted.quality[0])))
    # 整数进入浮点统计须无损。无效样本不能经插值或舍入变为普通值。
    if dtype in (D.INT64,D.UINT64) and any(int(float(v))!=v for v in values):
        return ScalarValue(None,D.FLOAT64,False,Q.PRECISION_LOSS)
    if backend=='reference':
        total=sum(Fraction(v)*w for v,w in zip(values,weights))
        measure=sum(weights) if operation=='rolling_time_mean' else 10**9
        exact=total*Fraction(conversion.factor)/measure+Fraction(conversion.offset)
        try:
            number=float(exact)
        except OverflowError:
            return ScalarValue(None,D.FLOAT64,False,Q.NONFINITE)
        lost=number==0 and exact!=0
    else:
        import numpy as np
        numbers=np.asarray(values,dtype=np.float64)
        w=np.asarray(weights,dtype=np.float64)
        from .calculations_numpy import _sum_finite_numpy
        total_weight=float(np.sum(w))
        normalized=w/total_weight
        with np.errstate(under='ignore'):
            terms=numbers*normalized
        # 对极小项先放大再乘权重。真实纳秒和原驱动比例均有int64界限，
        # 2^512足以使这些暂存项不会因单项落入次正规范围就丢掉其合计。
        tiny=(np.abs(terms)<np.finfo('float64').tiny)&(numbers!=0)
        total,failed,quality=(_sum_finite_numpy(terms[~tiny]) if np.any(~tiny) else (0.,False,Q.NONE))
        if failed:
            return ScalarValue(None,D.FLOAT64,False,quality)
        extra_exponent=0
        if np.any(tiny):
            residual,failed,quality=_sum_finite_numpy(np.ldexp(numbers[tiny],512)*normalized[tiny])
            if failed:
                return ScalarValue(None,D.FLOAT64,False,quality)
            if abs(total)<=1:
                total=ldexp(total,512)+residual
                extra_exponent=-512
            else:
                total+=ldexp(residual,-512)
        mantissa,exponent=frexp(total)
        factor,ef=frexp(conversion.factor)
        scale,es=frexp(1 if operation=='rolling_time_mean' else total_weight/1e9)
        try:
            number=ldexp(mantissa*factor*scale,exponent+extra_exponent+ef+es)+conversion.offset
        except OverflowError:
            return ScalarValue(None,D.FLOAT64,False,Q.NONFINITE)
        lost=number==0 and total!=0 and not conversion.offset
    if not isfinite(number) or lost:
        return ScalarValue(None,D.FLOAT64,False,Q.NONFINITE if not isfinite(number) else Q.PRECISION_LOSS)
    return ScalarValue(number,D.FLOAT64)
