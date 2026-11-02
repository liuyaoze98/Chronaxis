"""实际运行当前公共定义例子、来源命令和独立配置导出，产物只写新建独立目录。

输入为同目录analysis-imports.yaml、shared/definitions.yaml和快速开始 ASC / DBC。
两后端及导出后运行应得到38J、6W、38/6W、76J；这些是合成预期，不是设备业务结论。
副作用限本次新目录，删除的仅是复制后公共定义，用于证明导出已独立；不修改手册原件。
"""
from datetime import datetime,timezone,timedelta
import json
from math import isclose
from pathlib import Path
import shutil
import subprocess
import sys
from example_support import new_output

from chronaxis import AnalysisRunner,load_analysis_plan


def calculate(path, work, backend):
    """运行并核四个手算结果。参数: 配置路径、新work目录、后端名。返回: 值字典。异常: 执行/断言错误。"""
    expected={'energy':38.,'sample_average':6.,'time_average':38./6.,'double_energy':76.}
    with AnalysisRunner(backend).run(load_analysis_plan(path),work) as result:
        reader=result.iter_calculations()
        try:values={row.calculation_id:row.value for row in reader}
        finally:reader.close()
        assert set(values)==set(expected)
        for name,value in expected.items():assert isclose(values[name],value,rel_tol=1e-12,abs_tol=1e-12),(name,values)
    return values


def command(root, arguments):
    """从不同目录执行实际CLI。参数: 工作根、字符串参数列表。返回: stdout。异常: 非零退出/超时。"""
    completed=subprocess.run([sys.executable,'-B','-m','chronaxis',*map(str,arguments)],
        cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert completed.returncode==0,(arguments,completed.stdout,completed.stderr)
    return completed.stdout


def main():
    """复制例子、核来源、导出后移除公共文件再运行。参数: 无。返回: None。异常: IO/断言/运行错误。"""
    examples=Path(__file__).resolve().parent
    root, label = new_output('imports-manual-')
    # 明确复制所用的配置与 CAN 教学输入；保持相对结构，不扫描业务目录或复制其他用户文件。
    for relative in ('analysis-imports.yaml','shared/definitions.yaml','data/can/quickstart.asc','data/can/teaching.dbc'):
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(examples/relative,target)
    plan=root/'analysis-imports.yaml'
    values={backend:calculate(plan,root/('run-'+backend),backend) for backend in ('reference','numpy')}
    command(root,['validate',plan]);command(root,['explain',plan])
    origins=json.loads(command(root,['config','origins',plan,'--fields','--format','json']))
    assert any(row['declared_path']=='$.signals[0].field.signal' and Path(row['file']).name=='definitions.yaml'
               for row in origins['items'])
    effective=root/'independent.json'
    command(root,['config','resolve',plan,'--defaults','--output',effective])
    (root/'shared/definitions.yaml').unlink()
    values['independent']=calculate(effective,root/'run-independent','numpy')
    # 只保存有限验证摘要，原日志和完整配置不复制到额外报告中。
    report=dict(device_label=label,data_kind='synthetic',status='passed',
                checked_at=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
                values=values,cli_commands=4,source_fields=len(origins['items']),definition_removed=True)
    output=root/'verification.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(output)


if __name__=='__main__':
    main()
