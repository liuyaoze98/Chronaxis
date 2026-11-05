"""用四条合成CAN报文演示每条表达式贡献、缺值原因和最终能量汇总。

前两条在同一时刻，各含4000W；period显式为0.1s，每条贡献400J。第三条
同类报文没有解出功率，记录missing_input；第四条未知ID不构造求值。因此
总和800J，3次尝试、2次有效贡献、1次跳过；不再乘真实时间差。

本模块导入时不写文件或启动进程。main显式创建唯一work案例、BLF/DBC和计划，
仅经公开load_analysis_plan、AnalysisRunner及AnalysisResult执行，两次发布同一结果。有限游标
设已知行数上限并关闭，退出后核RAM账本归零，summary.json保实际设备标签。
输入均为合成，不代表用户日志或旧ChrgInfo完整触发/cache兼容。
"""

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4
from chronaxis import AnalysisRunner, load_analysis_plan


def create_inputs(root):
    """在本例新目录写四条BLF及单消息DBC，缺值来自真实空payload。

    参数: root为唯一新案例目录。返回: (blf,dbc)两个Path。
    异常: 可选CAN依赖、写入或stop原错，不跳过验证，不修改历史资源。
    """
    import can
    blf, dbc = root/'power.blf', root/'power.dbc'
    dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
        'BO_ 256 Power: 2 Node\n SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node\n', encoding='utf-8')
    writer = can.BLFWriter(blf)
    try:
        for second, frame_id, payload in ((0, 256, b'\xa0\x0f'), (0, 256, b'\xa0\x0f'),
                (1, 256, b''), (2, 257, b'\xff')):
            writer.on_message_received(can.Message(timestamp=1700000000.0+second,
                arbitration_id=frame_id, is_extended_id=False, channel=0, data=payload))
    finally:
        writer.stop()
    return blf, dbc


def configuration(blf, dbc, backend, batch_rows, tables):
    """声明完整消息定位、W/s/J单位和同刻策略，不把period当实际dt。

    参数: blf/dbc为本例路径，backend/batch_rows/tables为显式选项。
    返回: 可交load_analysis_plan的JSON字典。异常: 本函数无输入I/O；配置错误由公开校验拒绝。
    """
    return dict(config_version=4,
        dataset=dict(name='message_energy', entity='synthetic_device', session='session',
            domain=dict(start='0s', end='4s')),
        sources=[dict(name='bus', source_type='can_blf', path=str(blf),
            legacy_profile='sclicer-functions-v1', reader_options=dict(decode_policy='legacy'), dbc_by_channel={'0':str(dbc)},
            time=dict(time_type='relative', unit='s', origin='synthetic_message_clock', offset='-1700000000s'))],
        signals=[dict(name='power', source='bus', field=dict(channel=0,  signal='Power',
            frame_id=256, is_extended=False, is_fd=False), dtype='float64', unit='W',
            valid_for='1ns', same_time_policy='last_by_sequence')],
        rules=[], windows=[], calculations=[],
        message_calculations=[dict(name='energy', source='bus', profile='sclicer-functions-v1', operation='legacy_sum',
            message_policy='current_message-v1',
            update_message=dict(channel=0, frame_id=256, is_extended=False, is_fd=False),
            expr='power * period', unit='J', parameters=dict(period=dict(value=0.1, unit='s')))],
        execution=dict(backend=backend, batch_rows=batch_rows, result_buffer_rows=1,
            memory_budget_bytes=256*1024**2), outputs=dict(tables=tables, contributions='full'), diagnostics=dict(trace=True, integrity=True),
        metadata=dict(device_label=os.environ.get('CHRONAXIS_DEVICE_LABEL','pending'),
            data_kind='synthetic', example='message_energy_analysis'))


def bounded_rows(reader, maximum):
    """只收集本合成夹具已知上限的少量行，任何退出路径都关闭真实游标。

    参数: reader为公开结果游标；maximum为明确上限。返回: 有限tuple。
    异常: 原读取或上限错误优先，关闭副错附note和真实reader；无主错时传播关闭错误。
    """
    rows, primary = [], None
    try:
        for row in reader:
            assert len(rows)<maximum, '示例输出超过合成行数上限'
            rows.append(row)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            reader.close()
        except BaseException as cleanup:
            if primary is None:
                raise
            # 不让二次关闭盖掉原取消/读取错误，未关真实reader仍留父结果及恢复属性。
            primary.add_note('示例游标关闭附加失败: '+type(cleanup).__name__)
            if not reader.closed and getattr(primary,'row_iterator_cleanup_owner',None) is None:
                primary.row_iterator_cleanup_owner=reader
    return tuple(rows)


