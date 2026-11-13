/** 回归附件链接改写及独立Markdown导航解析；只验证内存文本，不改变手册文件。 */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {references,rewriteLinks} from './manual_markdown.mjs';

const sample='# 配置说明\n\n<a id="config-detail"></a>\n[字段`dataset.domain`](../Current/fast-energy.md#usage)\n[版本][version]\n\n[version]: versioning.md\n\n`[不改](code.md)`\n```yaml\ntext: "[不是导航](missing.md)"\n```\n';
const changed=rewriteLinks(sample,url=>url.replace('../Current/fast-energy.md','../../../fast-energy.html'));
assert(changed.includes('[字段`dataset.domain`](../../../fast-energy.html#usage)'));
assert(changed.includes('`[不改](code.md)`'));
assert(changed.includes('text: "[不是导航](missing.md)"'));
const parsed=references(changed);
assert.deepEqual(parsed.links,['../../../fast-energy.html#usage','versioning.md']);
assert(parsed.ids.includes('config-detail')&&parsed.ids.includes('配置说明'));
assert.deepEqual(references('# Same\n# Same\n').ids,['same','same-1']);
assert.deepEqual(references('![图](image.png)\n<a href="target.html#part">目标</a>').links,['image.png','target.html#part']);
const move=url=>'moved/'+url;
const cases=[
  ['[版本](versioning.md "版本规则")','[版本](moved/versioning.md "版本规则")'],
  ['[版本](<versioning.md> "版本规则")','[版本](<moved/versioning.md> "版本规则")'],
  ['[v][ref]\n\n[ref]: <versioning.md> "规则"','[v][ref]\n\n[ref]: <moved/versioning.md> "规则"'],
  ['    [不是导航](keep.md)\n\n[真实](keep.md)','    [不是导航](keep.md)\n\n[真实](moved/keep.md)'],
  ['> ```text\n> [不是导航](keep.md)\n> ```\n\n> [真实](keep.md)','> ```text\n> [不是导航](keep.md)\n> ```\n\n> [真实](moved/keep.md)'],
  ['- 条目\n  ```text\n  [不是导航](keep.md)\n  ```\n- [真实](keep.md)','- 条目\n  ```text\n  [不是导航](keep.md)\n  ```\n- [真实](moved/keep.md)'],
  ['``[不改`字段`](keep.md)`` [真实](next.md)','``[不改`字段`](keep.md)`` [真实](moved/next.md)'],
  ['[![图](image.png)](page.md "页面")','[![图](moved/image.png)](moved/page.md "页面")'],
  ['[文件](part(one).md)','[文件](moved/part(one).md)'],
  ['[版本](versioning.md)\r\n\r\n```text\r\n[原文](keep.md)\r\n```','[版本](moved/versioning.md)\r\n\r\n```text\r\n[原文](keep.md)\r\n```'],
];
for(const [input,expected] of cases)assert.equal(rewriteLinks(input,move),expected);
assert.equal(rewriteLinks('[版本](<part name.md>)',move),'[版本](<moved/part name.md>)');
// 执行实际渲染器的纯定位函数，不启动整个HTML构建；防止约束链接漏装或过度放行。
const renderer=readFileSync(new URL('./render_current_docs.mjs',import.meta.url),'utf8').replaceAll('\r\n','\n');
const destinationStart=renderer.indexOf('function destination(target){');
const destinationEnd=renderer.indexOf('\n}\n',destinationStart)+2;
assert(destinationStart>=0&&destinationEnd>destinationStart);
const attachmentRoot=path.resolve('manual-attachment-boundary');
const attachmentDocs=path.join(attachmentRoot,'Docs/Current');
const attachmentOutput=path.join(attachmentDocs,'_build/html');
const collected=new Map();
const resolveDestination=vm.runInNewContext('('+renderer.slice(destinationStart,destinationEnd)+')',{
  root:attachmentRoot,docs:attachmentDocs,output:attachmentOutput,path,
  sourceMap:new Map(),attachments:collected,
  slash:value=>value.replaceAll('\\','/'),htmlName:value=>value.replace(/\.md$/,'.html'),
});
const publishedRequirements=['README.md','constraints-windows-py312-min.txt','constraints-windows-py312-max.txt',
  'constraints-windows-py313-min.txt','constraints-windows-py313-max.txt'];
for(const name of publishedRequirements){
  const source=path.join(attachmentRoot,'requirements',name);
  const expected=path.join(attachmentOutput,'attachments/requirements',name);
  assert.equal(resolveDestination(source),expected);
  assert.equal(collected.get(source),expected);
}
const rejectedRequirements=['requirements/private.txt','requirements/requirements.txt','requirements/nested/README.md',
  'requirements/../private.txt','requirements-backup/README.md'];
for(const name of rejectedRequirements)assert.throws(()=>resolveDestination(path.resolve(attachmentRoot,name)),/文档附件超出公开范围/);
assert.equal(resolveDestination(path.join(attachmentRoot,'Docs/Release/release-notes-0.1.0.dev4.md')),
  path.join(attachmentOutput,'attachments/Docs/Release/release-notes-0.1.0.dev4.md'));
console.log(JSON.stringify({checks:8+cases.length+1+publishedRequirements.length*2+rejectedRequirements.length+1,status:'passed'}));
