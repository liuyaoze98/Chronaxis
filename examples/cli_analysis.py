"""用真实模块CLI贯通旧INI导入、静态报告、运行与发布，并独立对照公共API。

输入在work/m2-cli-example/<uuid>创建，复用已验合成BLF/DBC/CSV及三种INI，
不导入tests或RefProjects。每模式执行四个-B -m chronaxis命令，随后在同一
load_analysis_plan对象上独立AnalysisRunner.run：这是两次真实分析，不声称总共只扫描一次。
手算仍为正桶400J、负桶500J，或single活动[1,3)秒/窗口[0,5)秒、start_only
在1秒触发/窗口[0,3)秒。mapping声明numpy，显式backend只覆盖实际执行。

当前所有平坦结果表跨CLI/API逐bytes相等；明确请求的输入诊断逐字段相等。同一API结果两次write的全部表bytes必须相等。
摘要保存原BOM/CRLF、报告SHA、参数声明身份、命令日志、实际清单及表SHA。
有限结果游标复用已验关闭规则；API结果真实close后RAM账本须为零。CLI的
成功摘要在其close之后输出，本例不把已退出子进程的账本宣称为直接观测。

导入模块不读写输入或启动进程；显式main才生成案例。只测合成数据，不证明
旧完整cache/T54、LC02/L07修复、用户日志、RSS或其它平台已经通过。
"""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.migration import load_legacy_ini

# 两种启动方式使用同一已验夹具和有限游标，不复制旧业务代码或测试Case。
if __package__:
    from .import_legacy_analysis import (create_inputs, mapping_for, original_ini,
        legacy_facts, sclicer_facts, repeated_publish)
else:
    from import_legacy_analysis import (create_inputs, mapping_for, original_ini,
        legacy_facts, sclicer_facts, repeated_publish)

ROOT = Path(__file__).absolute().parents[1]
MAX_EXAMPLE_FILE_BYTES = 2 * 1024**2  # 本例最多八行；限制意外大产物，不作通用读取器。
MAX_EXAMPLE_ROW_BYTES = 1024**2  # 与本例256MiB预算的结果单行上限一致。


