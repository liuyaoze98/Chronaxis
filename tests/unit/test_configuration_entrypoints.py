"""从实际YAML/JSON文件走公开API、CLI和批量隔离，证明共享语法已接三个入口。"""
from copy import deepcopy
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ruamel.yaml import YAML
from chronaxis import AnalysisRunner, load_analysis_plan, load_batch_plan, run_batch, PlanValidationError
from chronaxis.migration import load_legacy_ini
import test_legacy_import_sclicer as migration_fixture


class ConfigurationEntrypointTests(unittest.TestCase):
    """每例使用独占work；数据源/计划/映射各自相对路径不可互换。"""

    def setUp(self):
        """建立三行真实CSV及独立配置目录。参数: 无。返回: None。异常: 实际IO错误。"""
        self.root=Path(tempfile.mkdtemp(prefix='yaml-entrypoints-',dir='work')).resolve()
        self.folder=self.root/'configuration';self.folder.mkdir()
        (self.folder/'input.csv').write_text('t,p\n0,2\n1,4\n2,100\n',encoding='utf-8')
        self.config=dict(config_version=3,dataset=dict(name='demo',entity='object',session='session',
            domain=dict(start='0s',end='2s')),sources=[dict(name='input',source_type='signal_csv',
            path='input.csv',time_column='t',time=dict(time_type='relative',unit='s',clock='common'))],
            signals=[dict(name='power',source='input',field='p',dtype='float64',unit='W',valid_for='2s')],
            calculations=[dict(name='energy',scope='session',operation='integral',expr='power')],
            execution=dict(backend='reference',batch_rows=1),metadata=dict(device_label='home'))

    def write(self,name,data):
        """用独立JSON或标准YAML输出夹具。参数: 文件名/原生值。返回: 路径。异常: 实际IO错误。"""
        path=self.folder/name
        if path.suffix=='.json':path.write_text(json.dumps(data),encoding='utf-8')
        else:
            yaml=YAML(typ='safe',pure=True);yaml.version=(1,2)
            with path.open('w',encoding='utf-8') as stream:yaml.dump(data,stream)
        return path

    def command(self,*arguments):
        """从不同cwd实际运行模块CLI。参数: 命令参数。返回: CompletedProcess。异常: 超时/IO。"""
        return subprocess.run([sys.executable,'-B','-m','chronaxis',*map(str,arguments)],cwd=self.root,
            env=dict(os.environ,CHRONAXIS_DEVICE_LABEL='home'),capture_output=True,text=True,encoding='utf-8',timeout=60)

    def test_public_analysis_api_and_cli_have_equal_current_results(self):
        """两格式同一静态计划，实际积分6J；CLI validate/explain/run都从文件父目录定位CSV。参数: 无。返回: None。异常: 断言。"""
        paths=[self.write('analysis.json',self.config),self.write('analysis.yaml',self.config)]
        plans=[load_analysis_plan(path) for path in paths]
        self.assertEqual(plans[0],plans[1])
        observed=[]
        for index,plan in enumerate(plans):
            result=AnalysisRunner().run(plan,work_dir=self.root/f'api-{index}')
            try:
                cursor=result.iter_calculations()
                try:rows=tuple(cursor)
                finally:cursor.close()
                self.assertEqual(len(rows),1)
                self.assertEqual((rows[0].value,rows[0].unit,rows[0].status),(6.0,'J','complete'))
                observed.append(rows)
            finally:result.close()
            self.assertEqual(result.spool.budget.ram_bytes,0)
        self.assertEqual(observed[0],observed[1])
        for action in ('validate','explain'):
            values=[]
            for path in paths:
                completed=self.command(action,path,'--format','json')
                self.assertEqual(completed.returncode,0,completed.stderr)
                values.append(json.loads(completed.stdout))
            self.assertEqual(values[0],values[1])
        output=self.root/'cli-published'
        completed=self.command('run',paths[1],'--output',output)
        self.assertEqual(completed.returncode,0,completed.stderr)
        with (output/'会话结果.csv').open(encoding='utf-8-sig',newline='') as stream:
            published=list(csv.DictReader(stream))
        self.assertEqual(len(published),1)
        self.assertEqual(float(published[0]['energy（J）']),6.0)

    def test_static_yaml_only_reads_the_selected_configuration(self):
        """不存在数据与DBC不妨碍静态加载；YAML语法定位保公共异常类型。参数: 无。返回: None。异常: 断言。"""
        config=deepcopy(self.config);config['sources'][0]['path']='missing.csv'
        path=self.write('unread.yml',config);opened=[];original=Path.open
        def observe(target,*args,**kwargs):
            """只允许指定配置的实际打开。参数: Path与打开参数。返回: FD。异常: 非配置I/O。"""
            self.assertEqual(target,path);opened.append(target);return original(target,*args,**kwargs)
        with patch.object(Path,'open',observe):load_analysis_plan(path)
        self.assertEqual(opened,[path])
        path.write_text('config_version: 3\nconfig_version: 3\n',encoding='utf-8')
        with self.assertRaises(PlanValidationError) as caught:load_analysis_plan(path)
        self.assertEqual(caught.exception.code,'duplicate_key')
        self.assertIn('第2行',str(caught.exception))
        completed=self.command('validate',path)
        self.assertEqual(completed.returncode,2,completed.stderr)
        for action in ('validate','explain','run'):
            args=(action,self.folder/'missing.yaml')
            if action=='run':args+=('--output',self.root/'never-created')
            completed=self.command(*args)
            self.assertEqual(completed.returncode,1,completed.stderr)

    def test_yaml_batch_is_lazy_and_bad_child_does_not_stop_other_tasks(self):
        """批量YAML不预读子计划，坏YAML任务失败而JSON/YAML有效任务均完成。参数: 无。返回: None。异常: 断言。"""
        self.write('good.yaml',self.config);self.write('other.json',self.config)
        (self.folder/'bad.yaml').write_text('config_version: [',encoding='utf-8')
        raw=dict(batch_version=1,process_count=1,fail_fast=False,jobs=[dict(name=name,plan=file) for name,file in
            (('bad','bad.yaml'),('good','good.yaml'),('other','other.json'))])
        path=self.write('batch.yml',raw)
        with patch('chronaxis.batch.runner.load_analysis_plan',side_effect=AssertionError('不能预读任务')):
            plan=load_batch_plan(path)
        self.assertEqual([job.plan.parent for job in plan.jobs],[self.folder]*3)
        output=self.root/'batch-output'
        report=run_batch(plan,output,device_label='home')
        try:
            document=json.loads((output/'batch_report.json').read_text(encoding='utf-8'))
            self.assertEqual(document['counts'],dict(completed=2,failed=1,cancelled=0))
        finally:report.close()
        completed=self.command('batch','run',path,'--output',self.root/'batch-cli')
        self.assertEqual(completed.returncode,1,completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['counts'],dict(completed=2,failed=1,cancelled=0))

    def test_ini_mapping_yaml_keeps_original_bytes_paths_and_issue_protocol(self):
        """INI原文不变，两格式映射同计划/身份；YAML错误仍返回迁移Issue及实际行列。参数: 无。返回: None。异常: 断言。"""
        ini=self.root/'source.ini';content=b'[TRIGGER_test]\r\nmode=single\r\nexpr=OBC_OpMod==2\r\n';ini.write_bytes(content)
        mapping=migration_fixture.mapping_fixture()
        paths=[self.write('mapping.json',mapping),self.write('mapping.yaml',mapping)]
        results=[load_legacy_ini(ini,path,mode='sclicer_single',device_label='home') for path in paths]
        for result in results:
            self.assertIsNotNone(result.plan,result.report.to_dict())
            self.assertEqual(result.original_ini,content)
            self.assertEqual(result.plan.sources[0].config.paths[0],self.folder/'missing/input.csv')
        self.assertEqual(results[0].plan,results[1].plan)
        self.assertEqual(results[0].report.mapping_identity,results[1].report.mapping_identity)
        output=self.root/'imported.json'
        completed=self.command('legacy','import',ini,'--mode','sclicer_single','--mapping',paths[1],'--output',output)
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(load_analysis_plan(output).identity,results[1].plan.identity)
        paths[1].write_text('analysis:\n  key: 1\n  key: 2\n',encoding='utf-8')
        failed=load_legacy_ini(ini,paths[1],mode='sclicer_single')
        self.assertIsNone(failed.plan)
        issue=failed.report.issues[-1]
        self.assertEqual((issue.code,issue.path,issue.line,issue.column),('duplicate_mapping_key','$.analysis.key',3,3))
        self.assertEqual(ini.read_bytes(),content)


if __name__=='__main__':
    unittest.main()
