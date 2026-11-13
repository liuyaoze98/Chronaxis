# 连续记录的多进程读取

同一次充电或试验分成多个 ASC/BLF 文件时，把这些文件放在同一个 `sources` 来源中，用 `execution.process_count` 设置读取、解析和 DBC 解码的工作进程上限。主进程连续处理信号、事件、有效期和计算，最终得到一套会话结果。切换文件不会结束事件，也不会重新开始积分。

例如一段充电记录分成十个文件，配置最多 4 个工作进程可让多个文件同时读取和解码，最终仍输出这一段充电的结果。只需同帧逐报文累计时，还可选择[高性能积分器](fast-energy.md)，其工作进程同时计算单帧贡献。

## 最小可运行配置

下载完整的 [continuous-parallel.yaml](examples/continuous-parallel.yaml)，与随册 `data/can/session` 和 `teaching.dbc` 一起使用。从 examples 目录运行：

```powershell
chronaxis validate continuous-parallel.yaml
chronaxis explain continuous-parallel.yaml
chronaxis run continuous-parallel.yaml --output session-result
```

```yaml
config_version: 4                   # 选择分析配置结构版本；填写整数4
dataset:                            # 定义本次分析的身份与可选时间范围
  name: continuous_charge           # 命名整个会话，不为每个文件建立新会话
sources:                            # 列出输入来源；本例只有一个连续CAN来源
  - paths:                          # 按列表顺序接续这些记录文件
      - data/can/session/part1.asc  # 本来源的第一个分卷
      - data/can/session/part2.asc  # 同一会话的下一个分卷
    dbc_by_channel:                 # 指定各通道解释报文字节所需的DBC
      '1': data/can/teaching.dbc    # 通道1使用此相对路径的DBC
signals:                            # 定义计算可以引用的信号
  - name: power                     # 为输入功率取分析名称
    field:                          # 在DBC中定位信号
      frame_id: '0x100'             # 信号所在报文的ID
      signal: Power                 # DBC中的信号名称
    valid_for: 3s                   # 每次有效更新最多沿用3秒，超时后值未知
calculations:                       # 列出要得到的计算结果
  - name: energy                    # 命名能量结果
    operation: integral             # 将功率乘实际持续时间后累计
    expr: power                     # 使用上面已定义的功率信号
execution:                          # 设置本次分析的执行方式及资源
  process_count: 4                  # 最多4个文件读取/解码工作进程，另有主进程
```

本例写 `4`，但只有两个输入文件，因此最多使用两个文件工作进程。`4` 是推荐起点，省略时程序仍默认 `1`；只有一个文件时，调高上限不会把该文件拆开。

第一个文件在 0、1 秒提供 2、4 W，第二个文件在 3、4 秒提供 8、10 W，来源观测到 6 秒。1～3 秒跨越文件边界，仍使用 4 W：总能量为 `2×1 + 4×2 + 8×1 + 10×2 = 38 J`。例子中每个有效值都在 3 秒有效期内。

运行完成后，从本次完成清单的 `outputs` 定位会话结果 CSV，查看第一条记录：`energy（J）` 应为 **38**，同一行的 `energy：状态` 为「完整」，说明为空。单位已写在数值列名中。`explain` 中的 `source_execution` 应列出两个文件和最多两个读取进程；这表示计划上限，不是测量出的加速倍数。

## 文件的时间如何接续

`sources[].file_merge` 控制同一来源各文件的记录顺序。它与进程数分别设置；增大进程数不会自动排序、移动时间或删除重复报文。

|值|行为|如何选择|
|---|---|---|
|`concatenate`，默认|依次消费 `paths` 中的文件，保留文件内部记录顺序。按该任务原有的输入检查范围检查时间回退。|已确认分卷按时间接续时使用。目录和通配符先按自然文件名顺序展开。|
|`time_order`|先检查每个文件内部所需记录的时间，再按“时间、文件列表位置、文件内记录序号”稳定归并。|文件时间有交叠，且已确认时间坐标可直接比较时使用。文件内回退仍报错，不通过排序修复。|

