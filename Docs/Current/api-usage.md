# Python API用法

公开入口位于`chronaxis`包。文件配置使用load_analysis_plan；程序生成配置使用AnalysisPlan.from_dict；AnalysisRunner执行，AnalysisResult读取和发布。先完成[安装](installation.md)，再按下面的完整流程运行。

单一ASC/BLF来源的基础配置设置`execution.process_count: 4`，下面的`run(plan)`直接沿用它。要在一次调用中覆盖配置，使用`AnalysisRunner().run(plan, process_count=4)`；同一实例的`validate`和`explain`也接受这个仅关键字参数。`None`沿用配置且不修改原计划，正整数设置本次上限。CSV、内存和多来源联合分析保持1，独立批量任务在外层设置并行。完整范围见[连续记录多进程](continuous-files.md)。


## 如何读参数表

参考表把真实Python名称、类型、是否必填、缺省值和用途分别列出。None表示不提供某个可选对象，不等于0、空字符串或空列表。类型中的竖线表示可选类型；tuple表示固定顺序的不可变序列。类的字段描述保存的状态；构造参数仍以实际签名为准。自动生成的标准方法和第三方库接口单独标注其来源。

## 加载、检查和执行

把下面的完整代码保存成`.py`文件，从源码仓库根目录运行；保留`if __name__ == "__main__":`入口保护，避免Windows启动工作进程时重复运行主程序。离线示例目录可直接运行[api_example.py](examples/api_example.py)，后者默认读取同目录analysis.yaml，也接受自定义配置路径。

```python
from chronaxis import AnalysisRunner, load_analysis_plan, validate_analysis_plan

def main():
    plan = load_analysis_plan("Docs/Current/examples/analysis.yaml")
    report = validate_analysis_plan(plan)
    if not report.valid or not report.execution_ready:
        raise RuntimeError(report)

    with AnalysisRunner().run(plan) as result:
        rows = result.iter_calculations()
        try:
            for row in rows:
                print(row.calculation_id, row.value, row.unit, row.status)
        finally:
            rows.close()
        result.write("new-result-directory")


if __name__ == "__main__":
    main()
```

配置中的进程上限为4，但本例只有一个ASC文件且采用默认接续方式，在当前进程读取；`explain`中的`read_process_limit`为0。若要运行两卷的同一组数据，把加载路径换成`Docs/Current/examples/input-can-directory.yaml`；此时`read_process_limit`为2，计算结果相同；这是计划上限，不是已观测到的PID数量。该合成示例的终端输出如下，每行依次为计算名称、数值、单位和状态。
```text
energy 38.0 J complete
sample_average 6.0 W complete
time_average 6.333333333333333 W complete
```

功率 2、4、8、10 W 分别持续 1、2、1、2 秒，积分为 2×1＋4×2＋8×1＋10×2＝38 J。四次读数的平均为 6 W，按时间加权的平均为 38÷6 W。write 将这些结果保存到示例中的结果目录。

load_analysis_plan读取主配置及明确的一层公共定义，相对路径按各自声明文件的父目录解释。AnalysisPlan.from_dict(config, base_dir=...)接收Python字典，不读取主配置文件；base_dir省略时采用当前工作目录。两个入口构建计划时，都可能枚举输入目录，并在需要推导CAN类型、单位或枚举表时读取DBC；此时不扫描业务报文或CSV记录。from_dict拒绝未展开的imports，应先用文件加载入口或chronaxis config resolve。两者都会检查未知字段、名称冲突、表达式和业务引用。

validate_analysis_plan返回静态ValidationReport；valid表示声明检查是否通过，execution_ready表示当前执行路径是否支持。explain_analysis_plan返回依赖和后端等ExplainReport。对已加载计划的静态检查不会读取业务数据；加载计划时，缺省CAN元数据可能需要读取DBC，仍不能证明真实数据有效。valid和execution_ready都不是全文件数据验收；坏行、实际时间回退、运行时权限或资源不足可能在run时才被发现。

AnalysisRunner(backend=None, *, extensions=None)沿用计划设置；配置省略backend时使用auto，按整个计划选择reference或numpy。reference使用独立参考数值实现；numpy按计算路径采用逐点或数组计算。显式传入auto、reference或numpy会覆盖本次执行设置；选择范围见[执行设置](execution.md)。`run(plan, work_dir=None, *, process_count=None)`执行分析并返回AnalysisResult；work_dir省略时分配独立暂存，显式指定时必须是新目录。结果不自动发布，调用write把数据写到结果目录；目录可重复使用，每次文件有独立时间后缀。

extensions 默认省略。只有 Python 宿主程序自行注册函数或滚动算子时，才在加载计划和创建 AnalysisRunner 时传入同一扩展注册对象，完整例子见[宿主扩展](host-extensions.md)。签名中的 * 表示其后的参数必须按名字填写。

## 逐行读取和关闭

