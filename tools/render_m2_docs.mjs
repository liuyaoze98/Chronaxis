/**
 * 将明确选择的M2/M3/Current手册渲染为带离线搜索、页内导航和冻结源码的HTML。
 * 输入为Docs/<版本> Markdown、清单与已安装marked；输出仅在_build/html。
 * 不连接网络，不执行文档内代码，不改变产品或人工正文。
 * CHRONAXIS_MARKED_PATH可指定已有marked模块，默认从本地工具安装目录查找。
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// 明确选择版本，禁止把任意路径作为输出目录。
const args = process.argv.slice(2);
if (args.length && (args.length !== 2 || args[0] !== '--edition' || !['M2','M3','Current'].includes(args[1]))) throw new Error('用法: --edition M2|M3|Current');
const edition = args[1] || 'M2';
// 当前版具有独立的信息结构；冻结版本继续使用原渲染规则。
if (edition === 'Current') {
  await import('./render_current_docs.mjs');
  process.exit(0);
}
// 当前版沿用完整手册布局；术语和页脚仍按所选版本明确区分。
const fullManual = edition !== 'M2';
const editionStatus = edition === 'Current' ? '当前能力及验收边界见状态页' : edition === 'M3' ? 'M3能力及验收边界见状态页' : 'M2阶段仍待验证';
const docs = path.join(root, 'Docs', edition);
const output = path.join(docs, '_build/html');
const markedPath = process.env.CHRONAXIS_MARKED_PATH || path.join(docs, '_build/tooling/node_modules/marked/lib/marked.esm.js');
const { marked } = await import(pathToFileURL(markedPath).href);
const escape = (s) => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const slash = (s) => s.replaceAll('\\', '/');
const navigation = [ ['index','概览'], ['terms','术语解释'], ['quickstart','快速上手'], ['expressions','全部表达式'], ['execution','运行参数'], ['inputs','输入数据'], ['concepts','时间与指标'],
  ['configuration','配置说明'], ['api-usage','Python API'], ['migration','CLI与迁移'], ['results','结果与排错'],
  ['examples','完整示例'], ['architecture','架构与流程'], ['status','实际状态'], ['reference/index','全部API'], ['maintenance','文档维护'] ];
if (fullManual) navigation.splice(7,0,['intervals','间隔选择与按需执行'],['results-v2',edition === 'Current' ? '配置3精简结果' : '配置2精简结果'],['rules','八种规则'],['sequences','请求响应'],['presets','四个预设'],['text-inputs','ASC / 报文CSV'],['exports','导出与重采样'],['batch','独立批量任务']);
if (edition === 'Current') {
  navigation.find(([url]) => url === 'concepts')[1] = '时间与计算';
  const configIndex = navigation.findIndex(([url]) => url === 'configuration');
  navigation.splice(configIndex + 1, 0, ['configuration-tools','配置工具'], ['imports','公共定义与独立导出']);
}
const css = `:root{--ink:#182b3a;--muted:#506679;--line:#dbe3e9;--nav:#eef3f7;--accent:#006d78}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:95px}body{margin:0;color:var(--ink);background:#fff;font:16px/1.75 system-ui,'Microsoft YaHei',sans-serif}header{height:72px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:26px;padding:0 28px;background:#fff;position:sticky;top:0;z-index:5}header strong{font-size:23px;letter-spacing:.02em}header small{font-size:12px;color:var(--muted);border:1px solid var(--line);padding:3px 8px;border-radius:5px}.search{margin-left:auto;width:min(440px,42vw);position:relative}input{width:100%;padding:10px 14px;border:1px solid #b6c7d3;border-radius:6px;font:inherit;font-size:14px}.hits{display:none;position:absolute;top:48px;right:0;width:min(620px,85vw);max-height:70vh;overflow:auto;background:white;box-shadow:0 10px 35px #243c5733;border:1px solid var(--line)}.hits a{display:block;padding:10px 14px;border-bottom:1px solid var(--line);text-decoration:none;overflow-wrap:anywhere}.hits small{display:block;border:0;padding:0;font-size:12px}.layout{display:grid;grid-template-columns:228px minmax(0,1fr) 210px;max-width:1600px;margin:auto}nav{background:var(--nav);padding:28px 18px;position:sticky;top:72px;align-self:start;height:calc(100vh - 72px);overflow:auto}nav a{display:block;padding:7px 12px;text-decoration:none;color:#395366;border-radius:5px;font-size:14px}nav a.active{background:#d8e9eb;color:#005d66;font-weight:700}nav p{font-size:12px;padding:0 12px;color:var(--muted)}article{min-width:0;padding:34px 40px 90px}aside{position:sticky;top:72px;align-self:start;max-height:calc(100vh - 72px);overflow:auto;font-size:12px;padding:28px 20px 25px 0}aside a{display:block;color:var(--muted);text-decoration:none;padding:4px 0;overflow-wrap:anywhere}h1{font-size:32px;line-height:1.35;margin:0 0 24px}h2{font-size:23px;margin-top:38px;padding-top:10px;border-top:1px solid var(--line);overflow-wrap:anywhere}h3{font-size:18px;margin-top:25px}a{color:var(--accent);text-underline-offset:3px}p{margin:15px 0}blockquote{margin:20px 0;background:#f0f6f8;border-left:4px solid #40818a;padding:8px 18px;color:#435a6a;font-size:14px}pre{background:#f3f6f9;border:1px solid var(--line);padding:18px;border-radius:6px;overflow:auto;font:13px/1.65 Consolas,monospace}code{font-family:Consolas,monospace;font-size:.9em;overflow-wrap:anywhere}p code,li code,td code{background:#eef3f6;padding:2px 4px;border-radius:3px}table{width:100%;border-collapse:collapse;font-size:14px;margin:22px 0;table-layout:auto}td,th{padding:10px 12px;text-align:left;border:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}td,th{min-width:75px}td:first-child,th:first-child{min-width:105px}th{background:#edf3f7}tr:nth-child(even){background:#fafcfd}li{margin:5px 0}details{border:1px solid var(--line);padding:10px 14px;border-radius:5px}summary{cursor:pointer}footer{margin-top:40px;font-size:12px;color:var(--muted)}.source-line{display:block;white-space:pre}.source-line:target{background:#fff1a8}.num{display:inline-block;width:55px;color:#6b7d8c;user-select:none} @media(max-width:1150px){.layout{grid-template-columns:210px minmax(0,1fr)}aside{display:none}article{padding:28px}} @media(max-width:720px){.layout{display:block}nav{position:static;height:auto;display:flex;flex-wrap:wrap;padding:8px}nav p{display:none}nav a{padding:5px 9px}header{padding:12px;height:auto;gap:8px;flex-wrap:wrap}header small{display:none}.search{width:100%;margin:0}article{padding:25px 16px}h1{font-size:27px}table{font-size:12px}td,th{padding:7px}pre{padding:12px}}`;

/** 遍历正文目录，排除可再生工件。 */
async function collect(directory) {
  const result = [];
  for (const entry of await fs.readdir(directory, {withFileTypes:true})) {
    if (entry.name === '_build') continue;
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) result.push(...await collect(target));
    else if (entry.name.endsWith('.md')) result.push(target);
  }
  return result.sort();
}