两个文件都从 0 秒计时不证明它们同步。已知时间偏移应按[来源时间配置](inputs.md)明确填写；没有依据时先核实采集记录。两条同刻、同内容的报文都会保留：逐消息累计分别处理；普通信号按 `same_time_policy` 选择或报错。

[continuous-time-order.yaml](examples/continuous-time-order.yaml)给出相对完整的配置：两个文件各自有序但彼此交错，明确选择 `time_order`，仍得到 38 J 和一段跨文件活动。配置增加共享内存、磁盘配额和事件规则，所有引用均已在文件中定义。

## 进程数、接口和支持范围

|设置|填写规则与作用|
|---|---|
|`execution.process_count`|正整数，默认 `1`。不接受 0、负数、小数、文本、布尔值或 `null`。表示本任务共用的读取/解码进程上限，不包含主进程；实际数量不超过输入文件数。不会根据 CPU 数量自动增加。|
|普通 CLI `--process-count`|适用于 `run`、`validate`、`explain`。显式值覆盖配置，只影响本次调用。|
|`AnalysisRunner.run/validate/explain(..., process_count=...)`|仅关键字参数。`None` 沿用计划；正整数覆盖本次上限，不修改原计划。非法覆盖抛 `ValueError`。|

当前并行读取和时间归并支持一个 CAN 来源，格式为 ASC、BLF 或两者混合，并使用 `reader.decode_scope: requested`。多个来源、CSV/内存来源或 `all` 解码会在执行前被拒绝；这些任务可以继续使用默认单进程接续路径。独立批量任务的工作进程内不能再建立文件池；一次连续分析请直接调用普通 `run`。

默认 `1` 加 `concatenate` 时，纯 BLF、ASC和混合来源均在当前进程读取与解码，不另建文件读取工作进程。显式 `time_order` 使用文件工作进程，即使上限为 1。`explain` 的 `source_execution` 给出文件数、归并方式、读取进程上限和是否使用归并暂存；这是静态声明，不是实测运行进程数，也没有扫描日志来证明时间有序。

```powershell
chronaxis validate continuous-parallel.yaml --process-count 4
chronaxis explain continuous-parallel.yaml --process-count 4
chronaxis run continuous-parallel.yaml --process-count 4 --output session-result
```

Python 中在主函数保护内启动实际运行，适用于 Windows 的多进程启动方式：

```python
from chronaxis import AnalysisRunner, load_analysis_plan

def main():
    plan = load_analysis_plan("continuous-parallel.yaml")
    with AnalysisRunner().run(plan, process_count=4) as result:
        result.write("session-result")

if __name__ == "__main__":
    main()
```

## 资源、失败与性能

`concatenate` 允许后续文件有限预读，满缓冲时等待。`time_order` 将各文件已校验的记录写入本次临时目录，全部文件读取成功后进行有界归并；临时磁盘成本受 `execution.spool_quota_bytes` 的累计额度约束。文件多时，每个归并输入还需要缓冲空间，额度不足会停止。

工作进程的受管理解码空间、传输缓冲和主进程状态共用 `memory_budget_bytes`，不是每个进程分别获得这份额度。Python 和第三方库的实际内存仍可能高于这项管理估算。预算不足、输入错误、工作进程崩溃或取消都不能作为正常文件结束；不会发布缺少后续文件的正常结果。关闭会回收本任务的进程及归并暂存，保留原始文件和已发布结果。

更多进程不保证更快。严格按文件接续可能受当前文件速度限制，时间归并增加暂存读写，连续计算仍在主进程完成。用相同输入、计算、输出和归并方式比较 1/2/4/8，并计入完整运行时间；不要用多次独立试验的批量耗时替代一次连续会话的耗时。
