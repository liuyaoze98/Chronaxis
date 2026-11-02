"""在新目标旁发布导入原文与报告，成功转换的计划最后才安装。

输入是LegacyImportResult和.json目标，可显式附INI/mapping源路径；输出固定
LegacyImportFiles。三个文件先写入同父UUID临时文件，flush及实际close成功后，
按原文、报告、计划顺序用Windows不覆盖rename安装。转换失败只安装前两件，
报告status仍表示转换结果，不能据此宣称分析已运行或数据已经验证。

目标、解析后的RefProjects边界和源路径冲突在创建目录前检查；安装仍以真实
no-replace操作防竞态，不依赖预先exists检查或os.replace。只声明已验证的
Windows文件安装语义，其他平台在写入前明确拒绝。目录本身不作跨文件原子
事务，已安装sidecar在后续失败时保留；计划是最后的提交点。

小owner仅持本次真实FD和已独占创建的三个UUID临时文件。失败不吞原取消、
MemoryError或I/O异常；清理副错附note，异常上的
legacy_import_publication_cleanup_owner.close()可重试关闭并移除自有临时文件。
不递归删除，不删除已发布sidecar、用户目标或原配置，也不配置日志或运行旧链。
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

from ..planning import AnalysisPlan
from .models import LegacyImportReport, LegacyImportResult


@dataclass(frozen=True)
class LegacyImportFiles:
    """保存词法绝对发布路径；plan为None时只有原文和失败转换报告。"""

    plan: Path | None
    original: Path
    report: Path


def _mapping_json(value):
    """仅展开计划固定MappingProxy，不反射任意对象或调用其序列化方法。

    参数: value为JSON编码器遇到的对象。返回: 原生dict副本。
    异常: TypeError为非MappingProxyType；MemoryError保持原生异常。
    """
    if type(value) is MappingProxyType:
        return dict(value)
    raise TypeError('导入计划JSON仅允许固定MappingProxyType扩展')


def _require_result(result):
    """核公开转换结果与原bytes/计划身份一致，拒绝失败结果携带部分计划。

    参数: result为LegacyImportResult。返回: None。
    异常: TypeError为非固定模型；ValueError为状态、原SHA或计划身份不一致。
    """
    if (type(result) is not LegacyImportResult or type(result.report) is not LegacyImportReport
            or type(result.original_ini) is not bytes):
        raise TypeError('发布需要LegacyImportResult、LegacyImportReport及原生INI bytes')
    report = result.report
    if report.source_sha256 != sha256(result.original_ini).hexdigest():
        raise ValueError('发布原INI bytes与转换报告SHA不一致')
    if result.plan is None:
        if report.status != 'failed' or report.plan_identity is not None:
            raise ValueError('无计划时只允许失败转换报告，plan_identity必须为None')
    elif (type(result.plan) is not AnalysisPlan or report.status != 'success'
            or report.plan_identity != result.plan.identity):
        raise ValueError('成功转换报告必须关联同一完整AnalysisPlan')


def _targets(output_path, source_paths):
    """先核词法目标、实际保护边界及源冲突，不创建任何输出。

    参数: output_path为.json文件Path/str；source_paths为INI及mapping的Path/str tuple。
    返回: (计划、原文、报告)三个绝对Path，按计划路径派生固定后缀。
    异常: TypeError为路径容器；ValueError为后缀/Ref/源冲突；FileExistsError为任一已有目标。
    """
    if not isinstance(output_path, (Path, str)) or type(source_paths) is not tuple:
        raise TypeError('output_path需要Path/str，source_paths需要tuple')
    if any(not isinstance(path, (Path, str)) for path in source_paths):
        raise TypeError('source_paths每项需要Path/str')
    target = Path(output_path).absolute()
    if target.suffix != '.json':
        raise ValueError('导入计划输出必须使用.json后缀')
    targets = (target, target.with_name(target.stem + '.original.ini'),
        target.with_name(target.stem + '.migration-report.json'))
    # resolve仅用于真实位置核对；安装仍使用原词法路径，已有悬空symlink也必须拒绝。
    project = Path(__file__).absolute().parents[3]
    protected = (project / 'RefProjects').resolve()
    resolved = tuple(path.resolve() for path in targets)
    sources = tuple(Path(path).resolve() for path in source_paths)
    for path, actual in zip(targets, resolved):
        if actual.is_relative_to(protected) or any(part.casefold() == 'refprojects' for part in actual.parts):
            raise ValueError('导入输出禁止位于RefProjects')
        if actual in sources:
            raise ValueError('导入输出不能与原INI或mapping配置同路径')
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        raise FileExistsError('导入目标已存在，禁止覆盖：' + str(path))
    return targets


class _PublicationOwner:
    """仅持本次独占临时文件及一个真实FD，不接管源文件或已安装目标。"""

    def __init__(self, targets):
        """先安装全部实际责任槽，尚不创建临时文件。

        参数: targets为三个已检查的绝对Path。返回: 新owner。异常: 原内存/UUID错误传播。
        """
        self._targets = targets
        self._token = uuid4().hex
        self._temporaries = [None, None, None]
        self._handle = self._opening_path = self._opening_index = None
        self.closed = False

    def _close_handle(self):
        """关闭当前真实FD，失败时保持同一对象及临时路径可恢复。

        参数: 无。返回: None。异常: 原close错误；未真实关闭则OSError。
        """
        if self._handle is not None:
            # FD已返回即证明本次独占创建，补齐open返回与临时槽安装之间的责任窗口。
            if self._opening_path is not None:
                self._temporaries[self._opening_index] = self._opening_path
            self._handle.close()
            if not self._handle.closed:
                raise OSError('导入临时文件FD尚未关闭')
            self._handle = None
        self._opening_path = self._opening_index = None

    def write(self, index, value, *, original=False):
        """独占创建一个临时文件，写完flush且真实close后才允许安装。

        参数: index选择原文/报告/计划槽；value为原bytes或固定JSON树；original选择二进制原文。
        返回: None。异常: 原open/write/flush/close/JSON/内存或取消错误，不隐式重试写入。
        """
        target = self._targets[index]
        temporary = target.parent / ('.' + target.name + '.import-' + self._token + '.tmp')
        self._opening_path, self._opening_index = temporary, index
        # 只在open成功返回真实FD后登记文件所有权；独占失败不能删除碰巧已有的UUID目标。
        if original:
            self._handle = temporary.open('xb')
        else:
            self._handle = temporary.open('x', encoding='utf-8', newline='\n')
        self._temporaries[index] = temporary
        if original:
            if self._handle.write(value) != len(value):
                raise OSError('原INI临时文件写入不完整')
        else:
            # 计划参数对象的声明顺序参与MessageDeclarations身份；不能为排版排序改写。
            # 报告不承担该声明语义，仍沿原规范键序；公式AST和核心身份算法均不改。
            json.dump(value, self._handle, ensure_ascii=False, allow_nan=False,
                sort_keys=index != 0, indent=2, default=_mapping_json)
            self._handle.write('\n')
        self._handle.flush()
        self._close_handle()

    def install(self, index):
        """用Windows真实不覆盖rename安装，成功后只撤本临时槽。

        参数: index为已完整关闭的临时文件槽。返回: None。
        异常: 原rename错误；不能用exists预检查取代最终no-replace。
        """
        os.rename(self._temporaries[index], self._targets[index])
        # rename已是提交事实，之后不写状态文件、不触碰目标或执行额外文件清理。
        self._temporaries[index] = None

    def close(self):
        """可重试关闭FD并逐个删除自有UUID临时文件，保留全部已安装sidecar。

        参数: 无。返回: None，成功后幂等。异常: 原close/unlink错误附同一最高owner。
        """
        if self.closed:
            return
        try:
            self._close_handle()
            for index, temporary in enumerate(self._temporaries):
                if temporary is not None:
                    try:
                        temporary.unlink()
                    except FileNotFoundError:
                        pass
                    self._temporaries[index] = None
            self.closed = True
        except BaseException as error:
            error.legacy_import_publication_cleanup_owner = self
            raise


def write_legacy_import(result: LegacyImportResult, output_path, *, source_paths=()) -> LegacyImportFiles:
    """发布原配置及转换报告，只有完整成功转换才在最后安装计划。

    参数: result为固定转换结果；output_path为新.json目标；source_paths可显式提供
        原INI/mapping路径tuple供CLI防止同源别名冲突。
    返回: LegacyImportFiles，均为绝对Path，转换失败时plan=None。
    异常: 类型/配置错误、已有目标、Ref边界及系统I/O错误保持原异常；非Windows为
        NotImplementedError。KI/MemoryError原样；清理副错仅附note，最高恢复owner留在原错上。
    副作用: 只创建目标父目录和三个自有临时文件；失败可保已装sidecar，绝不覆盖或删用户文件。
    """
    _require_result(result)
    targets = _targets(output_path, source_paths)
    if os.name != 'nt':
        raise NotImplementedError('导入文件发布目前只验证Windows不覆盖安装')
    files = LegacyImportFiles(targets[0] if result.plan is not None else None, targets[1], targets[2])
    owner = _PublicationOwner(targets)
    try:
        # 所有内容先写完并关闭；有计划时也只在两个sidecar安装成功之后提交计划。
        targets[0].parent.mkdir(parents=True, exist_ok=True)
        owner.write(1, result.original_ini, original=True)
        owner.write(2, result.report.to_dict())
        if result.plan is not None:
            owner.write(0, result.plan.raw_config)
        owner.install(1)
        owner.install(2)
        if result.plan is not None:
            owner.install(0)
        # 所有临时槽已由rename撤销，无需在提交点后再执行可能失败的I/O。
        owner.closed = True
        return files
    except BaseException as error:
        error.legacy_import_publication_cleanup_owner = owner
        try:
            owner.close()
        except BaseException as cleanup:
            error.add_note('导入发布清理附加失败：' + type(cleanup).__name__
                + '；调用legacy_import_publication_cleanup_owner.close()恢复')
        raise
