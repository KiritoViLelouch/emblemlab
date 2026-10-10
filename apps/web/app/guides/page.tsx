'use client';
import {useEffect,useState} from 'react';
import {API,api,Catalog,errorText} from '../lib';

type Values={emblem_name?:string;emblem_icon_ref?:string;recommended_holders?:string;composition_aliases?:string;notes?:string;label_status?:string};
type Row={id:string;row_number:number;revision:number;raw:Values;current:Values&{status:string;issues:string[];emblem_id:string|null;holders:{label:string;champion_id:string|null}[];aliases:string[]};history:{at:string;reviewer:string;note:string;revision:number;before:Values;after:Values}[]};
type Batch={id:string;game_id:string;ruleset_id:string;source_title:string;source_url:string|null;attribution:string;license_status:string;filename:string;patch:string;set:string;mode:string;imported_at:string;row_count:number;rows:Row[]};
type Game={id:string;name:string;versions:{ruleset_id:string;name:string}[]};
const statuses:Record<string,string>={needs_review:'待人工校正',matched:'已匹配 · 未核验',reviewed:'人工已确认映射'};
async function send<T>(path:string,init:RequestInit):Promise<T>{
 let response:Response;try{response=await fetch(API+path,init)}catch{throw Error('无法连接后端 API：'+API)}
 const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;
}

