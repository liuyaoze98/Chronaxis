/** 读取离线包中Markdown的真实链接与锚点；使用手册已有的marked，不执行文档代码。 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const modulePath=process.env.CHRONAXIS_MARKED_PATH || path.join(root,'Docs/Current/_build/tooling/node_modules/marked/lib/marked.esm.js');
const {marked}=await import(pathToFileURL(modulePath).href);

/** 从Markdown正文提取链接和显式/标题锚点；代码块及行内代码不作为导航。 */
export function references(text){
  const links=[],ids=new Set(),counts=new Map();
  marked.walkTokens(marked.lexer(text),token=>{
    if(token.type==='link'||token.type==='image')links.push(token.href);
    if(token.type==='html'){
      for(const match of token.raw.matchAll(/\bid\s*=\s*["']([^"']+)["']/gi))ids.add(match[1]);
      for(const match of token.raw.matchAll(/\b(?:href|src)\s*=\s*["']([^"']+)["']/gi))links.push(match[1]);
    }
    if(token.type==='heading'){
      // Markdown读者使用常见标题锚点；中文保留，格式标记和标点不进入锚点。
      const plain=marked.parseInline(token.text).replace(/<[^>]*>/g,'');
      const base=plain.toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu,'').replace(/\s/g,'-');
      const count=counts.get(base)||0;counts.set(base,count+1);
      ids.add(base+(count?'-'+count:''));
    }
  });
  return {links,ids:[...ids]};
}

/** 改写公开附件的Markdown目标，保留链接标签、代码围栏和行内代码原文。 */
export function rewriteLinks(text,resolve){
  // marked会规范换行；保留到原文字节位置的映射，仅替换实际导航的目标部分。
  let normalized='';const positions=[];
  for(let i=0;i<text.length;i++){
    if(text[i]==='\r'&&text[i+1]==='\n')continue;
    positions.push(i);normalized+=text[i];
  }
  const edits=[];
  const slice=(view,start,end)=>({text:view.text.slice(start,end),map:view.map.slice(start,end)});

  /** 将引用或列表去掉标记后的行映射回原文；无法精确定位时拒绝构建。 */
  function contentView(view,content){
    const rawLines=view.text.split('\n'),lines=content.split('\n');
    const map=[];let rawOffset=0;
    for(let i=0;i<lines.length;i++){
      const raw=rawLines[i],line=lines[i];
      const start=raw===undefined?-1:raw.indexOf(line);
      if(start<0)throw new Error('Markdown容器内容无法定位，不能安全改写链接');
      for(let j=0;j<line.length;j++)map.push(view.map[rawOffset+start+j]);
      if(i<lines.length-1)map.push(view.map[rawOffset+raw.length]);
      rawOffset+=raw.length+1;
    }
    return {text:content,map};
  }

  /** 定位链接或引用定义的目标，保留尖括号、标题和链接标签。 */
  function destinationRange(raw,definition=false){
    const starts=definition?[raw.match(/^\s*\[[^\]]+\]:\s*/)?.[0].length]:
      [...raw.matchAll(/\]\(\s*/g)].map(match=>match.index+match[0].length);
    for(const start of starts){
      if(start===undefined)continue;
      const angle=raw[start]==='<';let end=start+(angle?1:0),depth=0;
      for(;end<raw.length;end++){
        if(raw[end]==='\\'){end++;continue;}
        if(angle){if(raw[end]==='>')break;continue;}
        if(/\s/.test(raw[end])||raw[end]===')'&&depth===0)break;
        if(raw[end]==='(')depth++;
        if(raw[end]===')')depth--;
      }
      if(angle&&raw[end]!=='>')continue;
      const tail=raw.slice(end+(angle?1:0));
      const valid=definition?/^\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\((?:\\.|[^)\\])*\))?\s*$/s:
        /^\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\((?:\\.|[^)\\])*\))?\s*\)$/s;
      if(valid.test(tail))return {start:start+(angle?1:0),end,angle};
    }
    return null; // 引用式链接的目标位于def token中，不修改引用标签。
  }

  function update(token,view){
    const range=destinationRange(view.text,token.type==='def');
    if(!range)return;
    let replacement=resolve(token.href);
    if(replacement===token.href)return;
    if(!range.angle&&/\s/.test(replacement))replacement='<'+replacement+'>';
    const start=view.map[range.start],end=view.map[range.end-1]+1;
    if(start===undefined||!Number.isInteger(end))throw new Error('Markdown链接位置不完整');
    edits.push({start,end,replacement});
  }

  function walk(tokens,view){
    let cursor=0;
    for(const token of tokens){
      const start=view.text.indexOf(token.raw,cursor);
      if(start<0)throw new Error('Markdown token无法定位，不能安全改写链接');
      cursor=start+token.raw.length;const own=slice(view,start,cursor);
      if(token.type==='code'||token.type==='codespan')continue;
      if(token.type==='link'||token.type==='image'||token.type==='def')update(token,own);
      if(token.type==='blockquote')walk(token.tokens,contentView(own,token.text));
      else if(token.type==='list'){
        let itemOffset=0;
        for(const item of token.items){
          const at=own.text.indexOf(item.raw,itemOffset);
          if(at<0)throw new Error('Markdown列表项无法定位');
          itemOffset=at+item.raw.length;
          walk(item.tokens,contentView(slice(own,at,itemOffset),item.text));
        }
      }else if(token.type==='table'){
        let cellOffset=0;
        for(const cell of [...token.header,...token.rows.flat()]){
          const at=own.text.indexOf(cell.text,cellOffset);
          if(at<0)throw new Error('Markdown表格单元无法定位');
          cellOffset=at+cell.text.length;walk(cell.tokens,slice(own,at,cellOffset));
        }
      }else if(token.tokens)walk(token.tokens,own);
    }
  }
  walk(marked.lexer(normalized),{text:normalized,map:positions});
  edits.sort((a,b)=>b.start-a.start);let previous=text.length;
  for(const {start,end,replacement} of edits){
    if(end>previous)throw new Error('Markdown链接改写范围重叠');
    text=text.slice(0,start)+replacement+text.slice(end);previous=start;
  }
  return text;
}

/** 递归读取传入的离线目录；只返回相对路径、链接和锚点，不保存额外文件。 */
export async function inventory(directory){
  const docs=[];
  async function visit(folder){
    for(const entry of await fs.readdir(folder,{withFileTypes:true})){
      const target=path.join(folder,entry.name);
      if(entry.isDirectory())await visit(target);
      else if(entry.isFile()&&entry.name.endsWith('.md'))docs.push({file:path.relative(directory,target).replaceAll('\\','/'),...references(await fs.readFile(target,'utf8'))});
    }
  }
  await visit(directory);return docs;
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const directory=process.argv[2];
  if(!directory)throw new Error('请指定离线手册目录');
  console.log(JSON.stringify(await inventory(path.resolve(directory))));
}
