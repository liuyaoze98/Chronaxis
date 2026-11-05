"""初始化从真实CLI到可运行产物，覆盖独占写入和失败清理。"""
import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chronaxis.configuration.initialization import initialize_configuration
from chronaxis.configuration.template_catalog import available_templates,template_files


class ConfigurationInitTests(unittest.TestCase):
    """每例独立目录，已有内容和未知场景不应发生任何写入。"""

    def setUp(self):
        """建立work目录。参数: 无。返回: None。异常: IO。"""
        self.root=Path(tempfile.mkdtemp(prefix='configuration-init-',dir='work')).resolve()

    def command(self,*args):
        """实际CLI进程。参数: 参数。返回: CompletedProcess。异常: 超时。"""
        return subprocess.run([sys.executable,'-B','-m','chronaxis',*map(str,args)],cwd=self.root,
            env=os.environ.copy(),capture_output=True,text=True,encoding='utf-8',timeout=60)

    def test_every_style_materializes_exact_bundle(self):
        """26套内容逐字节对包，已有目录拒绝且不改变内容。参数: 无。返回: None。异常: 断言。"""
        for template in available_templates():
            for style in ('minimal','annotated'):
                target=self.root/(template.name+'-'+style)
                entry=initialize_configuration(template.name,target,style=style)
                self.assertEqual(entry,target/template.entrypoint)
                expected=dict(template_files(template.name,style=style))
                self.assertEqual({p.relative_to(target).as_posix():p.read_bytes() for p in target.rglob('*') if p.is_file()},expected)
                with self.assertRaises(FileExistsError):initialize_configuration(template.name,target)
                self.assertEqual(entry.read_bytes(),expected[template.entrypoint])
        with self.assertRaises(ValueError):initialize_configuration('unknown',self.root/'unknown')
        self.assertFalse((self.root/'unknown').exists())
        empty=self.root/'empty';empty.mkdir()
        with self.assertRaises(FileExistsError):initialize_configuration('signal-csv',empty)
        self.assertEqual(list(empty.iterdir()),[])

    def test_mid_write_failure_and_cancel_remove_only_owned_files(self):
        """第一份数据已写后主入口失败或取消，清理自有产物，父目录用户文件保留。参数: 无。返回: None。异常: 断言。"""
        sentinel=self.root/'user.txt';sentinel.write_text('keep',encoding='utf-8');original=Path.open
        for error in (OSError('synthetic write failure'),KeyboardInterrupt()):
            target=self.root/'partial'
            def fail(path,*args,**kwargs):
                """在入口打开处注入故障。参数: Path及打开参数。返回: 原FD。异常: 指定故障。"""
                if path==target/'plan.yaml':raise error
                return original(path,*args,**kwargs)
            with patch.object(Path,'open',fail):
                with self.assertRaises(type(error)):initialize_configuration('signal-csv',target)
            self.assertFalse(target.exists());self.assertEqual(sentinel.read_text(encoding='utf-8'),'keep')

    def test_cli_lists_generates_validates_and_runs(self):
        """实际默认注释模板生成后通过校验并积分13V·s；错误码明确。参数: 无。返回: None。异常: 断言。"""
        listed=self.command('config','init','--list');self.assertEqual(listed.returncode,0,listed.stderr)
        for template in available_templates():self.assertIn(template.name,listed.stdout)
        target=self.root/'example'
        generated=self.command('config','init','can-asc','--output',target)
        self.assertEqual(generated.returncode,0,generated.stderr)
        checked=self.command('validate',target/'plan.yaml');self.assertEqual(checked.returncode,0,checked.stderr)
        completed=self.command('run',target/'plan.yaml','--output',self.root/'result')
        self.assertEqual(completed.returncode,0,completed.stderr)
        with next((self.root/'result').glob('会话结果_*.csv')).open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        self.assertEqual(float(rows[0]['voltage_area（V*s）']),13)
        self.assertEqual(self.command('config','init','can-asc','--output',target).returncode,1)
        self.assertEqual(self.command('config','init','missing','--output',self.root/'missing').returncode,2)
        self.assertEqual(self.command('config','init','can-asc').returncode,2)
        self.assertEqual(self.command('config','init','can-asc','--list').returncode,2)


if __name__=='__main__':unittest.main()
