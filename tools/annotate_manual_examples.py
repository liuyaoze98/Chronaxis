"""用人工职责词典为全部手册YAML示例加注释，逐份验证解析值未改变。

参数--write才写文件；默认仅检查。父子控制字段分别注释，数据标量列表保持紧凑。
新字段缺说明时拒绝执行，不能用自动生成的泛化句子掩盖遗漏。
"""
import argparse
from datetime import datetime, timezone, timedelta
from io import StringIO
from pathlib import Path
import re
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from manual_example_comments import comment, example_comment

ROOT = Path(__file__).resolve().parents[1] / 'Docs/Current'
ORDER = ['config_version','imports','dataset','sources','signals','derived','transforms','presets','rules','windows',
         'sequences','calculations','aggregations','message_calculations','intervals','execution','diagnostics','outputs','metadata']


def render(text, example_path=None):
    """参数: YAML原文、可选的examples相对路径。返回同义YAML；错误上下文或解析值变化时失败。"""
    parser=YAML(typ='rt');parser.preserve_quotes=True;parser.width=120
    parser.indent(mapping=2,sequence=4,offset=2)
    value=parser.load(text);before=YAML(typ='safe').load(text)
    # 编辑器关联是有实际用途的注释，重写说明时必须保留。
    directives=re.findall(r'^#\s*yaml-language-server:.*$',text,re.M)
    parser.representer.add_representer(type(None),lambda representer,value: representer.represent_scalar('tag:yaml.org,2002:null','null'))
    if isinstance(value,CommentedMap):
        keys=list(value)
        for key in ORDER + [key for key in keys if key not in ORDER]:
            if key in value:value.move_to_end(key)

    def annotate(node,prefix=''):
        """参数: 节点/完整父路径。返回: None。异常: 未登记字段直接失败。"""
        if isinstance(node,(CommentedMap,CommentedSeq)):
            node.ca.comment=None;node.ca.items.clear();node.ca.end.clear()
        if isinstance(node,CommentedMap):
            # 仅调整存在引用关系的局部参数：读到公式之前先看到其参数定义。
            if re.search(r'message_calculations\[\d+\]$', prefix) and 'parameters' in node and 'expr' in node:
                if list(node).index('parameters') > list(node).index('expr'):
                    parameters = node.pop('parameters')
                    node.insert(list(node).index('expr'), 'parameters', parameters)
            # 内联映射是语法教程的内容；不能为了加注释统一改成多行。
            if node.fa.flow_style():
                for key in node:comment(f'{prefix}.{key}' if prefix else str(key))
                return
            for key,child in node.items():
                path=f'{prefix}.{key}' if prefix else str(key)
                # 使用行尾注释，便于读者把职责与同一行的具体值对应。
                explanation=example_comment(path,child,node)
                # fast只接受展开后一个文件；不能套用连续分析的多文件说明。
                if example_path and example_path.startswith('fast/'):
                    if re.fullmatch(r'sources\[\d+\]\.paths', path):
                        explanation='指定本次会话的ASC/BLF文件、目录或通配符；同次记录的分卷放在同一来源中'
                    explanation = {
                        'execution': '控制本次fast会话的工作进程、受管理内存和临时磁盘额度',
                        'execution.process_count': '限制读取、解码和单帧求值工作进程；正整数，默认1内联，不含主进程',
                        'execution.memory_budget_bytes': '限制受管理缓冲和状态的估算字节数；不含整个Python进程树的全部内存',
                        'execution.spool_quota_bytes': '限制累计预约暂存字节数；删除不返还，null不设额外上限',
                    }.get(path, explanation)
                if isinstance(child,CommentedMap) and child.fa.flow_style():
                    if any(isinstance(item,(CommentedMap,CommentedSeq)) for item in child.values()):
                        raise ValueError('内联教学映射仅支持标量子字段：'+path)
                    explanation+='；'+'；'.join(str(k)+'：'+comment(path+'.'+str(k)) for k in child)
                node.yaml_add_eol_comment(explanation,key=key)
                annotate(child,path)
        elif isinstance(node,CommentedSeq):
            if all(not isinstance(child,(CommentedMap,CommentedSeq)) for child in node):node.fa.set_flow_style()
            else:node.fa.set_block_style()
            for index,child in enumerate(node):annotate(child,f'{prefix}[{index}]')
    annotate(value)
    stream=StringIO();parser.dump(value,stream)
    # 只对本工具生成的注释标记定位，避免把字符串中的#当成注释；同块统一列。
    lines=stream.getvalue().splitlines()
    marked=[]
    for line in lines:
        indices=[m.start() for m in re.finditer(r'\s+# ',line)]
        marked.append(indices[-1] if indices else None)
    column=max((len(line[:at].rstrip()) for line,at in zip(lines,marked) if at is not None),default=0)+4
    lines=[line[:at].rstrip().ljust(column)+line[at:].lstrip() if at is not None else line for line,at in zip(lines,marked)]
    result=('\n'.join(directives)+'\n' if directives else '')+'\n'.join(lines)+'\n'
    # 单文件教学说明限定实际路径；不能把单BLF的legacy行为推广到文本CAN。
    if example_path == 'message-energy.yaml':
        source = before['sources'][0]
        assert len(before['sources']) == 1 and source['paths'] == 'data/power.blf'
        assert 'offsets' not in source and source.get('source_type', 'can_blf') in ('can_blf', 'asc_or_blf')
        assert source['reader']['decode_policy'] == 'legacy'
        notes = [
            '控制所选CAN帧的长度检查与解码失败处理。',
            '本例单BLF使用legacy：不增加这项DBC长度预检查，短帧仍尝试解码已有字段。',
            '解码异常返回空解码结果；缺少当前公式所需值时跳过该次贡献，不沿用前值。',
            '各路径差异见 ../inputs.html#解码失败时各读取路径的处理',
        ]
        result, count = re.subn(r'^(\s*)decode_policy: legacy[^\n]*$',
            lambda m: '\n'.join(m[1]+'# '+line for line in notes)+'\n'+
            (m[1]+'decode_policy: legacy').ljust(column)+'# 选择本例使用的解码策略；行为见以上说明', result, flags=re.M)
        assert count == 1, '单BLF教学说明未能准确定位'
    assert before==YAML(typ='safe').load(result),'注释改写改变了配置值'
    return result


