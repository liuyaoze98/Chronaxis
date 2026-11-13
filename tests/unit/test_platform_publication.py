"""实际平台上核单文件/目录的正向及回滚不覆盖，未知对象不清理。"""
from pathlib import Path
import os
import unittest
from unittest.mock import patch
from workspace_fixtures import TemporaryDirectory
from chronaxis.results.platform_files import move_no_replace
from chronaxis.results.publication import PublicationNames


class PlatformPublicationTests(unittest.TestCase):
    """源和目标均在本例独占目录，禁止依赖POSIX普通rename的覆盖行为。"""

    def test_files_directories_and_reverse_conflicts(self):
        """真实正向移动后模拟回滚源被占用；双方内容必须保留。"""
        for directory in (False,True):
            with self.subTest(directory=directory),TemporaryDirectory(prefix="platform-move-") as area:
                root=Path(area);source=root/"source";target=root/"target"
                if directory:source.mkdir();(source/"payload").write_text("ours")
                else:source.write_text("ours")
                move_no_replace(source,target);self.assertFalse(source.exists())
                if directory:source.mkdir();(source/"external").write_text("external")
                else:source.write_text("external")
                with self.assertRaises(FileExistsError):move_no_replace(target,source)
                self.assertEqual((target/"payload" if directory else target).read_text(),"ours")
                self.assertEqual((source/"external" if directory else source).read_text(),"external")

    def test_existing_target_types_are_never_overwritten(self):
        """已有普通文件、空/非空目录与悬空链接均由真实原语拒绝。"""
        for kind in ("file","empty","directory","link"):
            with self.subTest(kind=kind),TemporaryDirectory(prefix="platform-target-") as area:
                root=Path(area);source=root/"source";source.write_text("ours");target=root/"target"
                if kind=="file":target.write_text("external")
                elif kind in ("empty","directory"):
                    target.mkdir()
                    if kind=="directory":(target/"external").write_text("external")
                else:
                    try:target.symlink_to(root/"missing")
                    except OSError as error:
                        if getattr(error,"winerror",None)==1314:continue
                        raise
                with self.assertRaises(FileExistsError):move_no_replace(source,target)
                self.assertEqual(source.read_text(),"ours");self.assertTrue(os.path.lexists(target))

    def test_rollback_conflict_preserves_external_source(self):
        """中途失败时原临时名称已被别人占用，回滚不能覆盖它。"""
        with TemporaryDirectory(prefix="platform-rollback-") as area:
            root=Path(area);temporary=root/"temp";temporary.mkdir();(temporary/"data").write_text("ours");(temporary/"manifest").write_text("done")
            names=PublicationNames(root/"output",("data","manifest"));count=0
            def install(source,target):
                """首项真实移动后占用旧名，第二项注入原错误。返回None或OSError。"""
                nonlocal count
                count+=1
                if count==2:raise OSError("planned failure")
                move_no_replace(source,target);source.write_text("external")
            with self.assertRaisesRegex(OSError,"planned failure") as caught:names.publish(temporary,"manifest",install)
            self.assertEqual((temporary/"data").read_text(),"external")
            self.assertEqual((names.root/names.names["data"]).read_text(),"ours")
            self.assertTrue(any("回滚" in note for note in caught.exception.__notes__))

    @unittest.skipUnless(os.name!="nt","Linux目录fd所有权专项")
    def test_close_error_does_not_close_reused_descriptor(self):
        """Linux close释放编号后仍可报错；再次close不得伤到已复用的新文件。"""
        from chronaxis.results import platform_files
        with TemporaryDirectory(prefix="platform-fd-") as area:
            root=Path(area);spare=root/"spare";spare.write_text("other")
            owner=platform_files._DirectoryHandles();owner.open("source",root);owner.open("target",root)
            close=os.close;reused=[]
            def close_then_error(descriptor):
                """先真实释放再复用编号并报错，模拟Linux明示的关闭后错误。返回None或注入OSError。"""
                close(descriptor)
                if not reused:
                    new=os.open(spare,os.O_RDONLY)
                    if new!=descriptor:os.dup2(new,descriptor);close(new)
                    reused.append(descriptor);raise OSError("close failed after release")
            try:
                with patch.object(platform_files.os,"close",close_then_error):
                    with self.assertRaisesRegex(OSError,"after release"):owner.close()
                self.assertTrue(owner.closed);owner.close();os.fstat(reused[0])
            finally:
                if reused:close(reused[0])

    def test_parent_replacement_is_rejected_before_publish(self):
        """已登记结果根被替换时拒绝移动；新根的外部内容保留。"""
        with TemporaryDirectory(prefix="platform-parent-") as area:
            root=Path(area);temporary=root/"temp";temporary.mkdir();(temporary/"manifest").write_text("done")
            names=PublicationNames(root/"output",("manifest",));old=root/"old";names.root.rename(old);names.root.mkdir();(names.root/"external").write_text("external")
            with self.assertRaisesRegex(ValueError,"身份"):names.publish(temporary,"manifest")
            self.assertTrue((temporary/"manifest").exists());self.assertEqual((names.root/"external").read_text(),"external")
            names.close()

    @unittest.skipUnless(os.name!='nt','Linux不覆盖原语失败专项')
    def test_unsupported_primitive_preserves_files_and_closes_fds(self):
        """缺少原语或文件系统拒绝时明确失败，不退回可覆盖rename且不遗留目录fd。"""
        import ctypes
        import errno
        from chronaxis.results import platform_files
        with TemporaryDirectory(prefix='platform-unsupported-') as area:
            root=Path(area);source=root/'source';source.write_text('ours');target=root/'target'
            missing=NotImplementedError('renameat2 missing')
            with patch.object(platform_files,'_linux_rename',side_effect=missing):
                with self.assertRaises(NotImplementedError) as caught:
                    move_no_replace(source,target)
            self.assertIs(caught.exception,missing)
            self.assertEqual(source.read_text(),'ours')
            for code in (errno.ENOSYS,errno.EOPNOTSUPP,errno.EINVAL):
                with self.subTest(errno=code):
                    opened=[]
                    original_open=os.open
                    def observe_open(*args,**kwargs):
                        """记录本次真实打开的目录描述符；返回原fd，原异常继续向外。"""
                        descriptor=original_open(*args,**kwargs);opened.append(descriptor);return descriptor
                    def unavailable(*args):
                        """模拟内核返回指定errno；不移动任何文件。"""
                        ctypes.set_errno(code);return -1
                    expected=OSError if code==errno.EINVAL else NotImplementedError
                    with patch.object(platform_files,'_linux_rename',return_value=unavailable),patch.object(
                            platform_files.os,'open',observe_open),patch.object(
                            platform_files.os,'rename',side_effect=AssertionError('unsafe fallback')):
                        with self.assertRaises(expected):move_no_replace(source,target)
                    self.assertEqual(source.read_text(),'ours');self.assertFalse(target.exists())
                    self.assertEqual(len(opened),2)
                    for descriptor in opened:
                        with self.assertRaises(OSError) as caught:os.fstat(descriptor)
                        self.assertEqual(caught.exception.errno,errno.EBADF)

    @unittest.skipUnless(os.name!='nt','Linux真实rename后fd关闭失败专项')
    def test_manifest_rollback_completed_before_fd_close_error(self):
        """清单实际撤回后close报错，不能声称仍已发布；数据继续退回且保留主错。"""
        from chronaxis.results import platform_files
        for error_type in (OSError,FileNotFoundError):
            with self.subTest(error_type=error_type),TemporaryDirectory(prefix='platform-after-move-') as area:
                root=Path(area);temporary=root/'temp';temporary.mkdir()
                (temporary/'data').write_text('ours');(temporary/'manifest').write_text('done')
                names=PublicationNames(root/'output',('data','manifest'))
                primary=OSError('release lock failed')
                close_names=PublicationNames.close
                close_directories=platform_files._DirectoryHandles.close
                release_attempts=[];failed_fds=[]

                def release_then_fail(owner):
                    """第一次实际释放本例命名锁后报错，以触发已发布清单的真实回滚。"""
                    close_names(owner)
                    if owner is names and not release_attempts:
                        release_attempts.append(True)
                        raise primary

                def close_after_real_rollback(owner):
                    """清单已真实移动回temporary时，真实关闭目录fd后报告一次错误。"""
                    moved=(temporary/'manifest').exists() and not (names.root/names.names['manifest']).exists()
                    descriptors=(owner.source,owner.target)
                    close_directories(owner)
                    if release_attempts and moved and not failed_fds:
                        failed_fds.extend(descriptors)
                        raise error_type('directory close failed after rollback')

                with patch.object(PublicationNames,'close',release_then_fail),patch.object(
                        platform_files._DirectoryHandles,'close',close_after_real_rollback):
                    with self.assertRaises(OSError) as caught:
                        names.publish(temporary,'manifest')
                self.assertIs(caught.exception,primary)
                self.assertFalse(names.completed)
                self.assertEqual((temporary/'manifest').read_text(),'done')
                self.assertEqual((temporary/'data').read_text(),'ours')
                self.assertFalse(any(names.root.iterdir()))
                self.assertTrue(failed_fds)
                self.assertTrue(any('已撤回' in note for note in primary.__notes__))
                for descriptor in failed_fds:
                    with self.assertRaises(OSError):os.fstat(descriptor)

if __name__=="__main__":unittest.main()