iter_events、iter_segments、iter_sequences、iter_calculations、iter_selections和iter_input_trace分别返回事件、片段、配对、计算、筛选样本和输入追溯游标；iter_aggregations 返回对多行计算结果的组统计游标；iter_contributions读取明确请求的逐消息贡献。默认不生成未请求的明细。数据按固定字段逐行返回，字段见[结果](results.md)。

游标读完或提前退出都应close。结果用with管理，或在finally中调用close；关闭后读取会抛ResultClosedError。资源错误和取消不能当作空结果，发布或关闭失败也不能报告完成。

## 主要入口

| 入口 | 返回与副作用 |
|---|---|
| load_analysis_plan(path, *, extensions=None) | 读取主配置/imports并构建AnalysisPlan；按需枚举目录、读取DBC元数据 |
| AnalysisPlan.from_dict(config, *, base_dir=None, extensions=None) | 从字典构建计划；按需枚举目录、读取DBC，不扫描业务记录 |
| validate_analysis_plan(plan) | 返回静态校验报告，不运行 |
| explain_analysis_plan(plan) | 返回实际依赖、间隔和资源声明，不运行 |
| AnalysisRunner(...).run(plan, work_dir=None, *, process_count=None) | 沿用或覆盖文件读取进程上限；读输入、计算并占用暂存，返回需关闭的结果 |
| AnalysisResult.write(output_dir) | 向可重复使用的目录发布带时间后缀的表和运行清单，返回OutputManifest |
| load_batch_plan(path)、run_batch(...) | 加载批量清单并运行独立任务；子计划到任务启动时才加载 |
| build_preset(...)、resolve_preset_roles(...) | 检查预设角色并生成公共声明；通常直接写presets即可 |

主要公开入口见[Python API索引](api.md)，精确签名与说明链接到对应定义。内部模块及私有实现另见[开发参考](reference/index.md)。

## 在程序中构建配置

下面是完整调用示例，复用随手册提供的JSON对照文件构造Python字典。base_dir决定字典中相对输入路径的起点；该入口不读取imports，公共定义请使用文件加载入口。

```python
import json
from pathlib import Path
from chronaxis import AnalysisPlan, explain_analysis_plan

directory = Path("Docs/Current/examples")
config = json.loads((directory / "analysis.json").read_text(encoding="utf-8"))
plan = AnalysisPlan.from_dict(config, base_dir=directory)
print(explain_analysis_plan(plan))
```

## 异常与资源所有权

| 阶段 | 常见异常/结果 | 调用方处理 |
|---|---|---|
| 加载配置 | PlanValidationError | 查看path、source及可用的行列；修正后重新加载。此时未读业务日志。 |
| 执行 | AnalysisError；新包装的运行错误以__cause__保留原异常 | 检查输入路径、时间、解码或预算原因；不要把失败作为空结果。 |
| 创建或读取结果游标 | ResultClosedError、BudgetExceededError、ResultFormatError、OSError | 关闭游标，保留异常；检查生命周期、预算或暂存文件。具体类别见方法参考。 |
| 查询未请求的明细 | ContributionsUnavailableError；输入追溯未开启时AnalysisError | 按需开启outputs.contributions或diagnostics.trace后重新运行。 |
| 发布 | AnalysisError或ResultClosedError | 检查路径、写入权限、平台及原异常链；结果仍可用时可向同一或其他目录重试write。 |
| 批量任务 | 报告内failed/cancelled | 检查每个任务的状态；run_batch正常返回不保证所有任务成功。 |

`AnalysisError`、`ResultClosedError`可从chronaxis导入；其他结果异常定义在[chronaxis.results.errors](reference/chronaxis.results.errors.md)。结果对象和游标分别占用资源，with管理结果、finally关闭游标。关闭结果后，其run_manifest仍可用于查看小型诊断快照，但不能再读取数据或发布。

发生清理错误时，保留原异常和实际结果对象。普通运行失败可从所捕异常读取 `getattr(exc, "runner_cleanup_owner", None)`；结果发布或关闭失败可读取 `analysis_result_cleanup_owner`。排除文件占用等原因后，对存在的恢复对象调用 `close()`，也可直接重试仍持有的结果对象。恢复只释放本次资源，不重新计算或撤销已发布结果；属性可能仍指向已经关闭的对象，不能只凭属性存在判断资源是否仍被占用。

## 时间与预设入口

```python
from chronaxis import parse_duration, checked_add_ns, convert_time

duration_ns = parse_duration("500ms").time_ns  # 取转换结果中的整数纳秒
end_ns = checked_add_ns(1_000_000_000, duration_ns)
converted = convert_time(1.5, "s")
print(duration_ns, end_ns, converted)
```

预设通常通过配置`presets`使用，完整角色和参数示例见[业务预设](presets.md)。若在Python中组合预设，先构建PresetSpec和SignalDefinition，再调用resolve_preset_roles检查角色，build_preset取得PlanFragment；它只是配置片段，仍须合入完整AnalysisPlan才可运行。批量加载、运行和关闭报告的完整代码见[批量任务](batch.md)。

<a id="preset-api-chain"></a>
## 从类型化信号构造预设并执行

