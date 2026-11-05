"""在本工作进程内执行事先验证的参数，只上传本文件的少量结果。"""
from hashlib import sha256
import os
from pathlib import Path
from time import perf_counter
from .run import run_prepared
from .._batch_worker import _diagnostics

def _run_file(packet, directory, cancel):
    """在已持有该文件的工作进程直接分析并发布。返回任务状态及可选的小型汇总行。"""
    start = perf_counter()
    spec = packet['spec']
    facts = dict(job_id=packet['job_id'],plan_path=packet['path'],input_identity=str(spec['path']))
    try:
        if cancel.is_set():
            raise InterruptedError('文件启动前收到取消请求')
        database = None
        if packet['total']:
            # 求和要求同一份解码声明。核对本进程实际加载的 DBC，变动则该成员失败。
            import cantools
            dbc = Path(spec['dbc'])
            before = _dbc_digest(dbc)
            database = cantools.database.load_file(dbc)
            if before != spec['_dbc_digest'] or _dbc_digest(dbc) != before:
                raise ValueError('求总量期间模板的 DBC 内容发生改变')
        directory.mkdir(exist_ok=False)
        value = run_prepared(spec,directory/'output',engine='base_hpc_v1',
                             _return_rows=packet['total'], cancel_event=cancel,database=database)
        manifest, rows = value if packet['total'] else (value, None)
        return dict(**facts,status='completed',output_dir=manifest.parent,manifest_path=manifest,
                              run_id=directory.name,elapsed_seconds=perf_counter()-start), rows
    except InterruptedError as exc:
        return dict(**facts,status='cancelled',error_type='InterruptedError',
                              error_message=str(exc),elapsed_seconds=perf_counter()-start), None
    except Exception as exc:
        return dict(**facts,status='failed',error_type=type(exc).__name__,
                              error_message=str(exc),elapsed_seconds=perf_counter()-start), None


def _dbc_digest(path):
    """读取解码声明的摘要；只在请求跨文件求和时使用。"""
    with Path(path).open('rb') as source:
        return sha256(source.read()).hexdigest()


def file_response(packet, directory, cancel):
    """仅传已冻结的结果字段；接收方使用与通用批量相同的结果模型校验。"""
    try:
        result, rows = _run_file(packet, directory, cancel)
    except BaseException as exc:
        result = dict(job_id=packet['job_id'],status='failed',plan_path=packet.get('path'),
                      error_type=type(exc).__name__,error_message=str(exc),error_chain=_diagnostics(exc))
        rows = None
    result['worker_pid'] = os.getpid()
    response = ('fast_result', result, False)
    return response + (rows,) if packet['total'] else response