def run_example(backend='numpy', batch_rows=2, tables='csv'):
    """创建并运行一例，手算断言、两次发布和关闭账本全部通过后写summary。

    参数: backend为reference/numpy，batch_rows为1/2/7，tables为csv/jsonl。
    返回: 含来源标签、手算、实际与输出路径的小字典。异常: 原API或手算/关闭断言错误。
    副作用: 仅在work/message-energy-example的唯一子目录创建输入、暂存和发布。
    """
    root = Path(__file__).resolve().parents[1]/'work/message-energy-example'/uuid4().hex
    root.mkdir(parents=True)
    blf, dbc = create_inputs(root)
    config = configuration(blf,dbc,backend,batch_rows,tables)
    plan_path = root/'analysis.json'
    plan_path.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    plan = load_analysis_plan(plan_path)
    runner = AnalysisRunner()
    assert runner.validate(plan).execution_ready
    with runner.run(plan,work_dir=root/'analysis-work') as result:
        # 两条同刻原帧各自贡献；明确请求明细后，从实际行统计尝试和跳过。
        summary, = bounded_rows(result.iter_calculations(), 1)
        rows = bounded_rows(result.iter_contributions(), 3)
        traces = {row.original_sequence: row for row in bounded_rows(result.iter_input_trace(), 3)}
        assert summary.value == 800.0 and summary.unit == 'J'
        assert tuple(row.original_sequence for row in rows) == (0, 1, 2)
        assert tuple(row.evaluation_index for row in rows) == (0, 1, 2)
        assert tuple(row.value for row in rows) == (400.0, 400.0, None)
        assert tuple(row.reason for row in rows) == ('contributed', 'contributed', 'missing_input')
        assert set(traces) == {0, 1, 2}
        source, = result.metadata.input_diagnostics
        assert source.source == 'bus' and source.record_count == 3 and source.source_eof
        assert source.sha256 and source.digest_scope == 'required-decoded-records-v1'
        # 两次write都消费已封口结果；不通过第二次run产生另一份分析。
        first, second = result.write(root/'published1'),result.write(root/'published2')
        assert first.status==second.status=='completed' and first.row_counts==second.row_counts
        for name,count in first.row_counts:
            left,right=root/'published1'/(name+'.'+tables),root/'published2'/(name+'.'+tables)
            assert left.read_bytes()==right.read_bytes(), name
        budget = result.spool.budget
        report = dict(device_label=result.metadata.device_label, data_kind='synthetic', backend=backend,
            batch_rows=batch_rows, tables=tables, work_dir=str(root), message_policy='current_message-v1',
            expression=config['message_calculations'][0]['expr'], parameters=dict(period=dict(value=0.1, unit='s')),
            expected_energy_J=800.0, actual_energy_J=summary.value,
            evaluation_count=len(rows), contribution_count=sum(row.value is not None for row in rows),
            skipped_count=sum(row.value is None for row in rows), input_diagnostics=source.to_dict(),
            contributions=[dict(original_sequence=row.original_sequence, evaluation_index=row.evaluation_index,
                time_ns=traces[row.original_sequence].time_ns,
                raw_values=json.loads(traces[row.original_sequence].values_json),
                contribution_J=row.value, reason=row.reason) for row in rows],
            published=[str(first.output_dir), str(second.output_dir)], repeated_tables_identical=True,
            limitations=['合成数据；未验用户真实日志', '逐消息汇总仅session范围',
                '诊断摘要只覆盖所需解码记录；不代表原始文件完整摘要',
                '本例显式选legacy解码以演示空payload跳过；默认strict会拒绝该帧'])
    assert budget.ram_bytes==0
    report['ram_after_close']=budget.ram_bytes
    (root/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    """解析明确选项，运行一例并只显示结果及文件路径。

    参数: 无，从CLI读取选项。返回: 小报告dict。异常: argparse或实际示例原错。
    """
    parser=argparse.ArgumentParser(description='逐条报文贡献、缺值原因及800J汇总示例')
    parser.add_argument('--backend',choices=('reference','numpy'),default='numpy')
    parser.add_argument('--batch-rows',type=int,choices=(1,2,7),default=2)
    parser.add_argument('--tables',choices=('csv','jsonl'),default='csv')
    args=parser.parse_args()
    report=run_example(args.backend,args.batch_rows,args.tables)
    print(f"{report['backend']} / batch={report['batch_rows']}: 400J + 400J，跳过1条，合计800J")
    print('明细和两次发布：'+report['work_dir'])
    return report


if __name__=='__main__':
    # spawn子进程只在显式入口启动，导入示例不产生数据或分析。
    main()
