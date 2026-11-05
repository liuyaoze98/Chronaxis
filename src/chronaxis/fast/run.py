"""准备和执行单文件同帧累计，仅在文件全部计算成功后发布结果。"""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ..results.publication import PublicationNames, output_root
from .can_io import run_one


def run_prepared(spec, output, *, engine, database=None, cancel_event=None, _return_rows=False):
    """执行单文件，返回完成清单。批量请求跨文件总量时另返回未舍入指标行。"""
    table_format = spec.get('table_format','jsonl')
    if table_format not in ('jsonl','csv','readable_csv'):
        raise ValueError('fast 单文件仅支持 readable_csv、csv 或 jsonl 汇总')
    root = output_root(output)
    rows,warnings = run_one(spec,database,cancel_event=cancel_event)
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
            record = dict(engine=engine,status='completed',input=str(spec['path']),warnings=warnings,
                          outputs=[{'name':names.names[table]}])
            (temp/manifest).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
            names.publish(temp,manifest)
        path = root/names.names[manifest]
        return (path,tuple(rows)) if _return_rows else path
    finally:
        names.close()


def run(config, output):
    """读取单文件 Chronaxis 配置并执行，返回该次发布的 manifest 路径。"""
    from .config import compile_config
    spec = compile_config(config,_with_database=True)
    return run_prepared(spec,output,engine='base_hpc_v1',database=spec.pop('_database'))