通常在YAML的presets中声明即可，由加载器展开。需要在Python里检查角色或组合节点时，可按以下完整过程调用：SignalDefinition → PresetSpec → resolve_preset_roles → build_preset → PlanFragment.to_dict → AnalysisPlan.from_dict → AnalysisRunner.run。

SignalDefinition从chronaxis.core.binding导入；它没有根包同名导出。resolve_preset_roles返回绑定检查结果，不返回样本；build_preset也自行检查角色。生成片段只含规则、窗口、派生和计算节点，仍须补齐dataset、sources和signals。不要同时合并片段又把同一预设放进presets，避免展开两次。

完整文件为[preset_api_example.py](examples/preset_api_example.py)。从examples目录执行`python preset_api_example.py --output preset-api-result`；该脚本为示例工作目录和发布目录创建共同的父目录，所以 --output 须填写新路径。得到 heat_duration=9.0s、complete。这里是Python API代码，字典是函数参数，不要求把用户YAML改写成JSON。

这个接口示例直接提供内存记录，因此显式使用`process_count: 1`。处理自己的ASC/BLF分卷时，使用上方文件加载例及其`execution.process_count: 4`配置。

```python
"""从类型化信号到预设片段，再执行完整分析。参数: --output结果目录。返回: 报警时长。"""
from pathlib import Path
import argparse
from chronaxis import (PresetSpec, resolve_preset_roles,
                       build_preset, AnalysisPlan, AnalysisRunner)
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType


def run(output):
    """参数: 结果输出目录。返回: 生成的计算行。异常: 角色/计划/执行错误；关闭结果。"""
    # 类型化对象中的有效期使用整数纳秒；它不包含任何输入样本。
    temperature=SignalDefinition(name='temperature',source='table',field='temperature',
        dtype=SignalDType.FLOAT64,unit='degC',valid_for_ns=10_000_000_000)
    signals=(temperature,)
    spec=PresetSpec.from_dict(dict(name='heat',preset_type='threshold_excursion',version='1',
        role_bindings={'signal':'temperature'},parameters={'unit':'degC','enter_threshold':80,'exit_threshold':75}))
    roles=resolve_preset_roles(spec,signals)
    assert roles[0].definition is temperature and roles[0].resolution=='explicit'
    fragment=build_preset(spec,signals)  # 返回PlanFragment；此函数也会自行检查角色。
    nodes=fragment.to_dict()            # 仅节点声明，不包含sources、signals或运行结果。
    raw=dict(config_version=4,dataset=dict(name='preset_api'),
        execution=dict(process_count=1),
        sources=[dict(name='table',source_type='memory',
            rows=[dict(time=f'{t}s',values={'temperature':v}) for t,v in ((0,85),(3,77),(9,75),(10,75))])],
        signals=[dict(name=s.name,source=s.source,field=s.field,dtype=s.dtype.value,unit=s.unit,valid_for=f'{s.valid_for_ns}ns') for s in signals])
    # 本例基础计划还没有同类节点，故可update。已有节点时须逐列表合并并检查ID冲突。
    # 不再同时把spec加入raw['presets']，否则同一预设会展开两遍。
    raw.update(nodes)
    plan=AnalysisPlan.from_dict(raw)
    with AnalysisRunner().run(plan,work_dir=output/'work') as result:
        rows=list(result.iter_calculations())
        assert len(rows)==1 and rows[0].value==9.0 and rows[0].unit=='s'
        result.write(output/'published')
        return rows


def main():
    """参数: CLI结果目录。返回: None。异常: 原校验/执行/I/O错误。"""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output;output.mkdir(parents=True,exist_ok=False)
    for row in run(output):print(row.calculation_id,row.value,row.unit,row.status)


if __name__=='__main__':main()
```

已有计划中合并时，derived按名称合并、各节点列表逐项追加，再交AnalysisPlan校验重名与引用；不要用update覆盖已有业务列表。本例基础计划没有这些节点，因此显式使用update。各函数的完整签名及参数见[公开API](api.md)。

## 结果聚合的Python调用示例

在仓库根目录运行以下代码。每次加载先在事件范围内计算均值，再用 `AnalysisResult.iter_aggregations()` 逐组读取 P95。发布 CSV 是可选步骤。[功率试验与输入下载](calculations.md#v4-power-statistics)

将代码保存成 .py 文件，从仓库根目录运行。main 入口保护可避免 Windows 启动读取进程时重复执行脚本。首个示例打印 load_mean_p95 19.5 W complete 2 2，表示两次活动的均值为 10 W 和 20 W，采用线性分位数算法得到 P95 为 19.5 W。

```python
from chronaxis import AnalysisRunner, load_analysis_plan

def main():
    plan = load_analysis_plan("Docs/Current/examples/power-statistics.yaml")
    with AnalysisRunner().run(plan) as result:
        for row in result.iter_aggregations():
            print(row.aggregation_id, row.value, row.unit, row.status,
                  row.included_count, row.candidate_count)


if __name__ == "__main__":
    main()
```

<a id="api-table-reading"></a>