def main():
    """参数: --write选择写入。返回: None。异常: 任一块失败则在写文件前中止。"""
    arguments=argparse.ArgumentParser(description=__doc__);arguments.add_argument('--write',action='store_true');args=arguments.parse_args()
    pending={};count=0;stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    # 先全部准备并校验，避免遇到未登记字段时已经改了一半文件。
    for path in ROOT.glob('*.md'):
        text=path.read_text(encoding='utf8')
        def replace(match):
            """参数: 完整YAML代码块。返回: 同义注释块。异常: 原校验错误。"""
            nonlocal count
            count+=1
            return match[1]+render(match[2])+match[3]
        updated=re.sub(r'(^[~`]{3}ya?ml\s*\n)(.*?)(^[~`]{3})',replace,text,flags=re.M|re.S)
        if updated!=text:
            pending[path]=updated
    for path in (ROOT/'examples').rglob('*.yaml'):
        count+=1
        pending[path]='# 合成教学配置；请连同配套输入使用，数值仅用于复现本例。\n'+render(path.read_text(encoding='utf8'),path.relative_to(ROOT/'examples').as_posix())
    # config init默认注释版也使用同一职责词典；显式minimal风格保留其少注释用途。
    for path in (ROOT.parents[1]/'src/chronaxis/configuration/templates').rglob('annotated.yaml'):
        count+=1
        pending[path]=render(path.read_text(encoding='utf8'))
    if args.write:
        for path,text in pending.items():path.write_text(text,encoding='utf8')
    print(f'{count} YAML documents preserved; {len(pending)} files prepared; write={args.write}')


if __name__=='__main__':main()
