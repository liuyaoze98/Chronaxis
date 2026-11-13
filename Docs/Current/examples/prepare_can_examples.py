"""生成同一组 ASC、BLF 和混合目录输入并验证结果。

参数 --output 必须为不存在的目录。只生成合成 CAN 文件；不会修改输入文件。
三个目录均包含相同四次功率更新和观测终点，格式不影响 38 J 的手算结果。
"""
import argparse
from copy import deepcopy
import json
from io import StringIO
from math import isclose
from pathlib import Path
import shutil
import struct

import can
from ruamel.yaml import YAML
from chronaxis import AnalysisRunner, load_analysis_plan


def commented_yaml(config):
    """将同一配置对象写成带说明的教学YAML，不另维护一套配置。

    参数: config为本脚本生成的配置字典。返回: 可解析、行末注释对齐的文本。
    异常: 未登记字段或序列化后内容改变时拒绝输出。无文件副作用。
    """
    comments = {
        'config_version': '分析配置版本，填写整数4',
        'dataset': '命名这次连续分析', 'name': '本对象名称，供引用或结果识别',
        'execution': '设置文件读取和解码的并行上限',
        'process_count': '最多4个文件工作进程；本例两卷，最多使用两个',
        'sources': '同一次记录的输入来源', 'paths': '输入目录，相对本配置；文件按自然序接续',
        'dbc_by_channel': '各通道使用的DBC文件', '1': '用户通道1的DBC，相对本配置',
        'time': '将日志时间转换到共同起点', 'offset': '减去合成记录的绝对起点，得到0至6秒',
        'signals': '定义计算可引用的功率信号', 'field': '在DBC中定位原始信号',
        'frame_id': '报文ID，十进制256等于0x100', 'signal': 'DBC中的原始信号名',
        'calculations': '请求能量、样本均值和时间加权均值',
        'operation': '选择本项计算方法', 'expr': '使用已定义的power功率值',
    }
    yaml = YAML(typ='safe', pure=True)
    yaml.default_flow_style = False
    yaml.sort_base_mapping_type_on_output = False
    stream = StringIO()
    yaml.dump(config, stream)
    lines = stream.getvalue().splitlines()
    width = max(map(len, lines)) + 2
    # 此配置的列表项均为映射；逐键注释，不改动缩进、值或列表结构。
    annotated = []
    for line in lines:
        key = line.strip().removeprefix('- ').split(':', 1)[0].strip("'\"")
        annotated.append(line.ljust(width) + '# ' + comments[key])
    text = '\n'.join(annotated) + '\n'
    if yaml.load(text) != config:
        raise ValueError('教学YAML与原配置不同')
    return text


def main():
    """生成教学文件并逐个目录运行。返回: 无。异常: IO、运行或数值核对失败。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__).parent/'data/can/teaching.dbc', output/'teaching.dbc')
    # BLF 必须有非零的文件时间。三种目录统一采用同一时间起点和同一校准。
    epoch = 1_700_000_000
    chunks = (((0, 2.), (1, 4.), (3, 8.)), ((4, 10.), (6, None)))
    for kind in ('asc', 'blf', 'mixed'):
        folder = output/kind
        folder.mkdir()
        for index, chunk in enumerate(chunks, 1):
            suffix = 'asc' if kind == 'asc' or (kind == 'mixed' and index == 1) else 'blf'
            messages = [can.Message(timestamp=epoch+t, arbitration_id=0x100 if value is not None else 0x7FE,
                                    is_extended_id=False, channel=0,
                                    data=struct.pack('<d', value) if value is not None else b'\0')
                        for t, value in chunk]
            path = folder/f'part{index}.{suffix}'
            if suffix == 'asc':
                lines = ['base hex timestamps absolute']
                lines += [f'{m.timestamp:.6f} 1 {m.arbitration_id:X} Rx d {len(m.data)} '+m.data.hex(' ').upper() for m in messages]
                path.write_text('\n'.join(lines)+'\n', encoding='ascii', newline='\n')
            else:
                with can.BLFWriter(path) as writer:
                    for message in messages:
                        writer.on_message_received(message)
    # 每个目录中的两个分卷可同时读取，仍作为一次连续分析计算。
    raw = dict(config_version=4, dataset={'name':'directory_energy'}, execution={'process_count':4},
               sources=[{'paths':'asc','dbc_by_channel':{'1':'teaching.dbc'},'time':{'offset':f'-{epoch}s'}}],
               signals=[{'name':'power','field':{'frame_id':'0x100','signal':'Power'}}],
               calculations=[{'name':'energy','operation':'integral','expr':'power'},
                             {'name':'sample_average','operation':'sample_mean','expr':'power'},
                             {'name':'time_average','operation':'time_weighted_mean','expr':'power'}])
    expected = {'energy':38., 'sample_average':6., 'time_average':38./6.}
    records = []
    for kind in ('asc', 'blf', 'mixed'):
        config = deepcopy(raw)
        config['sources'][0]['paths'] = kind
        path = output/f'{kind}.yaml'
        path.write_text(commented_yaml(config), encoding='utf-8', newline='\n')
        # JSON仍可供程序读取；教程和本次验证实际使用生成的YAML文件。
        (output/f'{kind}.json').write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
        with AnalysisRunner().run(load_analysis_plan(path), work_dir=output/(kind+'-run')) as result:
            values = {row.calculation_id:row.value for row in result.iter_calculations()}
            assert values.keys() == expected.keys() and all(isclose(values[k], v) for k,v in expected.items()), (kind, values)
            records.append({'directory':kind, 'values':values})
    evidence = output/'verification.json'
    evidence.write_text(json.dumps({'device_label':'home','data_kind':'synthetic','records':records}, indent=2)+'\n', encoding='utf-8')
    print(evidence)


if __name__ == '__main__':
    main()
