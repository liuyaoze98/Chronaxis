# 独立批量任务


如果有三辆车、三次互不相干的试验，可以给每次试验各写一个analysis.yaml，再用批量配置一起运行。每个任务有自己的信号状态、报警计时、等待响应队列和输出目录。

这和`execution.batch_rows`不是一回事。`batch_rows`只控制**一个任务一次处理多少信号样本**，不会重置状态；`batch run`调度**多个互相独立的任务**。同一次连续试验的part1.csv和part2.csv应放在同一来源的`paths`中，不能拆成两个独立任务后期望报警自动接续。

批量配置是单独文件，入口为`chronaxis batch run`或`load_batch_plan`/`run_batch`。用jobs列出不同分析配置，或用template与inputs把同一个分析模板应用到多个文件；两种写法不能混用。根级`process_count`控制分析工作进程数，例如填4表示最多四个工作进程同时执行独立任务。

## 完整批量配置

本页是独立批量文件，不嵌入普通分析配置。表中batch_version、jobs、process_count等均位于批量文件根级；子任务列表项的完整路径例如`jobs[].plan`。

[batch-minimal.yaml](examples/batch-minimal.yaml)只引用主ASC分析例analysis.yaml，任务名自动生成，默认顺序运行，能量为38J。

[batch-extended.yaml](examples/batch-extended.yaml)增加另一个ASC电压分析，最多两个任务同时运行。两个结果分别为38J和13V·s；它们是独立分析，不把两份记录拼成同一时间轴。文件与所引用的示例配置放在同一目录。

```yaml
batch_version: 1                    # 声明独立批量任务文件的结构版本；当前填写整数1
jobs:                               # 列出互相独立的分析任务，每项引用一份分析配置
  - plan: analysis.yaml             # 指定该任务的分析配置文件；相对于批量配置文件所在目录
  - plan: input-asc-minimal.yaml    # 指定该任务的分析配置文件；相对于批量配置文件所在目录
process_count: 2                    # 限制分析工作进程数；正整数，1表示一个工作进程依次执行
```

不需要给每个任务重复命名，也不需要把默认fail_fast或计算实现写出来。只有想为结果目录自定义名称时才填写jobs[].name。

|字段|数据类型|必填|省略时的值|可填写的值及用途|
|---|---|---|---|---|
|batch_version|整数|是|无|声明批量文件采用的结构版本，按当前支持版本填写。填`1`，表示本版批量配置格式；与分析配置里的config_version分开。|
|jobs|对象数组|与template二选一|无|组织要分别运行的分析任务，按希望查看报告的顺序填写。按期望的报告顺序列出任务；每项包含下面的name和plan。空数组表示没有任务，仍可生成空报告。|
|jobs[].name|字符串|否|按列表位置生成`job_1`、`job_2`等|给每个子任务取名称，用于结果定位及目录命名。本任务的名字，也是输出子目录名，例如`trial_a`。不能重复，`Trial_A`和`trial_a`也算重复；名称格式及保留名见下文。|
|jobs[].plan|字符串|是|无|指定该任务的完整分析配置；从实际保存的YAML/JSON路径取得。分析计划文件的路径，例如`"a/analysis.yaml"`。相对路径以批量配置所在目录为起点。|
|process_count|整数|否|`1`|控制分析工作进程数量上限。填正整数：`1`用一个工作进程依次执行，`2`最多两个工作进程并行，`4`最多四个。根据可用CPU、内存和磁盘选择；不会自动使用全部CPU。不能填0、负数、浮点数、布尔值、字符串或null。|
|fail_fast|布尔值|否|`false`|控制发现失败后是否继续启动尚未运行的任务。`false`：某个任务失败后仍尝试后续任务；`true`：发现失败后不再启动新任务，已经启动的任务继续执行并收尾。|
|backend|字符串或null|否|`null`|控制是否统一覆盖子任务的计算实现；无需统一时省略或null。`null`沿用每个分析计划的设置；`"reference"`让本批所有任务使用便于核对的参考计算；`"numpy"`让所有任务使用数组计算。两种实现应给出相同含义的结果，详见[运行参数](execution.md)。|

