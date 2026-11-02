"""在仓库以外的新目录安装候选wheel，直接使用安装目录的用户资料执行实际任务。

输入为wheel、手册渠道的指南ZIP、本地已安装的离线依赖目录与报告目标。保留独立
环境、各场景日志和结果供复查；不安装到用户Python，不修改输入、历史快照或服务。
"""
import argparse
import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def check(wheel, guide, deps, report, device):
    """参数: wheel和guide为发行物、deps已装依赖、report新报告、device设备。返回: 摘要。异常: 原环境/行为错误。"""
    # 使用系统临时目录创建一次性独立运行区；必须实际位于项目根目录外。
    area = Path(tempfile.mkdtemp(prefix="chronaxis-user-"))
    if area.resolve().is_relative_to(ROOT):
        raise ValueError("隔离安装目录应在仓库之外")
    runtime = area / "runtime"
    env = {k:v for k,v in os.environ.items() if k.upper() not in {"PYTHONHOME","PYTHONPATH","VIRTUAL_ENV"}}
    env.update(PIP_NO_INDEX="1",PIP_NO_CACHE_DIR="1",PIP_DISABLE_PIP_VERSION_CHECK="1",
               PYTHONUTF8="1",PYTHONIOENCODING="utf-8",PYTHONDONTWRITEBYTECODE="1",CHRONAXIS_DEVICE_LABEL=device)
    summary = dict(device_label=device, wheel=wheel.name, wheel_sha256=sha256(wheel.read_bytes()).hexdigest(),
                   directory=str(area), logs=[], cases={}, completed=False)
    report.parent.mkdir(parents=True, exist_ok=True)
    if report.exists():
        raise FileExistsError(report)

    def save():
        """参数: 无。返回: 无；记下成功与未完成项。异常: 报告写入错误。"""
        report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")

    def command(name, argv, cwd=area, expected=0):
        """参数: name日志名、argv参数、cwd目录、expected退出码。返回: stdout。异常: 非预期退出。"""
        proc = subprocess.run(list(map(str,argv)),cwd=cwd,env=env,capture_output=True,encoding="utf8",errors="replace")
        (area/(name+".stdout")).write_text(proc.stdout, encoding="utf8")
        (area/(name+".stderr")).write_text(proc.stderr, encoding="utf8")
        summary["logs"].append(dict(name=name,exit=proc.returncode))
        save()
        if proc.returncode!=expected:
            raise RuntimeError(f"{name} 退出{proc.returncode}，日志在{area}：{proc.stderr[-600:]}")
        return proc.stdout

    save()
    # 不向隔离环境添加项目PYTHONPATH，只复制已准备好的第三方依赖，排除旧包和pth。
    command("venv",[sys.executable,"-m","venv","--without-pip",runtime])
    python = runtime / ("Scripts/python.exe" if os.name=="nt" else "bin/python")
    site = Path(command("purelib",[python,"-I","-c","import sysconfig;print(sysconfig.get_path('purelib'))"]).strip())
    shutil.copytree(deps,site,dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("*.pth","*editable*","chronaxis*","__pycache__","pip","pip-*","setuptools*","wheel*","_distutils_hack","pkg_resources"))
    command("install",[sys.executable,"-m","pip","--python",python,"install","--no-index","--no-deps",wheel])
    command("dependencies",[sys.executable,"-m","pip","--python",python,"check"])
    command("can-versions",[python,"-I","-c",
        "from importlib.metadata import version; expected={'python-can':'4.6.1','cantools':'39.4.3','natsort':'8.4.0'}; "
        "actual={name:version(name) for name in expected}; assert actual==expected,(actual,expected); print(actual)"])
    check_name = "import chronaxis,pathlib,sys;assert pathlib.Path(chronaxis.__file__).is_relative_to(sys.prefix);print(chronaxis.__file__)"
    summary["import_path"]=command("import",[python,"-I","-c",check_name]).strip()
    out = area/"from-installed.zip"
    def cli(name,*args,cwd=area):
        """参数: name为日志名、args公开命令参数、cwd运行目录。返回: stdout。异常: 非零退出。"""
        return command(name,[python,"-I","-B","-m","chronaxis",*args],cwd)
    cli("guide","guide","--output",out)
    assert out.read_bytes()==guide.read_bytes(), "手册与安装包提供不同指南"
    direct = Path(cli("guide-path", "guide").strip()).parent
    english_entry = Path(cli("guide-path-en", "guide", "--language", "en").strip())
    assert direct.is_relative_to(site) and english_entry == direct / "en/README.md"
    assert (direct / "README.md").is_file() and english_entry.is_file()
    original_files = {p.relative_to(direct).as_posix(): sha256(p.read_bytes()).hexdigest()
                      for p in direct.rglob("*") if p.is_file()}
    user = area/"user"
    user.mkdir()
    # 极少数内置异常没有可反射签名；必须和参考页同样明确为空，而非伪造(*args)。
    check_api = """import inspect,json,chronaxis
rows=json.load(open('api/index.json',encoding='utf8'))['objects']
assert sorted(x['name'] for x in rows)==sorted(chronaxis.__all__)
for row in rows:
    obj=getattr(chronaxis,row['name'])
    try: actual=str(inspect.signature(obj))
    except (TypeError,ValueError): actual=None
    assert actual==row['signature'],(row['name'],actual,row['signature'])
print(len(rows))
"""
    summary["signature_count"]=int(command("public-signatures",[python,"-I","-c",check_api],direct))
    # 直接读取安装资源；配置用绝对路径，输出写外部工作目录，不复制或解压指南。
    plan_index = json.loads((direct/"tasks.json").read_bytes())
    for kind,term,args in (("task","充电",[]),("api","AnalysisRunner",[]),("field","valid_for",["--schema","analysis"]),
                          ("field","source_type",["--schema","analysis","--branch","can_asc"])):
        found = json.loads(command("lookup-"+term,[python,"-I","lookup.py",kind,term,*args],direct))
        assert found,term
    for term in ("持续", "能量"):
        found=json.loads(command("lookup-"+term,[python,"-I","lookup.py","task",term],direct))
        assert any(item["id"]=="CONDITION_ENERGY" for item in found),found
    for kind, term in (("task", "energy"), ("api", "AnalysisRunner"), ("field", "valid_for")):
        found = json.loads(command("english-lookup-" + kind,
            [python, "-I", "../lookup.py", "--language", "en", kind, term], direct / "en"))
        assert found, (kind, term)
    # 按英文README的相对路径，从en目录真正执行同一跨卷例子并核对能量。
    en_task = next(t for t in json.loads((direct / "en/tasks.json").read_bytes())["tasks"] if t["id"] == "CONDITION_ENERGY")
    command("english-run", [python, "-I", "../run_analysis.py", en_task["example"], user / "out-english"], direct / "en")
    with (user / "out-english/事件结果.csv").open(encoding="utf-8-sig", newline="") as stream:
        en_events = list(csv.DictReader(stream))
    assert len(en_events) == 1 and (en_events[0]["开始时间（s）"], en_events[0]["结束时间（s）"]) == ("61", "122")
    summary["english_energy_kwh"] = float(en_events[0]["energy_kwh（kWh）"])
    assert abs(summary["english_energy_kwh"] - 4000*61/3600000) < 1e-12
    for task in plan_index["tasks"]:
        slug,plan=task["id"],str((direct / task["example"]).resolve())
        if slug=="BATCH":
            cli("run-"+slug,"batch","run",plan,"--output","out-"+slug,cwd=user)
            batch=json.loads((user/("out-"+slug)/"batch_report.json").read_bytes())
            assert batch["jobs"] and all(job["status"]=="completed" for job in batch["jobs"]),batch["counts"]
        else:
            valid=json.loads(cli("validate-"+slug,"validate",plan,"--format","json",cwd=user))
            assert valid["valid"] and valid["execution_ready"],(slug,valid)
            published=json.loads(cli("run-"+slug,"run",plan,"--output","out-"+slug,cwd=user))
            assert published["status"]=="completed",published
            if slug=="CHARGE":
                with (user/"out-CHARGE/事件结果.csv").open(encoding="utf-8-sig",newline="") as stream:
                    row=next(csv.DictReader(stream))
                    values={key.rsplit("（",1)[1][:-1]:float(value) for key,value in row.items()
                            if key.endswith(("（Wh）","（Ah）"))}
                assert abs(values["Wh"] - 8000/3600)<1e-12 and abs(values["Ah"]-20/3600)<1e-12,values
                summary["charge"]=values
            if slug=="CONDITION_ENERGY":
                # 发布环境实际运行跨卷严格门槛例子，不能仅用completed判定业务正确。
                with (user/"out-CONDITION_ENERGY/事件结果.csv").open(encoding="utf-8-sig",newline="") as stream:
                    events=list(csv.DictReader(stream))
                assert len(events)==1,events
                row=events[0]
                assert (row["开始时间（s）"],row["结束时间（s）"])==("61","122"),row
                assert row["energy_kwh：状态"]=="完整",row
                assert abs(float(row["energy_kwh（kWh）"])-4000*61/3600000)<1e-12,row
                summary["conditional_energy_kwh"]=float(row["energy_kwh（kWh）"])
        summary["cases"][slug]="published"
        save()
    # 测试驱动器从维护区复制，输入始终是已安装包和发布资料，不提供源码检出。
    verify = area/"verify"
    verify.mkdir()
    driver=verify/"check_behavior.py"
    shutil.copyfile(ROOT/"tests/ai_release/check_behavior.py",driver)
    summary["behavior"]=json.loads(command("behavior",[python,"-I","-B",driver,direct],verify))
    assert original_files == {p.relative_to(direct).as_posix(): sha256(p.read_bytes()).hexdigest()
                              for p in direct.rglob("*") if p.is_file()}, "阅读/运行示例改写了安装资料"
    summary["direct_guide"] = str(direct)
    summary["guide_files_unchanged"] = True
    summary["completed"]=True
    save()
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("wheel","guide","deps","report"):
        parser.add_argument(name,type=Path)
    parser.add_argument("--device-label",required=True,choices=("home","work"))
    args=parser.parse_args()
    result=check(args.wheel.resolve(),args.guide.resolve(),args.deps.resolve(),args.report.resolve(),args.device_label)
    print(json.dumps(dict(directory=result["directory"],cases=len(result["cases"]),completed=result["completed"])))
