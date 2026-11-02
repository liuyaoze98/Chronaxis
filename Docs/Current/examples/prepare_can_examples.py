"""生成同一组 ASC、BLF 和混合目录输入并验证结果。

参数 --output 必须为不存在的目录。只生成合成 CAN 文件；不会修改输入文件。
三个目录均包含相同四次功率更新和观测终点，格式不影响 38 J 的手算结果。
"""
import argparse
from copy import deepcopy
import json
from math import isclose
from pathlib import Path
import shutil
import struct

import can
from chronaxis import AnalysisPlan, AnalysisRunner


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
    raw = dict(config_version=3, dataset={'name':'directory_energy'},
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
        (output/f'{kind}.json').write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
        with AnalysisRunner().run(AnalysisPlan.from_dict(config, base_dir=output), work_dir=output/(kind+'-run')) as result:
            values = {row.calculation_id:row.value for row in result.iter_calculations()}
            assert values.keys() == expected.keys() and all(isclose(values[k], v) for k,v in expected.items()), (kind, values)
            records.append({'directory':kind, 'values':values})
    evidence = output/'verification.json'
    evidence.write_text(json.dumps({'device_label':'home','data_kind':'synthetic','records':records}, indent=2)+'\n', encoding='utf-8')
    print(evidence)


if __name__ == '__main__':
    main()