/** 使用同一导航框架包装页面；固定样式和搜索脚本均保存在站点内。 */
function shell(title, body, relative, toc) {
  const prefix = slash(path.relative(path.dirname(relative), '.')) || '.';
  const nav = navigation.map(([url,label]) => `<a class="${relative === url+'.html' ? 'active':''}" href="${prefix}/${url}.html">${label}</a>`).join('');
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escape(title)} · Chronaxis ${edition}</title><link rel="stylesheet" href="${prefix}/style.css"></head><body><header><strong>Chronaxis</strong><small>${edition} · ${inventory.baseline.slice(0,7)}</small><div class="search"><input id="search" type="search" aria-label="搜索文档和API" placeholder="搜索模块、类、函数或使用问题…"><div class="hits" id="hits"></div></div></header><div class="layout"><nav><p>使用手册 / API参考</p>${nav}<p>${inventory.modules.length}模块 · ${counts.classes}类 · ${counts.functions}函数<br>${editionStatus}</p></nav><article>${body}<footer>源码基线${inventory.baseline.slice(0,7)} · device_label: ${inventory.device_label} · ${escape(documentationTask)}</footer></article><aside><b>本页目录</b>${toc}</aside></div><script src="${prefix}/search-data.js"></script><script>const prefix=${JSON.stringify(prefix)};${searchCode}</script></body></html>`;
}

const searchCode = `const input=document.getElementById('search'),hits=document.getElementById('hits');input.addEventListener('input',()=>{const q=input.value.trim().toLowerCase();hits.replaceChildren();if(!q){hits.style.display='none';return}const words=q.split(/\\s+/);const found=window.DOC_SEARCH.filter(x=>words.every(w=>(x.title+' '+x.text).toLowerCase().includes(w))).sort((a,b)=>Number(b.title.toLowerCase().endsWith(q))-Number(a.title.toLowerCase().endsWith(q))).slice(0,30);for(const item of found){const a=document.createElement('a');a.href=prefix+'/'+item.url;a.textContent=item.title;const small=document.createElement('small');small.textContent=item.text.slice(0,150);a.append(small);hits.append(a)}if(!found.length)hits.textContent='没有匹配项；可使用完整对象名或中文功能名。';hits.style.display='block'});document.addEventListener('keydown',e=>{if(e.key==='Escape')hits.style.display='none'});`;

await fs.mkdir(output, {recursive:true});
// Wide parameter tables become labelled rows in the app's narrow side panel.
// Ordinary small tables keep their comparison layout; M2 rendering is unchanged.
const narrowTables = fullManual ? `@media(max-width:760px){html{scroll-padding-top:140px}table.parameter-table,table.parameter-table tbody{display:block;width:100%}table.parameter-table thead{display:none}table.parameter-table tr{display:block;margin:14px 0;border:1px solid var(--line);border-radius:5px;overflow:hidden}table.parameter-table td{display:block;width:100%;min-width:0;border:0;padding:7px 12px;overflow-wrap:anywhere}table.parameter-table td+td{border-top:1px solid #edf1f4}table.parameter-table td::before{content:attr(data-label);display:block;font-size:12px;color:var(--muted);font-weight:600;margin-bottom:3px}table.parameter-table td:first-child{background:#edf3f7;font-size:15px}}` : '';
await fs.writeFile(path.join(output,'style.css'), css + narrowTables);
const inventory = JSON.parse(await fs.readFile(path.join(docs,'reference/inventory.json'),'utf8'));
// 页脚跟随本版文档元数据，不能在后续整改后继续显示旧任务号。
const documentationTask = fullManual ? JSON.parse(await fs.readFile(path.join(docs,'documentation.json'),'utf8')).task : 'DOC-M2-02';
const counts = {classes:0,functions:0};
for (const m of inventory.modules) for (const o of m.objects) counts[o.kind === 'class' ? 'classes' : 'functions']++;
const modules = new Map(inventory.modules.map(m=>[path.resolve(root,m.path), m]));
const search = [];
let pages = 0;
for (const file of await collect(docs)) {
  const relative = slash(path.relative(docs,file)).replace(/\.md$/,'.html');
  const text = await fs.readFile(file,'utf8');
  const title = (text.match(/^# (.+)$/m)||[])[1] || relative;
  let body = marked.parse(text, {gfm:true});
  if (fullManual) {
    body = body.replace(/<table>([\s\S]*?)<\/table>/g, (whole, content) => {
      const labels = [...(content.match(/<thead>[\s\S]*?<\/thead>/)?.[0] || '').matchAll(/<th[^>]*>([\s\S]*?)<\/th>/g)]
        .map(match => match[1].replace(/<[^>]+>/g, ''));
      if (labels.length < 5) return whole;
      return '<table class="parameter-table">' + content.replace(/<tr>([\s\S]*?)<\/tr>/g, (row, cells) => {
        let column = 0;
        return '<tr>' + cells.replace(/<td([^>]*)>/g, (_, attrs) => `<td${attrs} data-label="${escape(labels[column++] || '')}">`) + '</tr>';
      }) + '</table>';
    });
  }
  const headings=[]; const used=new Set();
  body=body.replace(/<h([123])>([\s\S]*?)<\/h\1>/g,(_,level,inner)=>{
    let id=inner.replace(/<[^>]+>/g,'').toLowerCase().replace(/[^\p{L}\p{N}_-]+/gu,'-');
    const stem=id;let n=1;while(used.has(id))id=stem+'-'+n++;used.add(id);
    if(level==='2')headings.push(`<a href="#${escape(id)}">${inner}</a>`);
    return `<h${level} id="${escape(id)}">${inner}</h${level}>`;
  });
  body=body.replace(/href="([^"#]+)(#[^"]*)?"/g,(whole,url,hash='')=>{
    if (/^[a-z]+:/i.test(url)) return whole;
    const target=path.resolve(path.dirname(file),decodeURI(url));
    // 正文中的网页入口在导出后仍指向站内，避免嵌入本机绝对路径。
    if(target.startsWith(output+path.sep)){
      return `href="${slash(path.relative(path.dirname(path.join(output,relative)),target))}${hash}"`;
    }
    if(modules.has(target)){
      const m=modules.get(target), newPath=path.join(output,'source',m.module+'.html');
      return `href="${slash(path.relative(path.dirname(path.join(output,relative)),newPath))}${hash}"`;
    }
    if(target.startsWith(docs+path.sep) && !target.includes(path.sep+'_build'+path.sep)){
      const r=slash(path.relative(docs,target));
      return `href="${slash(path.relative(path.dirname(relative),r)).replace(/\.md$/,'.html')}${hash}"`;
    }
    return `href="${pathToFileURL(target).href}${hash}"`;
  });
  const dest=path.join(output,relative); await fs.mkdir(path.dirname(dest),{recursive:true});
  await fs.writeFile(dest,shell(title,body,relative,headings.join('')));
  search.push({title,url:relative,text:text.replace(/[#*`|\n]/g,' ').slice(0,900)});
  pages++;
}
// 为每个具名定义创建直达锚点搜索项；源码来自同一固定Git对象而非工作区。
for(const m of inventory.modules){
  const source=await fs.readFile(path.join(docs,'_build/source',m.path),'utf8');
  if(createHash('sha256').update(source).digest('hex')!==m.sha256)throw new Error('冻结源码哈希不符: '+m.path);
  const relative='source/'+m.module+'.html';
  const body=`<h1>${escape(m.module)}</h1><blockquote>固定源码${inventory.baseline.slice(0,7)}，原样展示；当前工作区可能已有后续修改。</blockquote><pre>${source.split(/\r?\n/).map((line,i)=>`<span class="source-line" id="L${i+1}"><a class="num" href="#L${i+1}">${i+1}</a>${escape(line)}</span>`).join('')}</pre>`;
  await fs.mkdir(path.join(output,'source'),{recursive:true});
  await fs.writeFile(path.join(output,relative),shell(m.module,body,relative,''));
  for(const obj of m.objects){
    search.push({title:m.module+'.'+obj.name,url:'reference/'+m.module+'.html#api-'+obj.name.replaceAll('.','-'),text:(obj.summary||obj.kind)+' · 参数/字段 '+(obj.parameters||obj.fields||[]).map(p=>p.name).join(' ')});
  }
}
// 附件使用本地副本，双击网页也能读取，无需fetch或服务器。
await fs.cp(path.join(docs,'examples'),path.join(output,'examples'),{recursive:true});
if (fullManual) await fs.copyFile(path.join(docs,'documentation.json'),path.join(output,'documentation.json'));
await fs.copyFile(path.join(docs,'annotations.json'),path.join(output,'annotations.json'));
await fs.copyFile(path.join(docs,'reference-language.json'),path.join(output,'reference-language.json'));
await fs.copyFile(path.join(docs,'reference/inventory.json'),path.join(output,'reference/inventory.json'));
await fs.writeFile(path.join(output,'search-data.js'),'window.DOC_SEARCH='+JSON.stringify(search).replaceAll('<','\\u003c')+';');
console.log(JSON.stringify({pages,sourcePages:inventory.modules.length,searchItems:search.length,output}));
