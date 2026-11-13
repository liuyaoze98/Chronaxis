"""独占持有一份BLF输出文件，委托既有python-can格式写入，不重写BLF编码。

写入器与底层文件属于同一owner；文件头构造、压缩或最终头更新失败时关闭实际句柄。
第三方stop至多调用一次，关闭重试仅处理尚未关闭的文件，不重复压缩或重写完成头。
"""
from pathlib import Path
from .budget import _cleanup_owner


class BLFWrite:
    """管理一个新的BLF文件及其python-can writer，不接收来源路径或DBC。"""

    def __init__(self,path):
        """独占创建文件并安装writer。参数: 新.blf路径。返回: owner。异常: 原创建/文件头错误。

        传入文件对象由python-can的stop关闭；本对象只在第三方未完成关闭时收尾同一句柄。
        构造失败仍保留blf_write_cleanup_owner，不借重新打开文件修补失败。
        """
        self.path=Path(path)
        self._file=self._writer=None
        self._closed=self._stop_attempted=self._stop_succeeded=False
        try:
            if self.path.suffix.lower()!='.blf':raise ValueError('BLF写入需要.blf路径')
            from ..can_dependencies import import_can_dependency
            can=import_can_dependency('can')
            self._file=self.path.open('xb')
            self._writer=can.BLFWriter(self._file)
        except BaseException as error:
            _cleanup_owner(self,error,'blf_write_cleanup_owner','BLF写入器构造')
            raise

    @property
    def closed(self):
        """查询实际关闭状态。

        参数: 无。返回: bool，不表示失败文件可发布。异常: 无。
        """
        return self._closed

    def write(self,message):
        """写入当前原帧一次。

        参数: message为当前can.Message。返回: None。异常: 原写入错误或已结束时RuntimeError。
        不重试写入，避免重复添加帧。
        """
        if self._closed or self._stop_attempted:raise RuntimeError('BLF写入器已结束')
        self._writer.on_message_received(message)

    def finish(self):
        """完成压缩与最终文件头。

        参数: 无。返回: None，仅真实stop成功可正常返回。
        异常: 原收尾错误；已经失败的最终写入不能重试，返回RuntimeError。
        """
        if self._closed and self._stop_succeeded:return
        if self._stop_attempted:raise RuntimeError('BLF最终写入已经尝试，失败不能重试')
        self.close()
        if not self._stop_succeeded:raise RuntimeError('BLF最终写入未完成')

    def close(self):
        """关闭同一实际文件，第三方stop最多一次。

        参数: 无。返回: None，重复关闭安全。
        异常: 保留原收尾错误；实际文件仍未关闭时附可重试owner，其他错误加入notes。
        """
        if self._closed:return
        primary=None
        if self._writer is not None and not self._stop_attempted:
            self._stop_attempted=True
            try:
                self._writer.stop()
                self._stop_succeeded=True
            except BaseException as error:
                primary=error
        try:
            if self._file is not None and not self._file.closed:self._file.close()
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('BLF实际文件关闭附加失败: '+type(error).__name__)
        if self._file is None or self._file.closed:
            self._file=self._writer=None
            self._closed=True
        if primary is not None:
            if not self._closed:setattr(primary,'blf_write_cleanup_owner',self)
            raise primary
