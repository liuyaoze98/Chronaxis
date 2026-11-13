"""通过同一 DBC 检查真实 ASC、BLF 的帧身份、文件状态和失败发布。"""

import csv
import json
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
import unittest

import can

from chronaxis.configuration import load_configuration
from chronaxis.fast import run
from chronaxis.fast.can_io import run_one
from chronaxis.fast.run import run_prepared


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT/'Docs/Current/examples'


class FastFileTests(unittest.TestCase):
    """每次测试只创建本次文件；异常时检查先前成功结果仍然可读。"""

    def setUp(self):
        self.area = TemporaryDirectory(dir=ROOT/'work',prefix='hpc-files-')
        self.addCleanup(self.area.cleanup)
        self.root = Path(self.area.name)
        self.dbc = self.root/'test.dbc'
        self.dbc.write_text((EXAMPLES/'data/power.dbc').read_text().replace('BO_ 256 ', 'BO_ 0 '))
        self.spec = dict(dbc=str(self.dbc),channel=1,domain_ns=None,
                         metrics=[dict(name='energy',frame_id=0,is_extended=False,is_fd=False,
                                       unit='J',expr='power * period',parameters={'period':.1},
                                       signals={'power':dict(signal='Power',dtype='float64',scale=1,offset=0)})])

    def blf(self, name, frames):
        """写实际 BLF。参数为逐帧覆盖字段；所有未覆盖帧各贡献 400 J。"""
        path = self.root/name
        with can.BLFWriter(str(path)) as writer:
            for overrides in frames:
                fields = dict(channel=0,timestamp=1.,arbitration_id=0,is_extended_id=False,data=b'\xa0\x0f')
                writer.on_message_received(can.Message(**(fields|overrides)))
        return dict(self.spec,path=str(path))

    def test_same_identity_and_same_time(self):
        rows,_ = run_one(self.blf('bus.blf',[{},dict(channel=1),dict(is_extended_id=True),{}]))
        self.assertEqual(rows[0]['value'],800.)
        rows,_ = run_one(self.blf('another.blf',[{}]))
        self.assertEqual(rows[0]['value'],400.)
        path = self.root/'bus.asc'
        path.write_text((EXAMPLES/'data/message-clean.asc').read_text().replace(' 100 Rx',' 000 Rx'))
        rows,_ = run_one(dict(self.spec,path=str(path),domain_ns=[0,10**9]))
        self.assertEqual(rows[0]['value'],800.)

    def test_public_baseline_module_remains_executable_without_vendor(self):
        """实际模块CLI处理两条400J报文，基准入口不依赖已退出的旧源码副本。"""
        import os
        import subprocess
        import sys
        config=self.root/'baseline.json'
        spec=self.blf('baseline.blf',[{},{}]);spec['table_format']='jsonl'
        config.write_text(json.dumps(spec),encoding='utf8')
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
        completed=subprocess.run([sys.executable,'-X','utf8','-B','-m','chronaxis.fast.baseline',
            '--config',str(config),'--output',str(self.root/'baseline-output')],
            cwd=self.root,env=env,text=True,encoding='utf8',capture_output=True,timeout=30)
        self.assertEqual(completed.returncode,0,completed.stderr)
        manifest=Path(json.loads(completed.stdout)['manifest_path'])
        record=json.loads(manifest.read_text(encoding='utf8'))
        result=manifest.parent/record['outputs'][0]['name']
        self.assertEqual(json.loads(result.read_text(encoding='utf8'))['value'],800.)
        self.assertEqual(record['status'],'completed')

    def test_failure_does_not_publish_partial_result(self):
        root = self.root/'out'
        manifest = run_prepared(self.blf('good.blf',[{}]),root,engine='chrginfo_corrected')
        old = {p:p.read_bytes() for p in root.iterdir()}
        with self.assertRaisesRegex(ValueError,'第 2 条记录'):
            run_prepared(self.blf('bad.blf',[{},dict(data=b'\01')]),root,engine='chrginfo_corrected')
        self.assertEqual(old,{p:p.read_bytes() for p in root.iterdir()})
        self.assertEqual(json.loads(manifest.read_bytes())['status'],'completed')

    def test_asc_order_uses_only_selected_data_frame_identity(self):
        """无关通道、扩展帧、远程帧或错误帧不参与所选数据的时序校验。"""
        path = self.root/'channels.asc'
        header = 'date Mon Jan 01 00:00:00.000 2024\nbase hex timestamps absolute\ninternal events logged\n'
        first = '0.500000 1 0 Rx d 2 A0 0F\n'
        spec = dict(self.spec, path=str(path), domain_ns=[0,10**9])
        for other in ('2 0 Rx d 2 A0 0F', '1 0x Rx d 2 A0 0F', '1 0 Rx r 2', '1 ErrorFrame'):
            with self.subTest(other=other):
                path.write_text(header + first + '0.100000 ' + other + '\n', encoding='ascii')
                rows, _ = run_one(spec)
                self.assertEqual(rows[0]['value'],400.)
        path.write_text(header + first + '0.100000 1 0 Rx d 2 A0 0F\n', encoding='ascii')
        with self.assertRaisesRegex(ValueError,'时间回退'):
            run_one(spec)

    def test_public_example_and_repeated_run(self):
        paths = [run(EXAMPLES/'message-minimal.yaml',self.root/'out') for _ in range(2)]
        self.assertNotEqual(*paths)
        for path in paths:
            report = json.loads(path.read_bytes())
            with (path.parent/report['outputs'][0]['name']).open(encoding='utf8') as stream:
                row, = csv.DictReader(stream)
                self.assertEqual((row['计算项'],float(row['结果']),row['单位']),('energy',800.,'J'))

    def test_public_power_time_and_energy_contributions(self):
        """公开入口区分功率乘时间与已有能量直接相加，ASC和BLF均得到1000J。

        参数: 无。返回: None。异常: 断言失败、配置或读写失败。
        每个输入只含两条同刻目标报文。功率为4000/6000W时各乘0.1s；
        已有能量为400/600J时不声明公式参数。合成输入和结果只写本次临时目录。
        """
        template = EXAMPLES/'fast/data/power.dbc'
        header = 'date Mon Jan 01 00:00:00.000 2024\nbase hex timestamps absolute\ninternal events logged\n'
        for mode, signal_name, unit, values in (
            ('power', 'Power', 'W', (4000, 6000)),
            ('energy_sample', 'Energy', 'J', (400, 600)),
        ):
            # DBC定义与原始整数值共同表达测试单位；不会改写教学样例。
            dbc = self.root/(mode+'.dbc')
            dbc.write_text(template.read_text(encoding='utf8').replace(' SG_ Power ', ' SG_ '+signal_name+' ')
                           .replace('"W"', '"'+unit+'"'), encoding='utf8')
            for suffix in ('asc', 'blf'):
                with self.subTest(mode=mode, format=suffix):
                    source = self.root/(mode+'.'+suffix)
                    if suffix == 'asc':
                        records = ['0.000000 1 100 Rx d 2 '+value.to_bytes(2,'little').hex(' ').upper()+'\n'
                                   for value in values]
                        source.write_text(header+''.join(records), encoding='ascii')
                    else:
                        with can.BLFWriter(str(source)) as writer:
                            for value in values:
                                writer.on_message_received(can.Message(channel=0,timestamp=1.,arbitration_id=0x100,
                                                                       is_extended_id=False,data=value.to_bytes(2,'little')))
                    raw = load_configuration(EXAMPLES/'fast/analysis.yaml').data
                    raw['sources'][0].update(paths=str(source),dbc_by_channel={'1':str(dbc)})
                    raw['signals']=[dict(name=mode,field={'frame_id':'0x100','signal':signal_name},
                                         dtype='float64',valid_for='1s')]
                    calculation=raw['message_calculations'][0]
                    calculation.update(expr=mode,unit='J')
                    calculation.pop('parameters')
                    if mode == 'power':
                        # dt仅为本例参数名；已有能量分支完全省略parameters。
                        calculation.update(expr='power * dt',parameters={'dt':{'value':.1,'unit':'s'}})
                    config=self.root/(mode+'-'+suffix+'.json')
                    config.write_text(json.dumps(raw),encoding='utf8')
                    manifest=run(config,self.root/(mode+'-'+suffix+'-out'))
                    report=json.loads(manifest.read_bytes())
                    with (manifest.parent/report['outputs'][0]['name']).open(encoding='utf8',newline='') as stream:
                        row,=csv.DictReader(stream)
                    self.assertEqual((float(row['结果']),row['单位'],row['状态']),(1000.,'J','完整'))
