"""把已校验的随包合成场景写入新目录，不改写已有文件。"""
from pathlib import Path

from .template_catalog import available_templates, template_files


def initialize_configuration(scene, output, *, style='annotated'):
    """生成独立场景。参数: 场景名、新目录及风格。返回: 入口绝对路径。异常: ValueError/IO/取消。

    先读取全部包资源再独占创建目录，入口最后写出。写入失败仅删除本次创建的文件和目录；
    清理失败附注原错误并保留残余，不删除其他进程写入的文件，不以成功掩盖部分写入。
    """
    contents=template_files(scene,style=style)
    template=next(t for t in available_templates() if t.name==scene)
    target=Path(output).absolute()
    # mkdir的独占失败发生在清理区之前，已有目录（包括空目录、链接）不属于本次操作。
    target.mkdir()
    created_files=[];created_directories=[target]
    try:
        # 将主入口放在最后，使中途产物不能被误认为完整场景。
        for relative,content in sorted(contents,key=lambda item:item[0]==template.entrypoint):
            path=target/relative
            missing=[];parent=path.parent
            while parent!=target and not parent.exists():missing.append(parent);parent=parent.parent
            for directory in reversed(missing):directory.mkdir();created_directories.append(directory)
            with path.open('xb') as stream:
                created_files.append(path);stream.write(content)
        return target/template.entrypoint
    except BaseException as error:
        for path in reversed(created_files):
            try:path.unlink()
            except OSError as cleanup:error.add_note('未能清理本次文件 '+str(path)+': '+str(cleanup))
        for directory in reversed(created_directories):
            try:directory.rmdir()
            except OSError as cleanup:error.add_note('未能清理本次空目录 '+str(directory)+': '+str(cleanup))
        raise
