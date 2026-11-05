"""演示宿主注册的三类操作。输入是同目录中的ASC、DBC和host-analysis.yaml。

参数: --plan指定配置文件，省略时读取程序同目录的host-analysis.yaml；
--backend选择reference/numpy，--work-dir给本次运行的工作目录。
返回: 在终端打印已核实的电流结果。异常: 输入、预算或宿主回调错误会传播。
维护者：liuyaoze。
"""
import argparse
from math import isfinite
from pathlib import Path
import numpy as np
from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.numeric_numpy import NumericArray
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.extensions import ExtensionRegistry, FunctionSpec, ReductionSpec, TransformSpec, ValueSpec


AMP = ValueSpec(D.FLOAT64, "A")


def double_reference(args, resources):
    """参数: 有效标量与资源。返回: 两倍电流。异常: 数值错误。"""
    value = 2.0 * args[0].value
    return ScalarValue(value, D.FLOAT64) if isfinite(value) else ScalarValue(None, D.FLOAT64, False, Q.NONFINITE)


def double_numpy(args, resources):
    """参数: 有效样本列与资源。返回: 两倍电流列。异常: 预算或数值错误。"""
    column = args[0]
    temporary = 16 * len(column.values)
    resources.reserve(temporary)
    try:
        with np.errstate(over="ignore"):
            values = np.multiply(column.values, 2.0)
        valid = np.isfinite(values)
        quality = np.where(valid, 0, int(Q.NONFINITE)).astype(np.uint16)
        return NumericArray(D.FLOAT64, values, valid, quality)
    finally:
        resources.release(temporary)


class Peak:
    """一段样本范围独享的最大值状态，只持有一个已声明的标量。"""
    def __init__(self, resources):
        """参数: 资源视图。返回: 空状态。异常: 无。"""
        self.peak = None

    def consume(self, values):
        """参数: 已选真实样本。返回: None。异常: 输入类型错误。"""
        value = np.max(values.values).item() if isinstance(values, NumericArray) else max(v.value for v in values)
        self.peak = value if self.peak is None else max(self.peak, value)

    def merge(self, other):
        """参数: 另一同型状态。返回: None。异常: 无。"""
        if other.peak is not None:
            self.peak = other.peak if self.peak is None else max(self.peak, other.peak)

    def finalize(self):
        """参数: 无。返回: 已选样本最大值。异常: 本例的非空范围须先消费。"""
        return (ScalarValue(self.peak, D.FLOAT64) if self.peak is not None else
                ScalarValue(None, D.FLOAT64, False, Q.MISSING))

    def cancel(self):
        """参数: 无。返回: None。异常: 无。"""

    def close(self):
        """参数: 无。返回: None。异常: 无。"""
        self.peak = None


class BestGridMean:
    """每次会话从头记录各个网格均值的历史最高值。"""
    def __init__(self, resources):
        """参数: 资源视图。返回: 新状态。异常: 无。"""
        self.highest = None

    def advance(self, time_ns, window_ns, values, weights_ns):
        """参数: 实际网格、窗口、有效区间与所选纳秒权重。返回: 历史最高均值。异常: 空权重。"""
        if isinstance(values, NumericArray):
            average = np.average(values.values, weights=weights_ns).item()
        else:
            average = sum(v.value * w for v, w in zip(values, weights_ns)) / sum(weights_ns)
        self.highest = average if self.highest is None else max(self.highest, average)
        return ScalarValue(self.highest, D.FLOAT64)

    def cancel(self):
        """参数: 无。返回: None。异常: 无。"""

    def close(self):
        """参数: 无。返回: None。异常: 无。"""
        self.highest = None


def main():
    """参数: CLI配置路径、后端及工作目录。返回: None，向终端写实际结果。异常: 配置或运行错误。"""
    cli = argparse.ArgumentParser()
    cli.add_argument("--plan", type=Path, default=Path(__file__).with_name("host-analysis.yaml"),
                     help="Analysis YAML (defaults to host-analysis.yaml beside this program)")
    cli.add_argument("--backend", choices=("reference", "numpy"), default="numpy")
    cli.add_argument("--work-dir", type=Path, required=True)
    args = cli.parse_args()
    registry = ExtensionRegistry(
        functions=(FunctionSpec("double_current", "1", (AMP,), AMP, double_reference, double_numpy),),
        reductions=(ReductionSpec("peak_reading", "1", AMP, AMP, Peak, Peak, state_bytes=256, mergeable=True),),
        transforms=(TransformSpec("best_grid_mean", "1", AMP, AMP, BestGridMean, BestGridMean,
                                  state_bytes=256, history_ns=120_000_000),),
    )
    plan = load_analysis_plan(args.plan, extensions=registry)
    with AnalysisRunner(args.backend, extensions=registry).run(plan, work_dir=args.work_dir) as result:
        for row in result.iter_calculations():
            print(row.calculation_id, row.value, row.unit, row.status)
        for row in result.iter_selections():
            if row.valid:
                print(row.calculation_id, f"{row.time_ns / 1e9:.2f}s", row.value, row.unit)


if __name__ == "__main__":
    main()
