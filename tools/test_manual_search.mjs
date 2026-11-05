/** 核对真实全文索引和查询逻辑；不声称执行过浏览器键盘/剪贴板测试。 */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import './manual_search.js';
const context={};vm.createContext(context);context.window=context;
vm.runInContext(await fs.readFile(new URL('../Docs/Current/_build/html/search-data.js',import.meta.url),'utf8'),context);
const entries=context.DOC_SEARCH,{searchEntries,snippet}=globalThis.DOC_SEARCH_API;
for(const query of ['hysteresis','isclose','same_time_policy','spool_quota_bytes']){
  const found=searchEntries(entries,query,'guide');
  assert.ok(found.length>0,query);assert.ok(found.every(x=>x.category==='guide'));
}
assert.ok(searchEntries(entries,'AnalysisResult.iter_events','api').length);
assert.ok(searchEntries(entries,'self','internal').length);
assert.equal(searchEntries(entries,'原文曾称','guide').length,0);
assert.ok(!searchEntries(entries,'AnalysisResult','user').some(x=>x.category==='internal'));
const late='开头 '.repeat(600)+'目标字段 后续内容';
assert.ok(snippet(late,'目标字段').includes('目标字段'));
assert.equal(searchEntries(Array.from({length:65},(_,i)=>({title:'测试 '+i,text:'完整文本',category:'guide'})),'测试').length,65);
assert.ok(entries.every(x=>!x.text.includes('DOC-CURRENT-01')));
// 真实正文含通道键引号；生成索引必须还原实体，界面仍使用textContent。
const binding=entries.find(x=>x.url.includes('activity-tutorial.html#')&&x.text.includes('dbc_by_channel'));
assert.ok(binding&&binding.text.includes("'1'"));
assert.ok(!snippet(binding.text,'dbc_by_channel',400).includes('&#x27;'));
const english=entries.filter(x=>x.language==='en');
for(const query of ['hysteresis','valid_for','energy','frame_id']){
  const found=searchEntries(english,query);assert.ok(found.length,query);assert.ok(found.every(x=>x.url.startsWith('en/')));
}
assert.ok(searchEntries(english,'AnalysisResult.iter_events','api').length);
// 正式名称、英文名称和配置/API拼写应能找到同一功能的使用章节。
const capabilities=[
  ['时序变换','temporal-transforms.html'],['temporal transforms','en/temporal-transforms.html'],
  ['transforms','temporal-transforms.html'],['宿主扩展','host-extensions.html'],
  ['host extensions','en/host-extensions.html'],['ExtensionRegistry','host-extensions.html'],
  ['统计','aggregations.html'],['aggregations','en/aggregations.html'],
  ['window_delta','temporal-transforms.html'],
];
for(const [query,page] of capabilities){
  assert.ok(searchEntries(entries,query).some(hit=>hit.url.split('#')[0]===page),`${query} → ${page}`);
}
console.log(JSON.stringify({indexEntries:entries.length,englishEntries:english.length,checks:17+capabilities.length,status:'passed'}));
