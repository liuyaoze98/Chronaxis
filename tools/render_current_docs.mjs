/** 构建当前版离线手册。只写Docs/Current/_build/html，不访问网络或执行示例。 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const docs=path.join(root,'Docs/Current'), output=path.join(docs,'_build/html');
// 来源变化必须先复核译文，不能让普通HTML重建静默发布旧英文说明。
execFileSync(process.env.CHRONAXIS_DOC_PYTHON || 'python', ['-B', path.join(root,'tools/english_docs.py')], {stdio:'inherit'});
const tooling=path.join(docs,'_build/tooling/node_modules');
const {marked}=await import(pathToFileURL(process.env.CHRONAXIS_MARKED_PATH || path.join(tooling,'marked/lib/marked.esm.js')).href);
const {default:hljs}=await import(pathToFileURL(process.env.CHRONAXIS_HIGHLIGHT_PATH || path.join(tooling,'highlight.js/es/index.js')).href);
// 高亮在构建时完成；阅读和复制不需要网络或外部运行时。
let renderLanguage='zh';
marked.use({renderer:{code({text,lang}){
  const language=(lang||'text').split(/\s/)[0];
  const highlighted=hljs.getLanguage(language)?hljs.highlight(text,{language,ignoreIllegals:true}).value:escape(text);
  return `<div class="code-block"><div class="code-tools"><span>${escape(language)}</span><button type="button" class="copy-code" aria-label="${renderLanguage==='en'?'Copy code':'复制代码'}">${renderLanguage==='en'?'Copy':'复制'}</button><span class="copy-status" role="status"></span></div><pre><code class="hljs language-${escape(language)}">${highlighted}</code></pre></div>`;
}}});
const inventory=JSON.parse(await fs.readFile(path.join(docs,'reference/inventory.json'),'utf8'));
const navigation=JSON.parse(await fs.readFile(path.join(docs,'navigation.json'),'utf8')).groups;
const englishNavigation=JSON.parse(await fs.readFile(path.join(docs,'en/navigation.json'),'utf8')).groups;
const publicAPI=JSON.parse(await fs.readFile(path.join(docs,'public-api.json'),'utf8')).objects;
const publicTargets=new Set(publicAPI.map(x=>x.target.split('#')[0].replace(/\.md$/,'.html')));
const slash=x=>x.replaceAll('\\','/');
const escape=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const htmlName=x=>x.replace(/\.md$/,'.html');
const flat=navigation.flatMap(g=>g.pages.map(p=>({...p,group:g.title})));
const sourceMap=new Map(inventory.modules.map(m=>[path.resolve(root,m.path),m]));
const search=[];
const files=[];
const attachments=new Map();

/** 遍历源码文档，排除生成目录；返回排序稳定的文件清单。 */
async function collect(dir){
  for(const entry of await fs.readdir(dir,{withFileTypes:true})){
    if(entry.name==='_build')continue;
    const target=path.join(dir,entry.name);
    if(entry.isDirectory())await collect(target);
    else if(entry.name.endsWith('.md'))files.push(target);
  }
}
/** 用户页面隐藏维护履历；源码文件仍完整保留。 */
function readingText(text){
  const parts=text.split(/^## 变更履历\s*$/m);
  if(parts.length>1&&/^#{1,6} /m.test(parts.slice(1).join('\n')))throw new Error('变更履历后包含正文标题；请将正文移到履历前');
  return parts[0].trim();
}

/** 使用相对地址和分组导航生成离线页面。 */
function shell(title,body,relative,toc=[]){
  const en=relative.startsWith('en/'),tr=(zh,eng)=>en?eng:zh;
  const navGroups=en?englishNavigation:navigation;
  const local=relative.replace(/^en\//,'');
  const pages=navGroups.flatMap(g=>g.pages.map(p=>({...p,group:g.title})));
  const prefix=slash(path.relative(path.dirname(relative),'.'))||'.';
  const current=pages.find(p=>htmlName(p.path)===local);
  const idx=pages.indexOf(current),prev=pages[idx-1],next=pages[idx+1];
  const href=p=>`${prefix}/${en?'en/':''}${htmlName(p.path)}`;
  const nav=navGroups.map(g=>`<section class="nav-group"><h2>${escape(g.title)}</h2>${g.pages.map(p=>`<a ${htmlName(p.path)===local?'class="active" aria-current="page"':''} href="${href(p)}">${escape(p.title)}</a>`).join('')}</section>`).join('');
  const tocHTML=toc.map(h=>`<a class="depth-${h.level}" href="#${escape(h.id)}">${h.inner}</a>`).join('');
  const pager=current?`<div class="pager">${prev?`<a rel="prev" href="${href(prev)}">← ${escape(prev.title)}</a>`:'<span></span>'}${next?`<a rel="next" href="${href(next)}">${escape(next.title)} →</a>`:''}</div>`:'';
  const counterpart=en?local:(local.startsWith('source/')||local.startsWith('reference/')&&local!=='reference/configuration-schema.html'&&local!=='reference/index.html'?'en/reference/index.html':'en/'+local);
  return `<!doctype html><html lang="${en?'en':'zh-CN'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)} · Chronaxis</title><link rel="stylesheet" href="${prefix}/style.css"></head><body>
<a class="skip" href="#manual-main-content">${tr('跳到正文','Skip to content')}</a><header><a class="brand" href="${prefix}/${en?'en/':''}index.html">Chronaxis</a><span>${tr('用户手册','User manual')}</span><a class="language-link" href="${prefix}/${counterpart}" lang="${en?'zh-CN':'en'}">${en?'中文':'English'}</a><button id="nav-toggle" type="button" aria-expanded="false" aria-controls="navigation">${tr('目录','Contents')}</button><div class="search"><div class="search-controls"><input id="search" type="search" placeholder="${tr('搜索功能、字段或API','Search features, fields or APIs')}" aria-label="${tr('搜索文档','Search documentation')}" aria-controls="hits" aria-expanded="false"><select id="search-category" aria-label="${tr('搜索范围','Search scope')}"><option value="user">${tr('用户文档','User docs')}</option><option value="guide">${tr('功能指南','Guides')}</option><option value="api">${tr('公开API','Public API')}</option><option value="internal">${tr('内部参考','Internals')}</option><option value="all">${tr('全部','All')}</option></select></div><div class="hits" id="hits" aria-label="${tr('搜索结果','Search results')}"></div></div></header>
<div class="layout"><nav id="navigation" aria-label="${tr('章节目录','Chapters')}">${nav}</nav><main id="manual-main-content"><div class="breadcrumb">${escape(current?.group || tr('API参考','API reference'))} / ${escape(title)}</div><details class="mobile-toc"><summary>${tr('本页目录','On this page')}</summary>${tocHTML}</details><article>${body}</article>${pager}<footer>${tr('Chronaxis 用户手册 · 离线阅读','Chronaxis user manual · Offline edition')}</footer></main><aside aria-label="${tr('本页目录','On this page')}"><strong>${tr('本页目录','On this page')}</strong>${tocHTML}</aside></div>
<script src="${prefix}/search-data.js"></script><script>const prefix=${JSON.stringify(prefix)};</script><script src="${prefix}/manual.js"></script><script src="${prefix}/search.js"></script></body></html>`;
}

const css=`:root{--ink:#203345;--muted:#596c7b;--line:#dbe4eb;--accent:#006b74;--soft:#eef4f7}*{box-sizing:border-box}body{margin:0;color:var(--ink);font:16px/1.75 system-ui,'Microsoft YaHei',sans-serif;background:white}a{color:var(--accent);text-underline-offset:3px}header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:20px;padding:14px 24px;min-height:70px;background:white;border-bottom:1px solid var(--line)}.brand{font-size:23px;font-weight:750;text-decoration:none}.search{position:relative;margin-left:auto;width:min(460px,45vw)}input,select,button{font:inherit}input{width:100%;padding:8px 12px;border:1px solid #9db3bf;border-radius:5px}button{cursor:pointer}.hits{display:none;position:absolute;top:100%;right:0;max-height:70vh;overflow:auto;width:min(650px,90vw);background:white;box-shadow:0 8px 28px #2343;border:1px solid var(--line)}.hits a{display:block;padding:10px 15px;text-decoration:none;border-bottom:1px solid var(--line)}.hits small{display:block;color:var(--muted)}.layout{display:grid;grid-template-columns:240px minmax(0,1fr) 225px;max-width:1700px;margin:auto}nav{padding:22px 14px;background:var(--soft);height:calc(100vh - 70px);overflow:auto;position:sticky;top:70px}nav h2{font-size:13px;margin:20px 10px 6px;color:var(--muted);border:0;padding:0}nav a{display:block;font-size:14px;padding:5px 10px;text-decoration:none;border-radius:4px}nav a.active{background:#d5e9e9;font-weight:700;color:#004f59}main{min-width:0;padding:30px 38px 70px}.breadcrumb{font-size:12px;color:var(--muted);margin-bottom:20px}h1{font-size:32px;line-height:1.4;margin:0 0 25px}h2{font-size:24px;border-top:1px solid var(--line);padding-top:20px;margin-top:38px}h3{font-size:19px;margin-top:28px}h4{font-size:16px;margin-top:22px}h1,h2,h3,h4{overflow-wrap:anywhere;scroll-margin-top:95px}aside{padding:28px 18px 20px 0;position:sticky;top:70px;height:calc(100vh - 70px);overflow:auto;font-size:12px}aside a,.mobile-toc a{display:block;padding:4px 0;text-decoration:none;overflow-wrap:anywhere}aside .depth-3,.mobile-toc .depth-3{padding-left:14px}p{margin:15px 0}code{font-family:Consolas,monospace;font-size:.9em;overflow-wrap:anywhere}p code,li code,td code{background:var(--soft);padding:2px 4px;border-radius:3px}pre{position:relative;padding:20px;background:#f5f7fa;border:1px solid var(--line);border-radius:6px;overflow:auto;font:13px/1.65 Consolas,monospace}pre code{white-space:pre;overflow-wrap:normal}table{border-collapse:collapse;width:100%;font-size:14px;margin:22px 0}td,th{border:1px solid var(--line);text-align:left;padding:9px 11px;vertical-align:top;overflow-wrap:anywhere}th{background:var(--soft)}tr:nth-child(even){background:#fafcfd}.table-wrap{overflow:auto}blockquote{border-left:4px solid #568f96;background:#f0f6f8;padding:8px 18px;margin:20px 0}details{margin:18px 0}summary{cursor:pointer}.pager{display:flex;justify-content:space-between;gap:20px;border-top:1px solid var(--line);padding-top:20px;margin-top:45px}footer{color:var(--muted);font-size:12px;margin-top:32px}.skip{position:fixed;top:-50px;left:10px;background:white;z-index:20}.skip:focus{top:5px}.mobile-toc,#nav-toggle{display:none}.source-line{display:block;white-space:pre}.source-line:target{background:#fff2b4}.num{display:inline-block;width:55px;color:#6a7a88;user-select:none}@media(max-width:1180px){.layout{grid-template-columns:220px minmax(0,1fr)}aside{display:none}.mobile-toc{display:block}}@media(max-width:760px){header{gap:12px;flex-wrap:wrap;padding:12px}header>span{display:none}.search{width:100%;margin:0}.layout{display:block}#nav-toggle{display:block;margin-left:auto}nav{display:none;position:static;height:auto}nav.open{display:block}main{padding:24px 16px}h1{font-size:27px}h2{font-size:21px}table{font-size:13px}td,th{min-width:100px}pre{padding:14px}html{scroll-padding-top:150px}}`;
const script=`const toggle=document.getElementById('nav-toggle');toggle.addEventListener('click',()=>{const open=document.getElementById('navigation').classList.toggle('open');toggle.setAttribute('aria-expanded',String(open))});
document.querySelectorAll('.copy-code').forEach(button=>button.addEventListener('click',async()=>{
  const block=button.closest('.code-block'),text=block.querySelector('code').textContent,status=block.querySelector('.copy-status');
  try{
    let copied=false;
    if(navigator.clipboard&&window.isSecureContext){try{await navigator.clipboard.writeText(text);copied=true}catch{}}
    if(!copied){const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.left='-10000px';document.body.append(area);area.select();copied=document.execCommand('copy');area.remove();button.focus()}
    const en=document.documentElement.lang==='en';status.textContent=copied?(en?'Copied':'已复制'):(en?'Select the code and copy it':'请选中代码后复制');
  }catch{status.textContent=document.documentElement.lang==='en'?'Copy failed; select the code and copy it':'复制失败，请选中代码后复制'}
}));`;

// 输出是固定的可再生目录；先验证边界再清除旧附件，避免已移除的内容继续发布。
if(path.dirname(output)!==path.join(docs,'_build')||path.basename(output)!=='html')throw new Error('非法手册输出目录');
await fs.rm(output,{recursive:true,force:true});
await fs.mkdir(output,{recursive:true});
const highlightCSS=await fs.readFile(path.join(tooling,'highlight.js/styles/github.css'),'utf8');
await fs.writeFile(path.join(output,'style.css'),css+highlightCSS+'\n.code-tools{display:flex;align-items:center;gap:12px;font-size:12px;color:var(--muted);padding:8px 12px;border:1px solid var(--line);border-bottom:0;border-radius:6px 6px 0 0;background:var(--soft)}.code-tools button{margin-left:auto;border:1px solid #a9bbc5;border-radius:4px;background:white;padding:2px 10px}.code-block pre{margin-top:0;border-radius:0 0 6px 6px}.code-block pre code.hljs{padding:0;background:transparent;overflow:visible}');
await fs.writeFile(path.join(output,'manual.js'),script);
await fs.copyFile(path.join(root,'tools/manual_search.js'),path.join(output,'search.js'));
await fs.mkdir(path.join(output,'licenses'),{recursive:true});
await fs.copyFile(path.join(root,'LICENSE'),path.join(output,'licenses/Chronaxis-LICENSE.txt'));
await fs.copyFile(path.join(root,'Docs/Release/ThirdParty/highlight.js-LICENSE.txt'),path.join(output,'licenses/highlight.js-LICENSE.txt'));
await fs.appendFile(path.join(output,'style.css'),'\n.search-controls{display:flex;gap:6px}.search-controls input{min-width:0}.search-controls select{max-width:120px;border:1px solid #9db3bf;border-radius:5px;font-size:13px}.search-status{padding:8px 14px;font-size:13px;color:var(--muted)}.hits button{margin:12px;padding:6px 14px}.hits a:focus{background:#e1f1f1;outline:2px solid var(--accent);outline-offset:-2px}');
await collect(docs);files.sort();
// 与安装包复用同一生成器；失败时终止构建，避免首页指向旧资料。
execFileSync(process.env.CHRONAXIS_DOC_PYTHON || 'python', ['-B', path.join(root,'tools/build_ai_guide.py'), path.join(output,'Chronaxis-AI.zip'),'--directory',path.join(output,'ai-guide')], {stdio:'inherit'});
for(const file of files){
  const relative=htmlName(slash(path.relative(docs,file)));
  renderLanguage=relative.startsWith('en/')?'en':'zh';
  const local=relative.replace(/^en\//,'');
  const text=readingText(await fs.readFile(file,'utf8'));
  const title=(text.match(/^# (.+)$/m)||[])[1]||relative;
  let body=marked.parse(text,{gfm:true});
  const toc=[],used=new Set(["manual-main-content","navigation","nav-toggle","search","hits","search-category",...Array.from(body.matchAll(/\bid="([^"]+)"/g),m=>m[1])]);
  body=body.replace(/<h([1234])>([\s\S]*?)<\/h\1>/g,(_,level,inner)=>{
    const base=inner.replace(/<[^>]+>/g,'').toLowerCase().replace(/[^\p{L}\p{N}_-]+/gu,'-');
    let id=base,n=1;while(used.has(id))id=base+'-'+n++;used.add(id);
    if(level==='2'||level==='3')toc.push({id,level,inner});
    return `<h${level} id="${escape(id)}">${inner}</h${level}>`;
  });
  // 实际结果保持字段名和数字完整；宽表在容器内滚动，不逐字拆行。
  const tableStyle=local==='example-results.html'?' style="white-space:nowrap;overflow-wrap:normal"':'';
  body=body.replace(/<table>/g,`<div class="table-wrap"><table${tableStyle}>`).replace(/<\/table>/g,'</table></div>');
  body=body.replace(/href="([^"#]+)(#[^"]*)?"/g,(whole,url,hash='')=>{
    if(/^[a-z]+:/i.test(url))return whole;
    const target=path.resolve(path.dirname(file),decodeURI(url));
    let dest;
    if(sourceMap.has(target))dest=path.join(output,'source',sourceMap.get(target).module+'.html');
    else if(target.startsWith(output+path.sep))dest=target;
    else if(target.startsWith(docs+path.sep))dest=path.join(output,htmlName(path.relative(docs,target)));
    else {
      // 只复制公开规范及发布说明；未知附件直接拒绝，避免沿链接带入内部资料。
      const repositoryRelative=path.relative(root,target);
      const allowed=['Docs/Schema/','Docs/Release/'].some(prefix=>slash(repositoryRelative).startsWith(prefix));
      if(!allowed)throw new Error('文档附件超出公开范围: '+url);
      dest=path.join(output,'attachments',repositoryRelative);
      attachments.set(target,dest);
    }
    return `href="${slash(path.relative(path.dirname(path.join(output,relative)),dest))}${hash}"`;
  });
  const dest=path.join(output,relative);await fs.mkdir(path.dirname(dest),{recursive:true});
  await fs.writeFile(dest,shell(title,body,relative,toc));
  if(local!=='results-v2.html'){
    // 以完整章节为检索单元；保留页后半部分与字段表，不只截取开头摘要。
    const sections=body.split(/(?=<h[23] id=)/);
    const publicNames=publicAPI.filter(x=>htmlName(x.target.split('#')[0])===local).map(x=>x.qualified);
    // 一次还原HTML实体，保留原文本本来就有的实体字样；搜索界面仍用textContent。
    const plain=html=>html.replace(/<[^>]*>/g,' ').replace(/&(#x[0-9a-f]+|#[0-9]+|lt|gt|amp|quot|apos|nbsp);/gi,(_,entity)=>{
      if(entity.startsWith('#'))return String.fromCodePoint(entity[1].toLowerCase()==='x'?parseInt(entity.slice(2),16):parseInt(entity.slice(1),10));
      return {lt:'<',gt:'>',amp:'&',quot:'"',apos:"'",nbsp:' '}[entity.toLowerCase()];
    }).replace(/\s+/g,' ').trim();
    for(const section of sections){
      const heading=section.match(/^<h[23] id="([^"]+)">([\s\S]*?)<\/h[23]>/);
      const label=heading?plain(heading[2]):'';
      let category=local.startsWith('reference/')?'internal':local.startsWith('public-api/')?'api':'guide';
      if(publicTargets.has(local)&&publicNames.some(name=>label===name||label.startsWith(name+'.')&&!label.slice(name.length+1).startsWith('_')))category='api';
      if(['architecture.html','maintenance.html'].includes(local))category='internal';
      search.push({title:title+(label?' / '+label:''),url:relative+(heading?'#'+heading[1]:''),text:plain(section),category,language:renderLanguage});
    }
  }
}
for(const m of inventory.modules){
  const source=await fs.readFile(path.join(docs,'_build/source',m.path),'utf8');
  if(createHash('sha256').update(source).digest('hex')!==m.sha256)throw new Error('源码哈希不一致: '+m.path);
  const relative='source/'+m.module+'.html';
  const body=`<h1>${escape(m.module)}</h1><p>源码基线：${escape(inventory.baseline)}</p><pre>${source.split(/\r?\n/).map((line,i)=>`<span class="source-line" id="L${i+1}"><a class="num" href="#L${i+1}">${i+1}</a>${escape(line)}</span>`).join('')}</pre>`;
  await fs.mkdir(path.join(output,'source'),{recursive:true});await fs.writeFile(path.join(output,relative),shell(m.module,body,relative));
}
// 示例是生成目录中的副本；重建时清除旧副本，避免已撤下的结果混进新版手册。
const exampleOutput=path.resolve(output,'examples');
if(path.relative(path.resolve(docs,'_build/html'),exampleOutput)!=='examples')throw new Error('示例输出目录超出构建目录');
const exampleStat=await fs.lstat(exampleOutput).catch(error=>{if(error.code==='ENOENT')return null;throw error;});
if(exampleStat?.isSymbolicLink())throw new Error('示例输出目录不能是符号链接');
await fs.rm(exampleOutput,{recursive:true,force:true});
await fs.cp(path.join(docs,'examples'),exampleOutput,{recursive:true});
for(const [source,dest] of attachments){
  await fs.mkdir(path.dirname(dest),{recursive:true});
  await fs.copyFile(source,dest);
}
// 四份规范互有相对引用，整体复制才能离线使用。
await fs.mkdir(path.join(output,'attachments/Docs/Schema'),{recursive:true});
for(const name of ['analysis.schema.json','batch-v1.schema.json','definitions.schema.json','legacy-import-v1.schema.json']){
  await fs.copyFile(path.join(root,'Docs/Schema',name),path.join(output,'attachments/Docs/Schema',name));
}
for(const file of ['documentation.json','public-api.json','navigation.json','reference/inventory.json'])await fs.copyFile(path.join(docs,file),path.join(output,file));
for(const file of ['public-api.json','navigation.json'])await fs.copyFile(path.join(docs,'en',file),path.join(output,'en',file));
await fs.writeFile(path.join(output,'search-data.js'),'window.DOC_SEARCH='+JSON.stringify(search).replaceAll('<','\\u003c')+';');
const englishReview=createHash('sha256').update(await fs.readFile(path.join(docs,'en/translation-status.json'))).digest('hex');
await fs.writeFile(path.join(output,'build-manifest.json'),JSON.stringify({baseline:inventory.baseline,device_label:'home',pages:files.length,sourcePages:inventory.modules.length,groups:navigation.length,languages:['zh','en'],englishReview},null,2));
console.log(JSON.stringify({pages:files.length,sourcePages:inventory.modules.length,groups:navigation.length,output}));
