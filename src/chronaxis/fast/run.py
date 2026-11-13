"""准备和执行单会话同帧累计，仅在全部输入、累计和资源关闭成功后发布结果。"""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ..results.publication import PublicationNames, output_root


def run_prepared(spec: dict, output: str | Path, *, engine: str, database: object | None = None,
                 cancel_event: object | None = None, _return_rows: bool = False,
                 work_dir: str | Path | None = None, _programs_checked: bool = False) -> Path | tuple[Path, tuple]:
    """执行冻结会话并最后发布清单。

    参数: spec编译声明，output结果目录，engine执行器标识，database可复用DBC，
    cancel_event可选取消，_return_rows控制独立batch同时取得未舍入行，work_dir暂存父目录。
    _programs_checked仅供紧接公共编译器的内部调用；默认False仍检查全部原始公式。
    返回: 清单Path；_return_rows=True时返回(Path, 行tuple)。异常: 执行/取消/发布错误。
    """
    table_format = spec.get('table_format','jsonl')
    if table_format not in ('jsonl','csv','readable_csv'):
        raise ValueError('fast仅支持readable_csv、csv或jsonl汇总')
    root = output_root(output)
    from .session import run_session
    execution = {}
    rows,warnings = run_session(spec,database,cancel_event=cancel_event,work_dir=work_dir,
                               statistics=execution,_programs_checked=_programs_checked)
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError('发布结果前取消')
    table = 'results.jsonl' if table_format == 'jsonl' else 'results.csv'
    manifest = 'run_manifest.json'
    names = PublicationNames(root, (table,manifest))
    try:
        with TemporaryDirectory(dir=root,prefix='.fast-') as private:
            temp = Path(private)
            with (temp/table).open('x',encoding='utf-8',newline='') as out:
                if table_format == 'readable_csv':
                    writer = csv.writer(out)
                    writer.writerow(['计算项','结果','单位','状态','说明'])
                    reasons = {'no_target_frames':'没有目标报文','no_target_in_domain':'分析范围内没有目标报文',
                               'empty_file':'文件无观测数据','no_selected_direction':'有效目标帧均未进入该方向桶'}
                    for row in rows:
                        writer.writerow([row['name'],row['value'],row['unit'],
                                         '完整' if row['status']=='complete' else '无法确定',
                                         reasons.get(row.get('reason'),'')])
                elif table_format == 'csv':
                    writer = csv.DictWriter(out,fieldnames=['name','value','unit','status','reason'])
                    writer.writeheader()
                    writer.writerows(rows)
                else:
                    for row in rows:
                        out.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
            record = dict(engine=engine,status='completed',inputs=[item['path'] for item in spec.get('inputs', [dict(path=spec['path'])])],
                          execution=execution,warnings=warnings,
                          outputs=[{'name':names.names[table]}])
            (temp/manifest).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
            names.publish(temp,manifest)
        path = root/names.names[manifest]
        return (path,tuple(rows)) if _return_rows else path
    finally:
        names.close()


def run(config: str | Path, output: str | Path, *, process_count: int | None = None,
        work_dir: str | Path | None = None, cancel_event: object | None = None) -> Path:
    """运行一份fast单会话配置，所有分卷成功后发布汇总。

    参数: config为YAML/JSON配置路径；output为结果目录；process_count为可选正整数
    工作进程上限覆盖，None沿用配置默认1；work_dir为可选暂存父目录；cancel_event
    为可选带is_set方法的取消事件。覆盖不修改配置，1在当前进程执行。
    返回: pathlib.Path，本次成功清单。异常: 配置/文件/资源/数值错误及InterruptedError。
    """
    from .config import compile_config
    from .session import effective_spec
    spec = effective_spec(compile_config(config,_with_database=True),process_count)
    return run_prepared(spec,output,engine='base_hpc_v1',database=spec.pop('_database'),
                        work_dir=work_dir,cancel_event=cancel_event,_programs_checked=True)
