"""在没有项目源码的用户目录，通过安装包公开入口检查教学契约和真实诊断。

输入为已解压指南，当前位置用于新建小型合成计划和结果；不修改原指南或真实日志。
预期独立来自手算和明确拒绝规则。这里的结果不计入独立AI回答的成功率。
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import subprocess
import sys

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError, load_analysis_plan


def cli(*args, code=0):
    """参数: args为CLI参数，code为预期退出码。返回: stdout文本。异常: 命令不符抛AssertionError。"""
    # 使用已安装解释器，避免子命令意外从当前源码目录导入。
    proc = subprocess.run([sys.executable,"-B","-m","chronaxis",*map(str,args)],
                          capture_output=True, encoding="utf8")
    if proc.returncode != code:
        raise AssertionError((args, proc.returncode, proc.stdout, proc.stderr))
    return proc.stdout


def memory(values):
    """参数: values为每秒一个原始功率值，可为None。返回: 有明确观测范围与单位的内存配置。异常: 无。"""
    # 最后一个更新确定真实终点，避免把EOF之外的保持算进积分。
    return dict(config_version=3, dataset=dict(name="demo",domain=dict(start="0s",end=f"{len(values)-1}s")),
                sources=[dict(source_type="memory",time=dict(unit="s"),rows=[
                    dict(time=f"{i}s",values={"raw":v}) for i,v in enumerate(values)])],
                signals=[dict(name="power",field="raw",dtype="float64",unit="W",valid_for="3s")],
                calculations=[dict(name="energy",operation="integral",expr="power")])


def snapshot(config, backend="reference"):
    """参数: config为公开字典；backend为数值后端。返回: 关闭前取得的计算、事件和片段行。异常: 原分析错误。"""
    # 封闭结果和每个游标；这组几行小输入的对象可以在内存中核对。
    plan = AnalysisPlan.from_dict(config)
    active = AnalysisRunner(backend)
    with active.run(plan) as result:
        with closing(result.iter_calculations()) as cursor:
            calculations = list(cursor)
        with closing(result.iter_events()) as cursor:
            events = list(cursor)
        with closing(result.iter_segments()) as cursor:
            segments = list(cursor)
    return calculations, events, segments


def check(guide):
    """参数: guide为解压后的发布资料。返回: 实测案例摘要。异常: 任一行为或手算值不符即失败。"""
    csv = guide/"examples/input-csv-minimal.yaml"
    # 检查结构及真实依赖；静态警告必须保留，不充当实际输入核验。
    report = json.loads(cli("validate",csv,"--format","json"))
    explanation = json.loads(cli("explain",csv,"--format","json"))
    assert report["valid"] and report["execution_ready"] and not report["errors"] and report["warnings"]
    assert explanation["validation"] == report
    assert any(n["node_id"]=="energy" and n["dependencies"]==["power"] and n["unit"]=="J"
               for n in explanation["nodes"])
    answer = {}
    # 指南自带脚本只用公开接口，数值手算38 J；输出必须真实发布。
    proc = subprocess.run([sys.executable,"-B",str(guide/"run_analysis.py"),str(csv),"csv-out"],
                          check=True, capture_output=True, encoding="utf8")
    assert "38.0 J complete" in proc.stdout and Path("csv-out/run_manifest.json").is_file()
    answer["API/CSV"] = "38 J / complete"
    for backend in ("reference","numpy"):
        # 充分观测且全假：积分为0，样本选择统计均为空。
        conf = memory([2,2,2])
        conf["calculations"] = [dict(name="v"+str(i),operation=op,expr="power",condition="power < 0")
            for i,op in enumerate(("integral","sample_minimum","sample_maximum","sample_mean"))]
        rows,_,_ = snapshot(conf,backend)
        assert {r.calculation_id:r.value for r in rows} == {"v0":0.0,"v1":None,"v2":None,"v3":None}
        # 全未知不报正常0；同一输入改成已知全假的证据不能继续复用。
        unknown = memory([None,None,None])
        unknown["calculations"][0]["condition"] = "power > 0"
        rows,_,_ = snapshot(unknown,backend)
        assert rows[0].value is None and rows[0].status != "complete"
        # 两次真实活动在退出等待内合并，保留两个原事件的身份与边界。
        conf = memory([0,1,0,1,0,0,0])
        conf["rules"] = [dict(name="hot",rule_type="condition_duration",minimum_duration="0s",condition="power > 0")]
        conf["windows"] = [dict(name="context",rule="hot",anchor="activity",pre="0s",post="0s",
                                merge="exit_delay",exit_delay="2s")]
        _,events,segments = snapshot(conf,backend)
        assert len(events)==2 and len(segments)==1
        assert [(r.start_ns,r.end_ns) for r in events]==[(10**9,2*10**9),(3*10**9,4*10**9)]
        assert tuple(segments[0].parent_event_ids)==tuple(r.event_id for r in events)
        # 电压采样时旧值只在前三倍周期有效；0–0.3秒积分1.2 J，其余未知。
        conf = memory([4,0]); conf["signals"][0].pop("valid_for")
        conf["signals"][0]["period"] = "100ms"
        rows,_,_ = snapshot(conf,backend)
        assert abs(rows[0].value-1.2)<1e-12 and rows[0].status=="partial"
        # 输入是已经解码的毫安；显式额外转换一次，不把DBC转换重复应用。
        conf = memory([2000,2000])
        conf["signals"][0].update(name="pack_current",unit="A",semantic_id="battery.current",
                                  conversion=dict(input_unit="mA",scale=0.001))
        conf["calculations"] = [dict(name="maximum",expr="pack_current",operation="sample_maximum")]
        rows,_,_ = snapshot(conf,backend)
        assert rows[0].value == 2 and rows[0].unit == "A"
        # 仅明确的2编码表示开启；非零的3不能继续沿用上一次有效TRUE。
        conf = memory([0,2,3,0])
        conf["signals"][0].update(dtype="bool",unit="1",choices=[[0,False],[2,True]])
        conf["calculations"] = []
        conf["rules"] = [dict(name="active",rule_type="condition_duration",condition="power",
                              minimum_duration="0s")]
        _,events,_ = snapshot(conf,backend)
        assert len(events)==1 and events[0].start_ns==10**9 and events[0].end_ns==2*10**9
        assert events[0].status=="interrupted", events[0]
        answer[backend] = "zero, empty, unknown, two parents, TTL 1.2 J, conversion 2 A, code 2 active / 3 unknown"
    # 文件级真实诊断保留单一error；修复只替换版本类型，不改变条件和期望值。
    conf = memory([2,2,2]); conf["config_version"] = "3"
    bad = Path("repair.json"); bad.write_text(json.dumps(conf),encoding="utf8")
    err = json.loads(cli("validate",bad,"--format","json",code=2))["error"]
    assert "config_version" in err["path"] and err["code"] and err["message"]
    conf["config_version"] = 3
    bad.write_text(json.dumps(conf),encoding="utf8")
    assert json.loads(cli("validate",bad,"--format","json"))["execution_ready"]
    assert snapshot(conf)[0][0].value == 4
    answer["REPAIR"] = {"code":err["code"],"path":err["path"],"new_value_J":4}
    # 结构合法但没有可执行计算节点时走errors数组，解释报告嵌套在validation。
    conf["calculations"] = []
    bad.write_text(json.dumps(conf),encoding="utf8")
    unsupported = json.loads(cli("validate",bad,"--format","json",code=2))
    assert unsupported["errors"] and not unsupported["execution_ready"]
    assert json.loads(cli("explain",bad,"--format","json",code=2))["validation"]==unsupported
    # 语义名称不作为属性路径；被拒的表达式不能静默改写。
    conf = memory([2,2]); conf["signals"][0]["semantic_id"] = "battery.current"
    conf["calculations"][0]["condition"] = "power > 0"
    assert snapshot(conf)[0][0].value == 2
    conf["calculations"][0]["condition"] = "battery.current > 0"
    try:
        AnalysisPlan.from_dict(conf)
    except PlanValidationError as error:
        assert "battery" in str(error) or "属性" in str(error), str(error)
    else:
        raise AssertionError("点号表达式未拒绝")
    # 单层imports只由文件加载展开，且字段来源能回溯到实际定义文件。
    plan = guide/"examples/analysis-imports.yaml"
    assert load_analysis_plan(plan)
    assert "definitions.yaml" in cli("config","origins",plan,"--fields","--format","json")
    assert "imports" not in json.loads(cli("config","resolve",plan,"--defaults","--format","json"))
    return answer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guide",type=Path)
    print(json.dumps(check(parser.parse_args().guide.resolve()),ensure_ascii=False))
