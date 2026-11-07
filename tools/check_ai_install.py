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
    # 在真正的安装环境核对构建版本，摘要/详细元数据都不得借用仓库或旧安装身份。
    version_check = """from importlib.metadata import version
from dataclasses import replace
from chronaxis._version import software_version
from chronaxis.results.manifest import RunMetadata
expected = version('chronaxis')
assert software_version() == expected
metadata = RunMetadata('install-version', None, 'plan', 'reference', 4,
                       'relative', (), '2026-11-07T00:00:00+08:00')
for item in (metadata, replace(metadata, detailed_diagnostics=True)):
    assert item.to_dict()['software_version'] == expected
assert replace(metadata, software_version='0.0.1').to_dict()['software_version'] == '0.0.1'
print(expected)
"""
    summary['software_version'] = command('software-version', [python, '-I', '-B', '-c', version_check]).strip()
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
    assert json.loads((direct / 'manifest.json').read_bytes())['package_version'] == summary['software_version']
    original_files = {p.relative_to(direct).as_posix(): sha256(p.read_bytes()).hexdigest()
                      for p in direct.rglob("*") if p.is_file()}
    user = area/"user"
    user.mkdir()
    # 极少数内置异常没有可反射签名；必须和参考页同样明确为空，而非伪造(*args)。
    check_api = """import inspect,json,chronaxis
rows=json.load(open('api/index.json',encoding='utf8'))['objects']
assert sorted(x['name'] for x in rows if x.get('import_module','chronaxis')=='chronaxis')==sorted(chronaxis.__all__)
import importlib
for item in rows:
    assert hasattr(importlib.import_module(item.get('import_module','chronaxis')),item.get('import_name',item['name']))
for row in rows:
    obj=getattr(importlib.import_module(row.get('import_module','chronaxis')),row.get('import_name',row['name']))
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
    # 从真正查询结果继续阅读完整参考；不能只检验索引或示例可运行。
    summary['task_reading'] = []
    for language, terms in (('zh', ('结果聚合', '逐消息累计')), ('en', ('result aggregation', 'per-message accumulation'))):
        base = direct / ('en' if language == 'en' else '')
        for term, expected in zip(terms, ('POWER_STATISTICS', 'MESSAGE_ENERGY')):
            rows = json.loads(command('reading-' + language + '-' + expected,
                [python, '-X', 'utf8', '-I', direct / 'lookup.py', 'task', term, '--language', language], base))
            task, = [item for item in rows if item['id'] == expected]
            opened = []
            for reference in task['references']:
                filename, _, pointer = reference['path'].partition('#')
                target = (base / filename).resolve()
                assert target.is_relative_to(direct), target
                text = target.read_text(encoding='utf8')
                if pointer:
                    node = json.loads(text)
                    for part in pointer.split('/')[1:]:
                        key = part.replace('~1', '/').replace('~0', '~')
                        node = node[int(key)] if isinstance(node, list) else node[key]
                    assert node['items']['properties'], reference
                else:
                    required = ('group_by', 'include_partial', 'partial_policy', 'discovery_complete') if expected == 'POWER_STATISTICS' else ('parameters', 'message_policy', 'split_by_sign')
                    assert all(word in text for word in required), reference
                opened.append(reference['path'])
            # 示例也必须由这次查询给出，随后下方任务循环实际运行同一份文件。
            example = (base / task['example']).resolve()
            assert example.is_relative_to(direct) and example.read_text(encoding='utf8').strip(), example
            summary['task_reading'].append(dict(language=language, task=expected, references=opened, example=task['example']))
    save()
    # 按英文README的相对路径，从en目录真正执行同一跨卷例子并核对能量。
    en_task = next(t for t in json.loads((direct / "en/tasks.json").read_bytes())["tasks"] if t["id"] == "CONDITION_ENERGY")
    english_output=command("english-run", [python, "-I", "../run_analysis.py", en_task["example"], user / "out-english"], direct / "en")
    english_manifest=Path(english_output.strip().splitlines()[-1])
    english_info=json.loads(english_manifest.read_bytes())
    assert english_info['run']['software_version'] == summary['software_version']
    english_table=next(english_manifest.parent/item["name"] for item in english_info["outputs"] if item["name"].startswith("事件结果_"))
    with english_table.open(encoding="utf-8-sig", newline="") as stream:
        en_events = list(csv.DictReader(stream))
    assert len(en_events) == 1 and (en_events[0]["开始时间（s）"], en_events[0]["结束时间（s）"]) == ("61", "122")
    summary["english_energy_kwh"] = float(en_events[0]["energy_kwh（kWh）"])
    assert abs(summary["english_energy_kwh"] - 4000*61/3600000) < 1e-12
    for task in plan_index["tasks"]:
        slug,plan=task["id"],str((direct / task["example"]).resolve())
        if slug == "FAST_CONTINUOUS_SESSION":
            # 安装后的真实入口执行两种顺序；每个下载例包含完整来源/信号/公式。
            folder = Path(plan).parent
            for name in ('session.yaml', 'session-time-order.yaml'):
                source = folder/name
                explained = json.loads(cli('explain-'+name, 'fast','explain',source,'--process-count','4',cwd=user))
                assert explained['worker_process_limit'] == 2 and len(explained['inputs']) == 2
                published = json.loads(cli('run-'+name,'fast','run',source,'--output','out-'+name,
                                          '--process-count','2',cwd=user))
                manifest = Path(published['manifest_path'])
                data = json.loads(manifest.read_bytes())
                assert len(data['inputs']) == 2 and len(data['execution']['worker_pids']) == 2
                assert data['execution']['ram_estimated_bytes'] == 0
                with (manifest.parent/data['outputs'][0]['name']).open(encoding='utf-8-sig',newline='') as stream:
                    row, = csv.DictReader(stream)
                assert float(row['结果']) == 1200 and row['状态'] == '完整', row
            script = user/'run_fast_session.py'
            script.write_text(
                'import json\nfrom chronaxis.fast import run\n'
                'if __name__ == "__main__":\n'
                f'    path = run({str(folder/"session.yaml")!r}, "out-fast-python", process_count=4, work_dir="fast-work")\n'
                '    print(json.dumps({"manifest_path": str(path)}))\n', encoding='utf8')
            command('python-fast-session', [python,'-I','-B',script], user)
            published = json.loads((area/'python-fast-session.stdout').read_bytes())
            manifest = Path(published['manifest_path'])
            data = json.loads(manifest.read_bytes())
            assert len(data['execution']['worker_pids']) == 2
            with (manifest.parent/data['outputs'][0]['name']).open(encoding='utf-8-sig',newline='') as stream:
                row, = csv.DictReader(stream)
            assert float(row['结果']) == 1200 and not any((user/'fast-work').iterdir())
            summary['cases'][slug] = 'Two session modes; CLI and Python overrides; two workers; 1200 J; clean work directory'
            save()
            continue
        if slug == "FAST_MESSAGE_ENERGY":
            folder = Path(plan).parent
            explained = json.loads(cli("explain-fast-energy", "fast", "explain", plan, cwd=user))
            assert explained["engine"] == "base_hpc_v1" and len(explained["metrics"]) == 1, explained
            manifests = []
            for source in (Path(plan), folder / "analysis-blf.yaml"):
                valid = json.loads(cli("validate-" + source.stem, "fast", "validate", source, cwd=user))
                assert valid["valid"], valid
                output = user / ("out-" + slug)
                publication = json.loads(cli("run-" + source.stem, "fast", "run", source, "--output", output, cwd=user))
                manifest = Path(publication["manifest_path"])
                manifests.append(manifest)
                item, = json.loads(manifest.read_bytes())["outputs"]
                with (manifest.parent / item["name"]).open(encoding="utf-8-sig", newline="") as stream:
                    row, = csv.DictReader(stream)
                assert (row["计算项"], float(row["结果"]), row["单位"], row["状态"]) == ("energy", 800., "J", "完整"), row
            assert len(set(manifests)) == 2 and all(path.is_file() for path in manifests), manifests
            invalid = folder / "unsupported.yaml"
            command("reject-fast-full", [python, "-I", "-B", "-m", "chronaxis", "fast", "validate", invalid], user, 2)
            errors = json.loads((area / "reject-fast-full.stderr").read_bytes())["errors"]
            assert any(item["path"] == "$.outputs.contributions" for item in errors), errors
            summary["cases"][slug] = "ASC and BLF each 800 J"
            save()
            continue
        if slug == "FAST_TEMPLATE_TOTAL":
            run = json.loads(cli("run-" + slug, "fast", "batch", plan, "--output", "out-" + slug, "--total", cwd=user))
            report_data = json.loads(Path(run["report_path"]).read_bytes())
            total, = report_data["totals"]
            assert run["status"] == "completed" and total["value"] == 1200 and total["unit"] == "J" and total["status"] == "complete", report_data
            summary["cases"][slug] = "800 J + 400 J = 1200 J"
            save()
            continue
        if slug=="HOST_EXTENSION":
            # 此例的配置只引用已登记名称；普通 CLI 不能替用户加载 Python。
            program = Path(plan).with_name("host_extensions.py")
            for backend in ("reference","numpy"):
                # 参考端核对脚本同目录的缺省配置，数组端按任务声明显式选择配置。
                plan_args = ["--plan", plan] if backend == "numpy" else []
                text = command("host-"+backend,[python,"-X","utf8","-I",program,"--backend",backend,
                               *plan_args,"--work-dir",user/("host-"+backend)],user)
                peaks = [line.split() for line in text.splitlines() if line.startswith("peak ")]
                assert len(peaks)==1 and float(peaks[0][1])==80 and peaks[0][2:]==["A","complete"],text
            summary["cases"][slug]="both host backends: 80 A"
            save()
            continue
        if slug=="BATCH":
            batch_summary=json.loads(cli("run-"+slug,"batch","run",plan,"--output","out-"+slug,cwd=user))
            batch=json.loads(Path(batch_summary["report"]).read_bytes())
            assert batch["jobs"] and all(job["status"]=="completed" for job in batch["jobs"]),batch["counts"]
        else:
            valid=json.loads(cli("validate-"+slug,"validate",plan,"--format","json",cwd=user))
            assert valid["valid"] and valid["execution_ready"],(slug,valid)
            published=json.loads(cli("run-"+slug,"run",plan,"--output","out-"+slug,cwd=user))
            assert published["status"]=="completed",published
            manifest_path=Path(published["manifest"])
            manifest=json.loads(manifest_path.read_bytes())
            assert manifest['run']['software_version'] == summary['software_version'], slug
            if slug=="CONTINUOUS_FILES":
                # 从安装资料运行真实文件池；核独立手算值、静态上限及时间归并扩展。
                table=next(manifest_path.parent/item['name'] for item in manifest['outputs'] if item['name'].startswith('会话结果_'))
                with table.open(encoding='utf-8-sig',newline='') as stream:
                    assert float(next(csv.DictReader(stream))['energy（J）'])==38
                explained=json.loads(cli('continuous-explain','explain',plan,'--process-count','4','--format','json',cwd=user))
                assert explained['budget']['process_count']==4 and explained['source_execution'][0]['read_process_limit']==2,explained
                extended=Path(plan).with_name('continuous-time-order.yaml')
                extra=json.loads(cli('continuous-merge','run',extended,'--process-count','4','--output','out-continuous-merge',cwd=user))
                extra_path=Path(extra['manifest']);extra_manifest=json.loads(extra_path.read_bytes())
                events_path=next(extra_path.parent/item['name'] for item in extra_manifest['outputs'] if item['name'].startswith('事件结果_'))
                with events_path.open(encoding='utf-8-sig',newline='') as stream:
                    event,=list(csv.DictReader(stream))
                assert (event['开始时间（s）'],event['确认时间（s）'],event['结束时间（s）'])==('0','1','6'),event
                summary['continuous_energy_j']=38
            if slug=="MESSAGE_ENERGY":
                # 通用逐消息任务走普通run；独立手算两条4000W×0.1s贡献合计800J。
                table = next(manifest_path.parent / item["name"] for item in manifest["outputs"]
                             if item["name"].startswith("会话结果_"))
                with table.open(encoding="utf-8-sig", newline="") as stream:
                    rows = list(csv.DictReader(stream))
                assert len(rows) == 1 and float(rows[0]["energy（J）"]) == 800, rows
                assert rows[0]["energy：状态"] == "完整", rows
                summary["message_energy_j"] = 800
            if slug=="CHARGE":
                with next(manifest_path.parent/item["name"] for item in manifest["outputs"] if item["name"].startswith("事件结果_")).open(encoding="utf-8-sig",newline="") as stream:
                    row=next(csv.DictReader(stream))
                    values={key.rsplit("（",1)[1][:-1]:float(value) for key,value in row.items()
                            if key.endswith(("（Wh）","（Ah）"))}
                assert abs(values["Wh"] - 8000/3600)<1e-12 and abs(values["Ah"]-20/3600)<1e-12,values
                summary["charge"]=values
            if slug=="CALIBRATION":
                table = next(manifest_path.parent / item["name"] for item in manifest["outputs"]
                             if item["name"].startswith("会话结果_"))
                with table.open(encoding="utf-8-sig", newline="") as stream:
                    value = float(next(csv.DictReader(stream))["rated_power（W）"])
                assert abs(value - 50/3) < 1e-12, value
                summary["calibration_mean_w"] = value
            if slug=="CONDITION_ENERGY":
                # 发布环境实际运行跨卷严格门槛例子，不能仅用completed判定业务正确。
                with next(manifest_path.parent/item["name"] for item in manifest["outputs"] if item["name"].startswith("事件结果_")).open(encoding="utf-8-sig",newline="") as stream:
                    events=list(csv.DictReader(stream))
                assert len(events)==1,events
                row=events[0]
                assert (row["开始时间（s）"],row["结束时间（s）"])==("61","122"),row
                assert row["energy_kwh：状态"]=="完整",row
                assert abs(float(row["energy_kwh（kWh）"])-4000*61/3600000)<1e-12,row
                summary["conditional_energy_kwh"]=float(row["energy_kwh（kWh）"])
        summary["cases"][slug]="published"
        save()
    # 专题附带的脚本按用户普通调用方式运行；它会从自身目录导入同包辅助文件。
    summary['topic_examples'] = json.loads(command('topic-readability',
        [python, '-X', 'utf8', '-B', direct / 'examples/readability_examples.py',
         '--output-root', user, '--device-label', device], user))
    assert summary['topic_examples']['status'] == 'passed'
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
