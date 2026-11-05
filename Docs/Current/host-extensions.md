# 自定义分析算子（Python扩展）

Python程序可以补充三类分析能力：表达式中逐次计算一个值的函数、把一批样本汇成一个结果的样本统计，以及随时间输出新值的时序变换。Python提供算法实现并登记名称，配置只按名称调用；YAML不能任意导入或执行Python文件。负责登记并运行算法的Python程序称为宿主程序，这种方式也称为宿主扩展。

|扩展类型|配置中的调用位置|输入→输出|
|---|---|---|
|逐点函数 FunctionSpec|expr中的函数名，例如double_current(current)|同一时刻的输入值→一个值；可提供独立参考和NumPy实现|
|样本统计 ReductionSpec|calculations[].operation|一个统计范围内选中的有效真实样本→一个标量结果|
|时序变换 TransformSpec|transforms[].operation|每个输出时刻的窗口值和时长权重→该时刻的新值，可保存本次会话状态|

## 接入自定义算子

先运行本页随附完整Python示例，确认输入与结果；再修改算法回调。`ExtensionRegistry`把调用名与类型、单位和实现关联。加载计划和运行时须传入同一个注册对象，不能只在配置里写一个尚未登记的名字。

需要在已有信号分析中加入内部标定公式、样本统计或有状态的网格算法时，由维护该算法的 Python 程序创建注册表。普通 YAML 只引用注册名。这个例子用同一份 ASC 展示三种用法。先将[宿主程序](examples/temporal/host_extensions.py)、[宿主配置](examples/temporal/host-analysis.yaml)、[ASC](examples/temporal/meter.asc) 和 [DBC](examples/temporal/meter.dbc) 放在同一目录。

```powershell
python host_extensions.py --plan host-analysis.yaml --backend reference --work-dir host-ref
python host_extensions.py --backend numpy --work-dir host-numpy
```

`--plan` 接受配置文件路径。第一条命令指定当前目录的配置；第二条省略该选项，读取程序所在目录的 `host-analysis.yaml`。配置里的 ASC 和 DBC 均相对于所选配置文件定位。

`double_current` 将输入电流值加倍，select输出的四条有效记录为 20、40、80、10 A。`peak_reading` 接收选中样本，得到 **80 A，complete**。`best_grid_mean` 在每个输出时刻计算最近 0.12 秒的时间均值，并在状态里记住截至当时的最高均值。0.12、0.24、0.36、0.48 秒依次输出 10、20、30、30 A；最后一个窗口的当前均值已经回落至 22.5 A。

## 从程序传递注册表

下面是上方宿主程序的注册片段，放在 `double_reference`、`double_numpy` 两个回调定义之后；它依赖这些函数，不能单独运行。

```python
from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.core.types import SignalDType
from chronaxis.extensions import ExtensionRegistry, FunctionSpec, ValueSpec

amp = ValueSpec(SignalDType.FLOAT64, "A")
registry = ExtensionRegistry(functions=(
    FunctionSpec("double_current", "1", (amp,), amp, double_reference, double_numpy),
))
```

这一段只登记逐点函数。完整程序还向 `reductions`、`transforms` 传入各自的描述符。用 `load_analysis_plan(path, extensions=registry)` 或 `AnalysisPlan.from_dict(raw, extensions=registry)` 检查配置，再将**同一个对象**交给 `AnalysisRunner(backend, extensions=registry)`。普通 `python -m chronaxis run` 只有内置能力；使用这些宿主名字时运行上面的 Python 程序。可通过 `chronaxis.extensions.builtin_function_specs(4)` 查询内置逐点函数的签名、输入、常量、单位和后端等契约。

|注册类型|宿主收到什么|返回或保存什么|
|---|---|---|
|FunctionSpec|按声明顺序传入的参数。标量回调收 ScalarValue 元组；NumPy 回调收 NumericArray 元组，只传全部必要输入有效的行|返回同 dtype 声明的单值或同长列；每次调用结束释放为本次调用申请的临时内存额度|
|ReductionSpec|每个统计范围创建一个独立状态对象。`consume(values)` 收到已选、有效、真正更新的样本|该范围用 `finalize()` 返回一个 ScalarValue。声明 `mergeable=True` 才能合并同一注册与后端的两个状态|
|TransformSpec|每会话一个状态。`advance(time_ns, window_ns, values, weights_ns)` 收到当前网格、声明窗口、按先后排列的有效保持值和对应权重|返回这一格的 ScalarValue。可在后续网格复用状态，`history_ns` 是该操作允许的最大回看宽度|