def command_json(directory, name, arguments, label):
    """运行真正模块命令，先完整保存退出事实再核单行成功JSON。

    参数: directory为模式根；name为固定命令名；arguments为公开CLI参数；
        label来自当前CHRONAXIS_DEVICE_LABEL或pending，不从路径猜设备。
    返回: 原生JSON对象与命令日志Path。异常: 启动/超时/编码/断言或JSON原错。
    副作用: 唯一work目录保stdout/stderr/exit和实际环境声明；不截掉诊断。
    """
    # 继承显式依赖路径，子进程使用同一Python；禁pyc避免污染任何原输入目录。
    environment = os.environ.copy()
    environment.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    command = [sys.executable, '-B', '-m', 'chronaxis', *map(str, arguments)]
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
        text=True, encoding='utf-8', errors='strict', timeout=120)
    path = directory / ('command-' + name + '.json')
    path.write_text(json.dumps(dict(device_label=label, command=command, cwd=str(ROOT),
        environment=dict(CHRONAXIS_DEVICE_LABEL=environment.get('CHRONAXIS_DEVICE_LABEL'),
            PYTHONPATH=environment.get('PYTHONPATH'), PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8'),
        returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr),
        ensure_ascii=False, indent=2), encoding='utf-8')
    # stderr即使退出0也不能静默忽略；失败日志已在断言之前保存。
    assert completed.returncode == 0, (str(path), completed.returncode, completed.stderr)
    assert completed.stderr == '', (str(path), completed.stderr)
    assert len(completed.stdout.strip().splitlines()) == 1, (str(path), completed.stdout)
    value = json.loads(completed.stdout)
    assert type(value) is dict
    return value, path


def validation_json(report):
    """独立列出公共校验报告固定字段，不调用CLI被测序列化函数。

    参数: report为AnalysisRunner.validate结果。返回: JSON兼容dict。
    异常: 属性错误原样传播，接口漏字段不会被反射默认值掩盖。
    """
    # tuple/只读映射仅在此处按公开JSON合同展开，不增加静态验证承诺。
    return dict(valid=report.valid, errors=list(report.errors), warnings=list(report.warnings),
        capability_status=dict(report.capability_status), execution_ready=report.execution_ready)


def explanation_json(report):
    """独立逐字段对照依赖、有效后端和原配置身份。

    参数: report为AnalysisRunner.explain结果。返回: 含实际输入检查需求的固定七键dict。
    异常: 原属性错误，不访问来源或重构配置。
    """
    # 原节点顺序、状态驱动标记和预算声明都保留，不能只核节点个数。
    # 独立展开公开需求模型；连来源顺序、原因和未采集时间的声明也逐项比较。
    requirements = report.input_requirements
    scopes = [] if requirements is None else [dict(source=item.source,
        input_check=item.input_check, time_scope=item.time_scope,
        required_aliases=list(item.required_aliases), decode_frame_ids=list(item.decode_frame_ids),
        reasons=list(item.reasons), active=item.active) for item in requirements.sources]
    return dict(input_requirements=scopes, validation=validation_json(report.validation), plan_identity=report.plan_identity,
        source_names=list(report.source_names), nodes=[dict(node_id=node.node_id, node_type=node.node_type,
            dependencies=list(node.dependencies), unit=node.unit, backend=node.backend) for node in report.nodes],
        history_ns=dict(report.history_ns), budget=dict(report.budget),
        intervals={name: dict(mode=choice.mode, step_ns=choice.step_ns, driver=choice.driver)
                   for name, choice in report.intervals.resolved},
        diagnostics=dict(trace=report.diagnostics.trace, integrity=report.diagnostics.integrity,
                         retain_work=report.diagnostics.retain_work))


def file_fact(path):
    """有限块核本合成产物完整SHA和字节数，不只相信清单声明。

    参数: path为本例已关闭文件Path。返回: {bytes,sha256}。
    异常: 原I/O或超本例2MiB上限断言；with关闭实际FD。
    """
    digest, size = sha256(), 0
    # 不在read_bytes之前信任未知文件长度；每次只保64KiB并核累计上界。
    with path.open('rb') as handle:
        while chunk := handle.read(65536):
            size += len(chunk)
            assert size <= MAX_EXAMPLE_FILE_BYTES, str(path)
            digest.update(chunk)
    assert handle.closed
    return dict(bytes=size, sha256=digest.hexdigest())


def manifest_facts(path, plan, backend, label, counts):
    """核完成标记、实际身份/计数及每个输出文件的真实SHA。

    参数: path为run_manifest.json；plan为原计划；backend/label/counts为明确预期。
    返回: 已核原清单dict。异常: 原文件/JSON错误或事实断言。
    """
    manifest = json.loads(path.read_text(encoding='utf-8'))
    # 元数据仍是声明与运行事实的结构化记录，不能据单位标记声称物理已测量。
    assert manifest['status'] == 'completed' and manifest['row_counts'] == counts
    assert manifest['run']['plan_hash'] == plan.identity
    assert manifest['run']['backend'] == backend and manifest['run']['device_label'] == label
    assert manifest['run']['config_version'] == 4
    assert len(manifest['outputs']) == len(counts)
    assert {item['name'] for item in manifest['outputs']} == {
        *(name + '.' + manifest['table_format'] for name in counts)}
    for item in manifest['outputs']:
        actual = file_fact(path.parent / item['name'])
        assert actual['bytes'] == item['bytes']
        if 'sha256' in item:
            assert actual['sha256'] == item['sha256']
    return manifest


def compare_publications(cli_dir, api_dir, tables, counts, plan, cli_manifest, api_manifest):
    """逐表核CLI/API实际字节与摘要。参数: 发布目录及事实。返回: 对照。异常: 不一致。"""
    files = {}
    for name in counts:
        one, two = cli_dir / (name + '.' + tables), api_dir / (name + '.' + tables)
        assert one.read_bytes() == two.read_bytes(), name
        files[name] = dict(cli=file_fact(one), api=file_fact(two), bytes_identical=True)
    assert cli_manifest['run'].get('input_diagnostics', []) == api_manifest['run'].get('input_diagnostics', [])
    return dict(files=files, all_business_fields_equal=True, all_tables_bytes_identical=True)


def prepare_mode(directory, mode, batch_rows, tables, label):
    """写原INI/mapping并经真实legacy import发布，核配置/参数身份未漂移。

    参数: directory为模式根；mode/切批/表格式/实际环境标签均明确。
    返回: (已发布AnalysisPlan,迁移事实dict)。异常: 命令、导入或原字节/报告/身份断言。
    """
    config_dir = directory / 'mapping-directory'
    config_dir.mkdir(parents=True)
    ini, mapping_path, output = config_dir / 'old.ini', config_dir / 'mapping.json', directory / 'converted' / 'analysis.json'
    content, mapping = original_ini(mode), mapping_for(mode, 'numpy', batch_rows, tables, label)
    ini.write_bytes(content)
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')
    # 此独立静态API只读两份配置，不读数据；之后实际CLI仍完成全部导入和发布动作。
    expected = load_legacy_ini(ini, mapping_path, mode=mode, device_label=label)
    assert expected.plan is not None and expected.report.status == 'success'
    brief, command = command_json(directory, 'import', ['legacy', 'import', ini, '--mode', mode,
        '--mapping', mapping_path, '--output', output], label)
    assert set(brief) == {'status', 'plan', 'original', 'report', 'device_label', 'issue_count', 'error_count', 'warning_count'}
    assert (brief['status'], brief['plan'], brief['device_label'], brief['error_count']) == ('success', str(output), label, 0)
    report = json.loads(Path(brief['report']).read_text(encoding='utf-8'))
    assert report == expected.report.to_dict()
    assert brief['issue_count'] == len(report['issues'])
    assert brief['warning_count'] == sum(item['level'] == 'warning' for item in report['issues'])
    assert ini.read_bytes() == Path(brief['original']).read_bytes() == expected.original_ini == content
    assert content.startswith(b'\xef\xbb\xbf') and b'\r\n' in content
    assert report['source_sha256'] == sha256(content).hexdigest()
    plan = load_analysis_plan(output)
    assert plan.identity == expected.plan.identity == report['plan_identity']
    assert plan.bindings.identity == expected.plan.bindings.identity
    assert plan.execution.backend == 'numpy'
    declarations = []
    for actual, old in zip(plan.message_calculations, expected.plan.message_calculations):
        assert actual.expr.identity == old.expr.identity and actual.expr.bindings.identity == old.expr.bindings.identity
        assert tuple((item.name, item.value, item.unit) for item in actual.parameters) == (
            ('period', 0.1, 's'), ('factorZ', 1.0, '1'))
        declarations.append(dict(calculation_id=actual.calculation_id, compiled_identity=actual.expr.identity,
            declaration_identity=actual.expr.bindings.identity))
    assert len(plan.message_calculations) == len(expected.plan.message_calculations) == (2 if mode == 'legacy_sum' else 0)
    return plan, dict(mode=mode, ini=str(ini), mapping=str(mapping_path), plan_path=str(output),
        preserved_original=brief['original'], report_path=brief['report'], source_sha256=report['source_sha256'],
        report_file=file_fact(Path(brief['report'])), plan_identity=plan.identity,
        binding_declaration_identity=plan.bindings.identity, parameter_declarations=declarations,
        command_log=str(command), original_bom_crlf_preserved=True)


def run_example(backend='numpy', batch_rows=2, tables='jsonl'):
    """完成三模式的真实CLI/API对照，所有核验及API关闭成功后才保存summary。

    参数: backend为reference/numpy；batch_rows为1/2/7；tables为csv/jsonl。
    返回: 有限summary dict，summary_path指本次证据。异常: 参数、原I/O/进程/
        依赖/公开API或断言错误；不吞取消、不跳过未安装依赖、不假报部分成功。
    副作用: 只在work/m2-cli-example/<uuid>生成输入、命令日志、暂存及发布。
    """
    if type(backend) is not str or backend not in ('reference', 'numpy'):
        raise ValueError('backend必须为reference或numpy')
    if type(batch_rows) is not int or batch_rows not in (1, 2, 7):
        raise ValueError('batch_rows必须为1、2或7')
    if type(tables) is not str or tables not in ('csv', 'jsonl'):
        raise ValueError('tables必须为csv或jsonl')
    root = ROOT / 'work' / 'm2-cli-example' / uuid4().hex
    root.mkdir(parents=True)
    inputs = create_inputs(root)
    label, modes = os.environ.get('CHRONAXIS_DEVICE_LABEL', '').strip() or 'pending', {}
    for mode in ('legacy_sum', 'sclicer_single', 'sclicer_start_only'):
        directory = root / mode
        plan, migration = prepare_mode(directory, mode, batch_rows, tables, label)
        # 发布目录改变不应改变mapping-directory解释的实际输入目标。
        if mode == 'legacy_sum':
            assert plan.sources[0].config.path.resolve() == inputs['blf'].resolve()
            assert plan.sources[0].config.dbc_path.resolve() == inputs['dbc'].resolve()
        else:
            assert len(plan.sources[0].config.paths) == 1
            assert plan.sources[0].config.paths[0].resolve() == inputs['csv'].resolve()
        runner, identity = AnalysisRunner(backend=backend), plan.identity
        path, encoded = Path(migration['plan_path']), Path(migration['plan_path']).read_bytes()
        validation, valid_log = command_json(directory, 'validate', ['validate', path, '--backend', backend, '--format', 'json'], label)
        explanation, explain_log = command_json(directory, 'explain', ['explain', path, '--backend', backend, '--format', 'json'], label)
        assert validation == validation_json(runner.validate(plan))
        assert validation['valid'] and validation['execution_ready'] and validation['errors'] == []
        assert explanation == explanation_json(runner.explain(plan)) and explanation['plan_identity'] == identity
        # CLI路径参数是全新目录；后端覆盖不能改写mapping、生成配置或原plan。
        cli_dir = directory / 'cli-published'
        brief, run_log = command_json(directory, 'run', ['run', path, '--output', cli_dir,
            '--work-dir', directory / 'cli-work', '--backend', backend], label)
        assert set(brief) == {'status', 'run_id', 'plan_identity', 'backend', 'output', 'manifest', 'row_counts', 'device_label'}
        assert (brief['status'], brief['plan_identity'], brief['backend'], brief['device_label']) == ('completed', identity, backend, label)
        assert (brief['output'], brief['manifest']) == (str(cli_dir), str(cli_dir / 'run_manifest.json'))
        counts = (dict(calculations=2, contributions=8, input_trace=4)
            if mode == 'legacy_sum' else dict(events=1, segments=1))
        assert brief['row_counts'] == counts
        cli_manifest = manifest_facts(Path(brief['manifest']), plan, backend, label, counts)
        assert cli_manifest['run']['run_id'] == brief['run_id']
        with runner.run(plan, work_dir=directory / 'api-work') as result:
            # 手算由既有独立facts逐条核原帧/求值序号及窗口，不拿CLI输出自证。
            actual = legacy_facts(result) if mode == 'legacy_sum' else sclicer_facts(result, mode)
            assert result.metadata.plan_hash == identity and result.metadata.backend == backend
            assert result.metadata.device_label == label
            assert result.metadata.run_id != brief['run_id']
            repeated = repeated_publish(result, directory, tables)
            api_dir = Path(repeated['directories'][0])
            api_manifest = manifest_facts(api_dir / 'run_manifest.json', plan, backend, label, counts)
            assert api_manifest['run']['run_id'] == result.metadata.run_id
            comparison = compare_publications(cli_dir, api_dir, tables, counts, plan, cli_manifest, api_manifest)
            budget, api_run_id, input_identity = result.spool.budget, result.metadata.run_id, result.metadata.input_identity
        # API真实上下文已退出；不把发布前清单中的非零活结果费用误叫泄漏。
        assert result._closed and result.spool._closed and budget.ram_bytes == 0
        assert path.read_bytes() == encoded and plan.identity == identity and plan.execution.backend == 'numpy'
        modes[mode] = dict(migration=migration, actual=actual, cli=brief,
            command_logs=[migration['command_log'], str(valid_log), str(explain_log), str(run_log)],
            api=dict(run_id=api_run_id, input_identity=input_identity, repeated_publish=repeated,
                ram_after_close=budget.ram_bytes, closed=True, bounded_readers_closed=True),
            comparison=comparison, independent_actual_runs=2)
    # 所有模式都完成后才保存总成功；命令日志早已保留，失败不会留下虚假总成功。
    summary = dict(status='completed', device_label=label, data_kind='synthetic', backend=backend,
        declared_backend='numpy', batch_rows=batch_rows, tables=tables, work_root=str(root),
        summary_path=str(root / 'summary.json'), inputs={name: str(path) for name, path in inputs.items()},
        modes=modes, analysis_runs=dict(cli=3, api=3, total=6), cli_commands=12,
        manual=dict(legacy_sum_J=dict(positive=400.0, negative=500.0),
            single=dict(activity_ns=[1_000_000_000, 3_000_000_000], segment_ns=[0, 5_000_000_000]),
            start_only=dict(point_ns=1_000_000_000, segment_ns=[0, 3_000_000_000])),
        limitations=['合成输入，不代表用户实际数据验收或旧完整cache/T54通过',
            'CLI与API独立读取；当前平坦表全部字节相同',
            'CLI退出0和成功摘要按关闭后合同解释；本例不直接读取已退出进程的RAM账本',
            'API同一结果两次发布全部表bytes相等；普通三表跨独立运行bytes相等',
            'RAM是内部保守账本，不是RSS；LC02/L07及未测平台限制保持'])
    Path(summary['summary_path']).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def main(argv=None):
    """解析显式示例选项，完成后仅显示summary_path，不打印长命令输出。

    参数: argv为可选参数序列，None使用进程参数。返回: 完整有限summary dict。
    异常: argparse参数错误及示例原错；不吞取消，不运行历史主程序。
    """
    parser = argparse.ArgumentParser(description='三模式真实CLI链与公共API独立对照')
    parser.add_argument('--backend', choices=('reference', 'numpy'), default='numpy')
    parser.add_argument('--batch-rows', type=int, choices=(1, 2, 7), default=2)
    parser.add_argument('--tables', choices=('csv', 'jsonl'), default='jsonl')
    arguments = parser.parse_args(argv)
    summary = run_example(arguments.backend, arguments.batch_rows, arguments.tables)
    print(json.dumps(dict(summary_path=summary['summary_path']), ensure_ascii=False))
    return summary


if __name__ == '__main__':
    # spawn只导入定义；只有显式入口才创建输入、执行CLI和独立API分析。
    main()