任务名称用英文字母或下划线开头，后面可接英文字母、数字、下划线；不能用Python关键字（如`for`、`class`）或表达式函数名`abs`、`isclose`。例如`trial_a`有效，`trial-a`和`a/b`无效。它还要能在当前系统上创建同名目录，应避开Windows的CON、NUL等设备名称。

analysis.yaml中的输入相对路径仍按**它自己的目录**解释。例如子配置放在a/analysis.yaml，里面写data.csv就会读取a/data.csv；这不会改成相对批量文件查找。

## 一个模板处理整个目录

此方式的template、inputs、source也位于批量文件根级，与jobs方式二选一；source不是写在jobs中。

如果每个文件都是独立试验，输入列和分析方法又相同，不必复制多份配置。下面复用同目录的analysis.yaml，对data/can中匹配的ASC分别运行一次。自己的BLF可改成相应目录和*.blf；混合格式目录也可直接填写目录路径：

```yaml
batch_version: 1                    # 声明独立批量任务文件的结构版本；当前填写整数1
template: analysis.yaml             # 指定批量任务重复使用的分析配置路径；每个输入独立执行该配置
inputs: data/can/quickstart*.asc    # 选择批量处理的文件、目录或通配符；每个文件是独立任务
process_count: 2                    # 限制分析工作进程数；正整数，1表示一个工作进程依次执行
```

|字段|必填情况|用途和省略行为|
|---|---|---|
|template|使用此方式时必填|指定对每个输入文件重复执行的分析模板，填写分析配置的JSON/YAML路径；其中其他来源、DBC等相对路径仍以各自声明文件为准。|
|inputs|使用template时必填|指定要分别建立独立分析任务的输入文件集合。可填文件、目录、通配符或这些项目的列表。目录只找当前层，按来源格式筛选，按自然序展开，例如file2在file10之前；只有明确使用**通配符才递归查找。显式列表保持声明顺序。最多4096个文件。|
|source|模板有多个来源时必填|填写模板内要替换输入路径的来源name。只有一个来源时自动采用；不能选择memory来源。|

任务名依次为job_1、job_2等。每个任务替换模板中指定来源的文件，使用独立状态与输出目录。例如file2.csv和file10.csv分别得到自己的能量结果；不会把file2末尾的信号值或报警延续到file10。其他来源仍按模板声明使用。连续分卷应放在一个分析配置的paths中，不能用此方式替代。

## CLI与Python

```powershell
python -m chronaxis batch run batch-extended.yaml --output batch-output --process-count 2
```

`--process-count`可省略：先用批量文件中的process_count；文件也没填时使用1。批量CLI没有`--backend`选项，需在批量配置中填写backend；单任务run才有`--backend`。输出目录必须是新的路径，程序不覆盖既有结果。

```python
from chronaxis import load_batch_plan, run_batch

def main():
    plan = load_batch_plan("batch-extended.yaml")
    # process_count省略或为None时沿用配置；填正整数只覆盖本次运行。
    report = run_batch(plan, "batch-output", process_count=2)
    try:
        print(report.worker_process_count)  # 本次实际启动的分析工作进程数
        print(report.to_dict())
    finally:
        report.close()  # 重试尚未完成的资源清理；失败时保留报告供再次关闭

if __name__ == "__main__":
    main()
```

使用jobs时，`load_batch_plan`只读批量文件，任务启动时才读取各自计划和输入。使用template时，加载阶段读取模板、展开inputs并编译每个独立计划；需要补全CAN信号定义时会读取DBC，但此时不扫描业务报文。`run_batch`还写出batch_report.json。更低层的`BatchRunner.run()`返回报告对象，单独使用时需调用`write_batch_report()`写报告，不能假定已经发布报告文件。所有签名见[批量API](reference/chronaxis.batch.api.md)、[BatchRunner](reference/chronaxis.batch.runner.md)、[模型](reference/chronaxis.batch.models.md)。

Windows使用spawn启动子进程，会重新导入脚本。`if __name__ == "__main__":`保证只有最初启动的脚本派发任务，避免子进程再次创建整批任务。将代码保存为`.py`文件运行；不要直接把启动代码放在模块顶层。进程模式只验收Windows/Python 3.12。