`TransformSpec.interval_modes` 默认支持 actual、fixed、dbc，也可只声明本算法适用的模式。fixed/dbc 权重由相邻两次驱动信号更新之间的实际时间区间按实际重叠比折算，传入的 `time_ns` 始终是当前输出时刻。参考后端收到正整数或 Fraction 纳秒，数组后端收到 int64 纳秒列，含分数时为 float64 纳秒列。只处理整数纳秒权重的算法可声明 `interval_modes=("actual",)`。两后端仍各自需要实现。

工厂先收到管理其内存额度的 resources 对象，固定状态用 `state_bytes` 声明；动态空间在分配前 `reserve(n)`，不再使用时 `release(n)`。在 `cancel()` 中停止本次任务，在 `close()` 中释放自有资源。没有被任何请求结果依赖的时序变换不创建工厂状态。程序用名称、算法版本、输入输出类型与单位、可用后端及资源/历史设置识别一项注册实现，修改算法时更新版本。注册的 Python 回调作为受信任的宿主代码运行，请只登记自己愿意在该进程执行的实现。

## 描述符与回调完整参考

以下名称从`chronaxis.extensions`导入；完整可运行例已给出三类实现。None表示未提供某后端实现，不表示任意后端可用；至少提供一种，运行选定后端必须具备相应回调。

|构造签名|参数与返回|
|---|---|
|ValueSpec(dtype, unit)|dtype为SignalDType，unit为已登记单位；bool只用1，enum不直接接受；返回不可变输入／输出声明|
|FunctionSpec(name, version, inputs, output, reference=None, numpy=None)|inputs为ValueSpec元组，output为一个ValueSpec；reference/numpy为下表回调；返回逐点描述符|
|ReductionSpec(name, version, input, output, reference=None, numpy=None, state_bytes=0, mergeable=False)|input/output为数值ValueSpec；回调是创建状态对象的函数；state_bytes为非负整数固定内存字节；mergeable为bool|
|TransformSpec(name, version, input, output, reference=None, numpy=None, state_bytes=0, history_ns=0, interval_modes=('actual','fixed','dbc'))|数值输入输出；history_ns必须显式给正int64纳秒，不可沿用无效的0；interval_modes为非空、不重复的支持模式元组|
|ExtensionRegistry(functions=(), reductions=(), transforms=())|三类参数各为对应描述符元组；返回不可变注册表；名称在三类中均不能重复或占用内置名|

name为合法分析名称，version为非空算法版本文字；改变算法后由作者更新version。类型、单位、名称、资源参数非法时构造失败。注册表不替用户验证算法数学正确性。

|接口|收到的参数|返回与调用时机|
|---|---|---|
|逐点reference(args, resources)|按声明顺序的ScalarValue元组、临时内存额度接口|返回与声明匹配的ScalarValue；只有必要输入有效时调用|
|逐点numpy(args, resources)|按声明顺序的NumericArray元组，只含本批必要输入均有效的行|返回同长度、声明类型的NumericArray；不能改变行顺序|
|统计reference(resources)／numpy(resources)|本统计范围可申请内存的接口|返回独立状态对象；每个范围单独创建，跨批次保存累计值|
|统计state.consume(values)|参考实现为ScalarValue序列，数组实现为NumericArray；已筛选有效真实更新|返回None，把这批数据加入本范围状态|
|统计state.finalize()|无参数|返回声明类型的ScalarValue；范围结束时生成结果|
|统计state.merge(other)|同一算法、版本和后端的另一个状态|仅声明mergeable=True时必须提供；合并到当前状态|
|变换reference(resources)／numpy(resources)|本次会话的内存额度接口|返回本会话独立状态对象|
|变换state.advance(time_ns, window_ns, values, weights_ns)|实际输出时刻、窗口宽度、按顺序的有效保持值及对应权重|返回本格ScalarValue；状态可用于后续输出，回看不得超过history_ns|
|状态state.cancel()／close()|无参数|取消通知／最终释放自有资源；正常、失败、取消路径均应能安全清理|

回调签名、返回类型、数组长度或质量不符合声明会使运行失败，原异常保留供定位。不要返回看似有效的占位零来绕过失败。输出的ScalarValue／NumericArray按其valid和quality表达缺失或数值错误。
