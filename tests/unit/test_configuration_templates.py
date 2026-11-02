"""真实执行随包场景，以手算常数验收；两个版本共用同一输入但不共用计算预期。"""
from dataclasses import asdict, replace
import csv
import json
from pathlib import Path
import tempfile
import unittest

from chronaxis import AnalysisRunner, load_analysis_plan, load_batch_plan, run_batch
from chronaxis.configuration import load_configuration
from chronaxis.configuration.template_catalog import available_templates, template_files, _relative_path
from chronaxis.migration import load_legacy_ini
import test_configuration_schema as schema_tests


class ConfigurationTemplateTests(unittest.TestCase):
    """输入、运行和发布均在独占work目录；不更改模板资源或历史数据。"""

    def setUp(self):
        """建立独立测试目录。参数: 无。返回: None。异常: IO错误。"""
        self.root=Path(tempfile.mkdtemp(prefix='configuration-templates-',dir='work')).resolve()

    def materialize(self, template, style):
        """按真实包清单写测试副本。参数: 描述及风格。返回: 入口路径。异常: IO错误。"""
        folder=self.root/template.name/style;folder.mkdir(parents=True)
        for name,content in template_files(template.name,style=style):
            path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        return folder/template.entrypoint

    def collect(self, plan, folder):
        """执行、取有限摘要及发布。参数: 已校验计划和独占目录。返回: 四张摘要表。异常: 执行/断言。"""
        result=AnalysisRunner().run(plan,work_dir=folder/'work')
        try:
            output={}
            for table in ('calculations','events','segments','sequences'):
                cursor=getattr(result,'iter_'+table)()
                try:output[table]=[asdict(row) for row in cursor]
                finally:cursor.close()
            if plan.outputs.signal_csv is not None or plan.outputs.can_frames is not None:
                result.write(folder/'output')
            return output
        finally:
            result.close();self.assertEqual(result.spool.budget.ram_bytes,0)

    def check_expected(self, name, rows):
        """使用独立手算及时间边界断言。参数: 场景名、公开行。返回: None。异常: 断言。"""
        values={row['calculation_id']:row['value'] for row in rows['calculations']}
        events={row['rule_id']:(row['start_ns']/1e9,None if row['end_ns'] is None else row['end_ns']/1e9)
            for row in rows['events']}
        if name in ('signal-csv','signal-export','ini-mapping'):
            self.assertEqual(values['energy'],38)
        if name=='signal-csv':
            self.assertEqual(values['sample_average'],6)
            self.assertAlmostEqual(values['time_average'],38/6)
        if name=='charge-session':
            self.assertEqual(events['charging_activity'],(0,2))
            self.assertAlmostEqual(values['charging_energy'],8000/3600)
            self.assertAlmostEqual(values['charging_charge'],20/3600)
        elif name=='fault-window':
            self.assertEqual(events['fault_alarm'][0],2)
            self.assertEqual([(r['start_ns']/1e9,r['end_ns']/1e9) for r in rows['segments']],[(1,4)])
        elif name=='command-response':
            self.assertEqual([(r['status'],r['decided_ns']/1e9,r['delay_ns']) for r in rows['sequences']],
                [('matched',2,1000000000),('no_response',6,None)])
        elif name=='threshold':
            self.assertEqual(events['hot_activity'],(0,9));self.assertEqual(values['hot_duration'],9)
        elif name=='stability':
            self.assertEqual(events['hysteresis_alarm'],(1,4));self.assertEqual(events['debounced_alarm'],(2,4))
            self.assertAlmostEqual(values['hysteresis_alarm_average'],247/3)
            self.assertEqual(values['debounced_alarm_average'],81)
        elif name in ('can-blf','can-asc','raw-can-csv','can-export'):
            self.assertEqual(values['voltage_area'],13)
        if name=='ini-mapping':self.assertEqual(events['trigger_1'],(1,6))

    def test_minimal_templates_only_keep_needed_declarations(self):
        """防止重新加入身份副本、默认时间范围和可由DBC推导的声明。"""
        templates=available_templates()
        self.assertEqual([item.name for item in templates[:2]],['can-asc','can-blf'])
        for template in templates:
            document=load_configuration(self.materialize(template,'minimal')).data
            if template.config_type=='batch':
                self.assertTrue(all(set(job)=={'plan'} for job in document['jobs']))
                continue
            plan=document['analysis'] if template.config_type=='mapping' else document
            self.assertEqual(set(plan['dataset']),{'name'},template.name)
            self.assertEqual(len(plan['sources']),1,template.name)
            source=plan['sources'][0]
            self.assertNotIn('name',source,template.name)
            self.assertNotIn('clock',source.get('time',{}),template.name)
            if template.name not in ('signal-csv','raw-can-csv'):
                self.assertEqual(Path(source['path']).suffix.lower(),'.blf' if template.name=='can-blf' else '.asc')
                self.assertNotIn('source_type',source)
            for signal in plan['signals']:
                self.assertNotIn('source',signal,template.name)
                if isinstance(signal['field'],dict):
                    self.assertFalse({'dtype','unit','valid_for','period'} & set(signal),template.name)
            if template.name in ('can-export','signal-export'):
                self.assertEqual(plan.get('metadata'),{'device_label':'home'})
            else:self.assertNotIn('metadata',plan,template.name)

    def test_catalog_styles_and_schema_are_consistent(self):
        """十三场景两种风格内容相同，分析/批量/映射均通过独立标准规范。参数: 无。返回: None。异常: 断言。"""
        templates=available_templates();self.assertEqual(len(templates),13)
        self.assertEqual(len({t.name for t in templates}),13)
        schema_tests.ConfigurationSchemaTests.setUpClass()
        schemas={'analysis':'analysis.schema.json','batch':'batch-v1.schema.json','mapping':'legacy-import-v1.schema.json'}
        for template in templates:
            with self.subTest(scene=template.name):
                paths=[self.materialize(template,style) for style in ('minimal','annotated')]
                documents=[load_configuration(path).data for path in paths]
                self.assertEqual(*documents)
                schema_tests.ConfigurationSchemaTests.validators[schemas[template.config_type]].validate(documents[0])
                for path in paths:
                    if template.config_type=='analysis':load_analysis_plan(path)
                    elif template.config_type=='batch':load_batch_plan(path)
                    else:self.assertIsNotNone(load_legacy_ini(path.parent/'source.ini',path,mode='sclicer_single').plan)
        for path in ('../escape','/root','C:/file','a\\b',''):
            with self.assertRaises(ValueError):_relative_path(path)
        with self.assertRaises(ValueError):template_files('../other')
        with self.assertRaises(ValueError):template_files('signal-csv',style='unknown')

    def test_all_analysis_templates_run_with_both_backends_and_hand_results(self):
        """实际读取三种CAN及CSV，两个后端核事件、统计、序列和导出。参数: 无。返回: None。异常: 断言/执行错。"""
        for template in available_templates():
            if template.config_type!='analysis':continue
            observed=[]
            for style,backend in (('minimal','reference'),('annotated','numpy')):
                with self.subTest(scene=template.name,style=style):
                    path=self.materialize(template,style);plan=load_analysis_plan(path)
                    plan=replace(plan,execution=replace(plan.execution,backend=backend))
                    rows=self.collect(plan,path.parent);self.check_expected(template.name,rows);observed.append(rows)
                    if template.name=='signal-export':
                        index=[json.loads(s) for s in (path.parent/'output/exports.jsonl').read_text(encoding='utf-8').splitlines()]
                        grid=path.parent/'output/exports'/index[0]['directory']/'resampled.csv'
                        with grid.open(encoding='utf-8',newline='') as stream:points=list(csv.DictReader(stream))
                        self.assertEqual([int(r['time_ns'])/1e9 for r in points],[i/2 for i in range(12)])
                        # 导出仅使用[0,6)内样本；6秒原样本在范围外，末三格缺右邻点不能外推。
                        self.assertEqual([float(r['value']) for r in points[:9]],[2,3,4,5,6,7,8,9,10])
                        self.assertEqual([(r['value'],r['reason']) for r in points[9:]],[('','missing_right')]*3)
                    if template.name=='can-export':
                        import can
                        index=[json.loads(s) for s in (path.parent/'output/exports.jsonl').read_text(encoding='utf-8').splitlines()]
                        frames=path.parent/'output/exports'/index[0]['directory']/'frames.asc'
                        with can.ASCReader(str(frames)) as reader:messages=list(reader)
                        self.assertEqual([bytes(m.data) for m in messages],[b'\x01\x05',b'\x03\x06',b'\x01\x07'])
            if len(observed)==2:self.assertEqual(*observed)

    def test_batch_and_ini_templates_execute_without_changing_source(self):
        """批量两项均38J，INI原字节不变且事件按[1,6)关闭。参数: 无。返回: None。异常: 断言。"""
        templates={t.name:t for t in available_templates()}
        batch=self.materialize(templates['batch'],'annotated');output=batch.parent/'output'
        report=run_batch(load_batch_plan(batch),output,device_label='home')
        try:self.assertEqual(json.loads((output/'batch_report.json').read_text(encoding='utf-8'))['counts'],
            dict(completed=2,failed=0,cancelled=0))
        finally:report.close()
        tables=list(output.rglob('会话结果.csv'));self.assertEqual(len(tables),2)
        for table in tables:
            with table.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(float(rows[0]['energy（J）']),38)
        path=self.materialize(templates['ini-mapping'],'annotated');ini=path.parent/'source.ini';before=ini.read_bytes()
        imported=load_legacy_ini(ini,path,mode='sclicer_single',device_label='home')
        self.assertIsNotNone(imported.plan,imported.report.to_dict())
        self.check_expected('ini-mapping',self.collect(imported.plan,path.parent))
        self.assertEqual(ini.read_bytes(),before)


if __name__=='__main__':unittest.main()
