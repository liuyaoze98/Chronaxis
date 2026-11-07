"""fast单会话及独立批量命令的JSON响应；静态命令不读取报文文件。"""

import json
import sys

from .can_io import _prepare
from .config import compile_config
from .run import run_prepared
from ..planning.checks import PlanValidationError


def execute(args):
    """参数为 CLI 已解析的配置路径和动作。成功返回 0，配置或执行失败返回非零。"""
    try:
        if args.fast_command == 'batch':
            return _batch(args)
        from .session import effective_spec, _worker_process_limit
        spec = effective_spec(compile_config(args.config,_with_database=True), getattr(args,'process_count',None))
        database = spec.pop('_database')
        if args.fast_command != 'run':
            _prepare(spec,database)
    except (ValueError, OSError, TypeError) as error:
        details = {'valid':False,'errors':[item.to_dict() for item in error.diagnostics]
                   if isinstance(error,PlanValidationError) else [{'message':str(error)}]}
        if getattr(error,'blocked_checks',()):
            details['blocked_checks'] = error.blocked_checks
        print(json.dumps(details,ensure_ascii=False),file=sys.stderr)
        return 2
    if args.fast_command == 'run':
        try:
            path = run_prepared(spec,args.output,engine='base_hpc_v1',database=database)
        except (ValueError,OSError,RuntimeError,ArithmeticError) as error:
            print(json.dumps({'errors':[{'message':str(error)}]},ensure_ascii=False),file=sys.stderr)
            return 1
        response = {'manifest_path':str(path)}
    elif args.fast_command == 'explain':
        response = dict(engine='base_hpc_v1', file_policy='single_continuous_session',
                        worker_process_limit=_worker_process_limit(spec['process_count'], len(spec['inputs'])),
                        error_policy='fail_session', evaluation='current_message_before_direction',
                        validity='only_current_message', **spec)
    else:
        response = dict(valid=True,engine='base_hpc_v1')
    print(json.dumps(response,ensure_ascii=False,allow_nan=False))
    return 0


def _batch(args):
    """执行一份独立文件清单。CLI 保留实际报告位置，失败和取消返回非零。"""
    from .batch import run_batch
    try:
        path = run_batch(args.config,args.output,total=args.total,process_count=getattr(args,'process_count',None))
    except BaseException as exc:
        report = getattr(exc,'batch_report',None)
        if report is None:
            raise
        try:
            print(json.dumps({'status':report.status,'report_path':str(report.report_path),
                              'error':str(exc)},ensure_ascii=False))
        finally:
            report.close()
        return 1
    data = json.loads(path.read_text(encoding='utf-8'))
    print(json.dumps({'status':data['status'],'report_path':str(path)},ensure_ascii=False))
    return 0 if data['status']=='completed' else 130 if data['status']=='cancelled' else 1
