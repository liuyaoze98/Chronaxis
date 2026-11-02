"""合成CSV端到端核验；输入只读，输出使用新建独立目录。"""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
from example_support import new_output

from chronaxis import AnalysisRunner,load_analysis_plan


def main():
    """核两格式/两后端及实际CLI。参数: 无。返回: None。异常: 断言或原运行错误。

    产物位于可指定父路径的唯一目录，源配置和CSV只读；结果/游标均显式关闭。
    """
    directory=Path(__file__).resolve().parent
    output, label = new_output('current-manual-')
    root = output
    for suffix in ('json','yaml'):
        plan=load_analysis_plan(directory/('analysis.'+suffix))
        for backend in ('reference','numpy'):
            with AnalysisRunner(backend).run(plan,output/(suffix+'-'+backend)) as result:
                cursor=result.iter_calculations()
                try:values={row.calculation_id:row.value for row in cursor}
                finally:cursor.close()
                assert values['energy']==38 and values['sample_average']==6
                assert abs(values['time_average']-38/6)<1e-12
    plan=directory/'analysis.yaml'
    def command(*args):
        """真实CLI子进程并保每次结果。参数: 命令参数。返回: stdout。异常: 非零退出或超时。"""
        completed=subprocess.run([sys.executable,'-B','-m','chronaxis',*map(str,args)],cwd=root,
            env=os.environ.copy(),capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert completed.returncode==0,(args,completed.stderr)
        return completed.stdout
    for operation in ('validate','explain'):
        assert command(operation,plan).strip()
        json.loads(command(operation,plan,'--format','json'))
    command('run',plan,'--output',output/'published')
    with (output/'published/会话结果.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    assert len(rows)==1 and float(rows[0]['energy（J）'])==38
    report=dict(device_label=label,status='passed',api_runs=4,cli_commands=5,energy_j=38,sample_mean_w=6,time_weighted_mean_w=38/6)
    (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(output/'verification.json')


if __name__=='__main__':main()
