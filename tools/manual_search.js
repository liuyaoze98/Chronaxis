/** 离线全文搜索：纯查询函数与键盘界面共用；不发起网络请求。 */
(function(global){
  function searchEntries(entries,query,category='user'){
    const words=query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if(!words.length)return [];
    return entries.filter(item=>(category==='all'||category==='user'&&item.category!=='internal'||category===item.category)&&words.every(word=>(item.title+' '+item.text).toLowerCase().includes(word)))
      .map(item=>({item,score:words.reduce((n,w)=>n+(item.title.toLowerCase().includes(w)?10:0),0)}))
      .sort((a,b)=>b.score-a.score||a.item.title.localeCompare(b.item.title,'zh-CN')).map(x=>x.item);
  }
  function snippet(text,query,width=190){
    const words=query.toLowerCase().split(/\s+/).filter(Boolean),lower=text.toLowerCase();
    const positions=words.map(w=>lower.indexOf(w)).filter(x=>x>=0);
    const start=Math.max(0,(positions.length?Math.min(...positions):0)-55);
    return (start?'…':'')+text.slice(start,start+width)+(start+width<text.length?'…':'');
  }
  global.DOC_SEARCH_API={searchEntries,snippet};
  if(typeof document==='undefined')return;
  const english=document.documentElement.lang==='en';
  const input=document.getElementById('search'),hits=document.getElementById('hits');
  const category=document.getElementById('search-category');
  let found=[],limit=30;
  function close(){hits.style.display='none';input.setAttribute('aria-expanded','false')}
  function paint(){
    hits.replaceChildren();
    const status=document.createElement('p');status.className='search-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    status.textContent=english?(found.length?`${found.length} results; showing ${Math.min(limit,found.length)}`:'No matches. Try another category or fewer keywords.'):(found.length?`找到 ${found.length} 项，显示 ${Math.min(limit,found.length)} 项`:'没有匹配项；可切换类别或减少关键词。');hits.append(status);
    for(const item of found.slice(0,limit)){
      const a=document.createElement('a');a.href=prefix+'/'+item.url;a.textContent=item.title;
      const small=document.createElement('small');small.textContent=snippet(item.text,input.value);a.append(small);hits.append(a);
    }
    if(limit<found.length){const more=document.createElement('button');more.type='button';more.textContent=english?'Show more results':'显示更多结果';more.addEventListener('click',()=>{const previous=limit;limit+=30;paint();hits.querySelectorAll('a')[previous]?.focus()});hits.append(more)}
    hits.style.display='block';input.setAttribute('aria-expanded','true');
  }
  function update(){if(!input.value.trim()){close();return}found=searchEntries(global.DOC_SEARCH.filter(item=>(item.language||'zh')===(english?'en':'zh')),input.value,category.value);limit=30;paint()}
  input.addEventListener('input',update);category.addEventListener('change',update);
  input.addEventListener('keydown',event=>{if((event.key==='ArrowDown'||event.key==='Enter')&&hits.style.display==='block'){event.preventDefault();hits.querySelector('a')?.focus()}});
  hits.addEventListener('keydown',event=>{
    const links=[...hits.querySelectorAll('a,button')],idx=links.indexOf(document.activeElement);
    if(event.key==='ArrowDown'){event.preventDefault();links[Math.min(idx+1,links.length-1)]?.focus()}
    if(event.key==='ArrowUp'){event.preventDefault();if(idx<=0)input.focus();else links[idx-1]?.focus()}
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){close();if(hits.contains(document.activeElement))input.focus()}if(event.key==='/'&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName||'')){event.preventDefault();input.focus()}});
  document.addEventListener('click',event=>{if(!event.target.closest('.search'))close()});
})(globalThis);