function Editor({row,batch,catalog,onSaved,onBusyChange,disabled}:{row:Row;batch:Batch;catalog:Catalog;onSaved:(b:Batch)=>void;onBusyChange:(busy:boolean)=>void;disabled:boolean}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function save(event:React.FormEvent<HTMLFormElement>){
  event.preventDefault();const form=new FormData(event.currentTarget);setBusy(true);onBusyChange(true);setError('');
  try{onSaved(await send<Batch>(`/api/v1/guides/${batch.id}/rows/${encodeURIComponent(row.id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({...Object.fromEntries(form),expected_revision:row.revision,confirm:form.get('confirm')==='on'})}))}catch(e){setError(errorText(e))}finally{setBusy(false);onBusyChange(false)}
 }
 return <article className="panel guide-row"><div className="section-title"><h3>源文件第 {row.row_number} 行</h3><span className="badge">{statuses[row.current.status]}</span></div>
 <p>纹章映射：{row.current.emblem_id||'未匹配'}<br/>推荐持有者：{row.current.holders.map(h=>`${h.label} → ${h.champion_id||'未匹配'}`).join('；')||'未提供'}<br/>阵容别名：{row.current.aliases.join(' / ')||'未提供'}</p>
 {row.current.issues.length>0&&<ul className="guide-issues">{row.current.issues.map(issue=><li key={issue}>{issue}</li>)}</ul>}
 <details><summary>查看原始行与校正记录（修订 {row.revision}）</summary><pre>{JSON.stringify(row.raw,null,2)}</pre>{row.history.map(h=><div key={h.revision}><p>{h.at} · {h.reviewer} · {h.note}</p><pre>{JSON.stringify({before:h.before,after:h.after},null,2)}</pre></div>)}</details>
 <details><summary>人工校正标签与推荐</summary><form onSubmit={save}><fieldset disabled={busy||disabled} className="guide-fields">
 <label>纹章名称或当前版本 ID<input name="emblem_name" list={"guide-emblems-"+row.id} defaultValue={row.current.emblem_name||''}/></label>
 <datalist id={"guide-emblems-"+row.id}>{catalog.emblems.map(e=><option key={e.id} value={e.id}>{e.zh_CN} / {e.en_US}</option>)}</datalist>
 <label>图标引用（仅保存文本）<input name="emblem_icon_ref" defaultValue={row.current.emblem_icon_ref||''}/></label>
 <label>推荐持有者（用 | 分隔）<input name="recommended_holders" defaultValue={row.current.recommended_holders||''}/></label>
 <details><summary>当前版本棋子名称和 ID</summary><p>{catalog.champions.map(u=>`${u.zh_CN} (${u.id})`).join('；')}</p></details>
 <label>阵容别名（用 | 分隔）<input name="composition_aliases" defaultValue={row.current.composition_aliases||''}/></label>
 <label>备注<textarea name="notes" defaultValue={row.current.notes||''}/></label>
 <div className="guide-columns"><label>校正人<input name="reviewer" required maxLength={200}/></label><label>校正依据<input name="correction_note" required maxLength={1000}/></label></div>
 <label className="guide-check"><input name="confirm" type="checkbox"/>我已核对映射与当前版本规则</label>
 <small>不勾选可保存草稿。人工确认只核验标签映射，不代表胜率或强度。</small><button type="submit">{busy?'保存中…':'保存校正'}</button>
 </fieldset></form>{error&&<div role="alert" className="error">{error}。修订冲突时请重新打开此导入。</div>}</details></article>;
}

function GuideWorkspace(){
 const [games,setGames]=useState<Game[]>([]),[game,setGame]=useState('TFT'),[ruleset,setRuleset]=useState('fixture_tft_v1');
 const [catalog,setCatalog]=useState<Catalog|null>(null),[imports,setImports]=useState<Batch[]>([]),[batch,setBatch]=useState<Batch|null>(null);
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState('');
 useEffect(()=>{let active=true;api<Game[]>('/api/v1/games').then(data=>{if(active)setGames(data)}).catch(e=>{if(active)setError(errorText(e))});return()=>{active=false}},[]);
 useEffect(()=>{let active=true;setLoading(true);setCatalog(null);setBatch(null);setImports([]);setError('');Promise.all([api<Catalog>(`/api/v1/catalog?game_id=${game}&ruleset_id=${ruleset}`),api<Batch[]>(`/api/v1/guides?game_id=${game}&ruleset_id=${ruleset}`)]).then(([c,b])=>{if(active){setCatalog(c);setImports(b)}}).catch(e=>{if(active)setError(errorText(e))}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[game,ruleset]);
 async function upload(event:React.FormEvent<HTMLFormElement>){event.preventDefault();const data=new FormData(event.currentTarget);data.set('game_id',game);data.set('ruleset_id',ruleset);setBusy(true);setError('');try{const b=await send<Batch>('/api/v1/guides/import',{method:'POST',body:data});setBatch(b);setImports(await api<Batch[]>(`/api/v1/guides?game_id=${game}&ruleset_id=${ruleset}`))}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 async function open(id:string){setBusy(true);setError('');setBatch(null);try{setBatch(await api<Batch>('/api/v1/guides/'+id))}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 return <><div className="eyebrow">COMMUNITY GUIDES / 社区资料</div><h1>导入社区攻略</h1><p>保存推荐、出处与人工校正。社区观点独立于对局统计，不参与优化器评分。</p>
 <div className="notice">仅使用你有权提供的资料。当前可选版本为合成示例；图标引用不会被下载或自动识别。</div>
 <fieldset disabled={busy||loading} className="toolbar"><label>游戏<select value={game} onChange={e=>{const g=games.find(g=>g.id===e.target.value);if(g){setGame(g.id);setRuleset(g.versions[0].ruleset_id)}}}>{games.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label><label>规则版本<select value={ruleset} onChange={e=>setRuleset(e.target.value)}>{games.find(g=>g.id===game)?.versions.map(v=><option key={v.ruleset_id} value={v.ruleset_id}>{v.name}</option>)}</select></label></fieldset>
 <div className="guide-columns"><section className="panel"><h2>上传 CSV / XLSX</h2><p>第一行为英文列名；名称、图标引用、推荐持有者和阵容别名均为文本。多个推荐或别名用 | 分隔。</p>
 <details><summary>导入格式与限制</summary><p>emblem_name（必需列）；emblem_icon_ref、recommended_holders、composition_aliases、label_status、notes（可选列）。每行须提供名称或图标引用。label_status 仅接受 unverified 或 uncertain。UTF-8 CSV / XLSX，最多 5 MiB、1000 行、6 列；拒绝公式、统计列和非文本单元格。多工作表 XLSX 须指定表名。</p></details>
 <form onSubmit={upload}><fieldset disabled={busy||loading||!catalog} className="guide-fields">
 <label>文件<input name="file" type="file" accept=".csv,.xlsx" required/></label>
 <label>XLSX 工作表（单表可留空）<input name="sheet" maxLength={100}/></label>
 <label>来源标题<input name="source_title" required maxLength={300}/></label>
 <label>来源链接（可选）<input name="source_url" type="url" placeholder="https://…"/></label>
 <label>作者 / 署名<input name="attribution" required maxLength={1000}/></label>
 <label>授权状态<select name="license_status" defaultValue="unknown"><option value="unknown">未核实授权</option><option value="original">本人原创</option><option value="authorized">已获授权</option></select></label>
 <button type="submit">{busy?'处理中…':'导入并检查标签'}</button></fieldset></form></section>
 <section className="panel"><h2>当前版本导入记录</h2>{loading?<p role="status">加载中…</p>:imports.length===0?<p>暂无导入记录</p>:imports.map(b=><button className="guide-import" disabled={busy} key={b.id} onClick={()=>open(b.id)} aria-pressed={batch?.id===b.id}><strong>{b.source_title}</strong><small>{b.filename} · {b.row_count} 行 · {b.attribution}</small></button>)}</section></div>
 {error&&<div role="alert" className="error">{error}</div>}
 {batch&&catalog&&<section className="guide-results"><h2>{batch.source_title} <span className="badge">社区推荐 · 非对局统计</span></h2><p>署名：{batch.attribution} · 授权：{batch.license_status}<br/>版本：{batch.game_id} / {batch.patch} / {batch.set} / {batch.mode}<br/>导入时间：{batch.imported_at}{batch.source_url&&<><br/>来源：<a href={batch.source_url} target="_blank" rel="noreferrer">{batch.source_url}</a></>}</p><p>{batch.rows.filter(r=>r.current.status==='needs_review').length} 行待校正。精确匹配不会自动成为已核验资料。</p>{batch.rows.map(row=><Editor key={row.id+':'+row.revision} row={row} batch={batch} catalog={catalog} onSaved={setBatch} onBusyChange={setBusy} disabled={busy}/>)}</section>}
 </>;
}

export default function Page(){return process.env.NEXT_PUBLIC_PUBLIC_DEMO==='true'?<div className="notice">朋友测试版暂不开放社区资料上传和修改。</div>:<GuideWorkspace/>}