API参数或CLI的`--process-count`优先于批量文件，再其次是默认值1；覆盖不改写原文件。`BatchPlan(..., process_count=4)`和`BatchRunner(process_count=4)`也使用同一含义。普通分析的`execution`和`AnalysisRunner`没有进程数参数；批量能力不表示把一个连续会话拆给多个进程计算。

实际启动数最多为`min(process_count, 任务数)`；空批次或开始前取消不启动。配置4但只有两个任务时启动两个分析工作进程。调度主进程和每个任务可能创建的CAN读取子进程不包含在这个数中，所以操作系统显示的总进程数可以更多。工作进程完成任务后复用，但不会沿用上一任务的信号或事件状态。

报告中`process_count`保存本次生效的上限，`worker_process_count`保存实际启动数，`jobs[].worker_pid`保存执行该任务的进程PID，未启动项为null。已复用的工作进程可能出现在多个任务中。汇总按声明顺序排列，不按完成时间重排。

## 批量报告的设备来源标签

批量CLI读取环境变量`CHRONAXIS_DEVICE_LABEL`，去除首尾空白后作为批量报告的device_label；未设置或为空白时记录`pending`。标签由运行者根据实际设备约定填写，程序不查询机器来猜测。例如PowerShell先执行`$env:CHRONAXIS_DEVICE_LABEL = "home"`，只影响当前进程及其子进程的环境。

Python调用不自动读取这个环境变量，应按需要传`run_batch(plan, "batch-output", device_label="home")`；省略仍为pending。此参数标记整批报告，不能替代子分析配置里的`metadata.device_label`。普通分析与独立导出的要求见[导出说明](exports.md)。不需要报告设备来源时可使用默认pending，不把这个标签当作业务信号。

## 失败、取消和资源设置

以上例自动命名的job_1为例，结果位置如下：

|路径|保存什么|
|---|---|
|batch-output/job_1/work/|计算期间的暂存文件和诊断信息。|
|batch-output/job_1/output/|该任务正式写出的分析结果。|
|batch-output/batch_report.json|整批报告，按jobs中的顺序列出每个任务是否完成、失败或取消，以及错误和已有文件位置。|

报告的output_dir字段仅在正式结果已写出时填写。若文件已写出，但随后关闭资源失败，任务仍标为failed，同时保留结果路径，方便检查已写出的内容。

例如有A、B、C三个任务，同时最多运行两个。A和B已经开始，A失败时：

- fail_fast为false：B继续运行，C仍会被启动。
- fail_fast为true：B继续运行，C不再启动。

通过API的cancel_event或Ctrl+C取消时，也会停止启动后续任务，并在报告中保留已经完成的结果。

取消会等待已派发任务完成写出和关闭，不会立即强杀它们。普通任务失败按fail_fast处理；工作进程异常退出属于调度故障，会停止新派发、保留已完成输出，并清理它留下的CAN读取子进程。Python调用中的基础设施异常携带`batch_report`，可检查报告并调用其`close()`。

关闭持续失败时，工作进程暂停接收新任务，报告的`cleanup_pending`为true。资源仍由该进程持有；修复占用或环境问题后调用`report.close()`会远程重试。若所有工作进程都在等待清理，尚未启动的任务标为cancelled，不会假报完成。JSON报告保存发布时的清理状态，内存报告的`to_dict()`可读取重试后的状态。

命令退出码为0表示全部成功，1表示任务失败或文件操作失败（包括输出目录已存在），2表示批量配置或参数错误，130表示取消。如果既有失败又有取消，退出码为1。

每个任务的内存和磁盘额度仍由自己的analysis.yaml决定。两个任务各允许256MiB同时运行，不能认为整个程序只会使用256MiB；解析库和Python本身也有额外占用。先用1个任务确认结果，再根据机器内存调整process_count。并行的效果应使用实际任务测量；CPU、内存和磁盘都可能成为限制。


批量配置本身不支持imports；每个子分析配置可以导入自己的公共定义，来源路径按对应定义文件解释。config origins BATCH列出批量声明中的子配置或模板路径；它不代替逐个任务的来源报告。见[公共定义](imports.md)。
