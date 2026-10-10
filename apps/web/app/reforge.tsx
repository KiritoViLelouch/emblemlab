'use client';
import {useEffect, useState} from 'react';
import {api, Catalog, errorText, Result} from './lib';
import CandidateCard from './candidate';

type Law = {id:string;name:string;game:string;patch:string;set:string;mode:string;source:string;verification_status:string;probability_status:'unknown'|'verified';draw_policy:string;reforgers_per_target:number;max_targets:number};
type Probability = {numerator:number;denominator:number;value:number}|null;
type Evaluation = {emblem_ids:string[];status:string;score:number|null;result:Result|null};
type Summary = {expected_value:number|null;expected_delta:number|null;worst_case_score:number|null;best_case_score:number|null;maximum_downside:number|null;probability_of_loss:Probability;expected_downside:number|null;infeasible_outcomes:number;unresolved_outcomes:number;uncertainty:string[]};
type Action = {target_order:number[];legal:boolean;reason:string|null;reforgers_used:number;summary:Summary|null;outcomes:{emblem_ids:string[];evaluation_id:string;probability:Probability}[]};
type Analysis = {rule:Law;baseline_evaluation_id:string;strategies:{retained_indices:number[];legal:boolean;reason:string|null;actions:Action[]}[];evaluations:Record<string,Evaluation>;evaluation_complete:boolean;all_compositions_proven_optimal:boolean;elapsed_seconds:number};
const reasons:Record<string,string> = {locked_emblem:'包含锁定纹章',target_limit:'超出规则目标数量',insufficient_reforgers:'重铸器不足',target_not_permitted:'目标纹章不允许重铸',reachable_empty_pool:'部分可能路径会遇到空结果池',outcome_violates_duplicate_rule:'可能违反重复纹章限制',no_order_can_complete_all_outcomes:'没有能在所有结果下完成的固定顺序'};
const uncertainties:Record<string,string> = {probabilities_unknown:'概率未知',not_all_outcomes_have_proven_optimal_compositions:'部分结果无最优性证明或无可行阵容',baseline_not_proven_optimal:'重铸前阵容尚未证明最优'};
const number = (v:number|null) => v===null?'未知':v.toLocaleString('zh-CN',{maximumFractionDigits:3});
const probability = (p:Probability) => p?`${p.numerator}/${p.denominator}（${(100*p.value).toFixed(2)}%）`:'未知';

export default function ReforgePanel({catalog,request,slots,lockedIndices,busy,onBusyChange}:{catalog?:Catalog;request:unknown;slots:number[];lockedIndices:number[];busy:boolean;onBusyChange:(busy:boolean)=>void}) {
 const [laws,setLaws]=useState<Law[]>([]),[lawId,setLawId]=useState(''),[charges,setCharges]=useState(3),[analysis,setAnalysis]=useState<Analysis>(),[error,setError]=useState(''),[selected,setSelected]=useState('');
 const requestKey=JSON.stringify(request), lockKey=JSON.stringify(lockedIndices);
 useEffect(()=>{
  let active=true;setLaws([]);setLawId('');setError('');
  if(catalog)api<Law[]>(`/api/v1/reforge/rules?game_id=${catalog.game}&ruleset_id=${catalog.id}`).then(rows=>{if(active){setLaws(rows);setLawId(rows.find(r=>r.probability_status==='unknown')?.id||rows[0]?.id||'')}}).catch(e=>{if(active)setError(errorText(e))});
  return()=>{active=false};
 },[catalog]);
 useEffect(()=>{setAnalysis(undefined);setSelected('');setError('')},[requestKey,lockKey,charges,lawId]);
 const law=laws.find(l=>l.id===lawId);
 const emblemNames=(ids:string[])=>ids.map(id=>catalog?.emblems.find(e=>e.id===id)?.zh_CN||id).join('、')||'无纹章';
 const slotNames=(indices:number[])=>indices.map(i=>(slots[i]??i)+1).join('、')||'无';
 async function run(){
  onBusyChange(true);setError('');setAnalysis(undefined);setSelected('');
  try {setAnalysis(await api<Analysis>('/api/v1/reforge/analyze',{...JSON.parse(requestKey),reforge_rule_id:lawId,available_reforgers:charges,locked_emblem_indices:JSON.parse(lockKey),analysis_timeout_seconds:20,top_k:1}))}
  catch(e){setError(errorText(e))}finally{onBusyChange(false)}
 }
 const before=analysis?.evaluations[analysis.baseline_evaluation_id];
 const chosen=analysis?.evaluations[selected];
 return <section className="panel reforge-panel" aria-label="重铸情景分析">
  <div className="section-title"><h2>重铸情景分析</h2><span className="badge">版本隔离 · CP-SAT</span></div>
  <p>沿用左侧纹章、棋盘和棋子约束。枚举所有保留子集及固定重铸顺序；每枚目标最多重铸一次。</p>
  <fieldset disabled={busy}><div className="two"><div><label htmlFor="reforge-law">重铸规则</label><select id="reforge-law" value={lawId} onChange={e=>setLawId(e.target.value)}>{!laws.length&&<option value="">此版本无可用规则</option>}{laws.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></div><div><label htmlFor="reforge-charges">可用重铸器</label><select id="reforge-charges" value={charges} onChange={e=>setCharges(+e.target.value)}>{[0,1,2,3].map(n=><option key={n}>{n}</option>)}</select></div></div>
   {law&&<p className="meta">{law.game} · {law.patch} · {law.mode}<br/>{law.verification_status==='synthetic'?'合成规则演示，不代表真实游戏机制。':'已审阅版本规则。'}{law.probability_status==='unknown'?'概率未知：仅展示情景，不计算期望值。':law.verification_status==='synthetic'?'概率仅在合成规则内已知。':'概率已验证。'} 每枚消耗 {law.reforgers_per_target} 个重铸器。{law.draw_policy==='independent'?'各次独立抽取。':'每一步排除其他实例已持有的纹章，再按规则条件抽取。'}</p>}
   <button className="secondary" disabled={busy||!catalog||!law} onClick={run}>分析全部合法重铸策略</button>
  </fieldset>
  {error&&<p className="error" role="alert">{error}</p>}
  {analysis&&before&&<div className="reforge-results" aria-live="polite">
   <p className="meta">枚举完成 · {analysis.strategies.filter(s=>s.legal).length} / {analysis.strategies.length} 个合法保留策略 · {Object.keys(analysis.evaluations).length} 个独立库存 · {analysis.elapsed_seconds.toFixed(2)} 秒</p>
   {(!analysis.evaluation_complete||!analysis.all_compositions_proven_optimal)&&<div className="notice">部分求解未完成、无可行阵容或未证明最优。缺失结果不补零；涉及这些结果的期望值与完整范围不可用。</div>}
   <h3>1. 重铸前阵容价值</h3><p>原始纹章全部可用时的阵容估分：<strong>{number(before.score)}</strong> · {before.status}。这不是对当前实战棋盘的估值。</p>
   {before.result?.candidates[0]&&<details><summary>查看重铸前阵容与分配</summary><p>纹章编号顺序：{emblemNames(before.emblem_ids)}</p><CandidateCard c={before.result.candidates[0]} index={0} catalog={catalog}/></details>}
   <h3>2. 合法动作与可能结果</h3><p>保留不等于必须装备。每个结果都允许重新优化整个阵容与持有者；不含换阵成本、重铸器机会成本或真实胜率。</p>
   {analysis.strategies.map(s=><details className="reforge-strategy" key={s.retained_indices.join(',')}><summary>保留槽位 {slotNames(s.retained_indices)} · {s.legal?`${s.actions.filter(a=>a.legal).length} 个合法顺序`:`不可执行：${reasons[s.reason||'']||s.reason}`}</summary>
    {s.actions.map(a=><article className="reforge-action" key={a.target_order.join(',')}>
     <h4>{a.target_order.length?`重铸顺序 ${a.target_order.map(i=>(slots[i]??i)+1).join(' → ')}`:'不重铸'} · 消耗 {a.reforgers_used}</h4>
     {!a.legal&&<p>不可执行：{reasons[a.reason||'']||a.reason}</p>}
     {a.summary&&<><p>阵容估分范围：{number(a.summary.worst_case_score)} ～ {number(a.summary.best_case_score)}。最大下行损失：{number(a.summary.maximum_downside)}。</p>
      <p>{a.summary.expected_value===null?'期望值不可用。':`期望规则估分 ${number(a.summary.expected_value)} · 相对重铸前 ${number(a.summary.expected_delta)}。`}{a.summary.probability_of_loss&&`低于重铸前的概率 ${probability(a.summary.probability_of_loss)} · 期望下行损失 ${number(a.summary.expected_downside)}。`}</p>
      <p className="meta">{a.summary.uncertainty.map(u=>uncertainties[u]||u).join('；')||'所有结果均已证明最优；期望值仅针对所选规则估分。'} 无解 {a.summary.infeasible_outcomes} · 尚未确定最优 {a.summary.unresolved_outcomes}</p>
      <ul className="reforge-outcomes">{a.outcomes.map(o=><li key={o.evaluation_id}><span>{emblemNames(o.emblem_ids)}<br/><small>概率 {probability(o.probability)} · 估分 {number(analysis.evaluations[o.evaluation_id].score)} · {analysis.evaluations[o.evaluation_id].status}</small></span><button className="secondary" aria-pressed={selected===o.evaluation_id} onClick={()=>setSelected(o.evaluation_id)}>查看阵容</button></li>)}</ul>
     </>}
    </article>)}
   </details>)}
   {chosen&&<div className="reforge-composition"><h3>3. 所选结果阵容</h3><p>纹章编号顺序：{emblemNames(chosen.emblem_ids)} · {chosen.status}</p>{chosen.result?.candidates[0]?<CandidateCard c={chosen.result.candidates[0]} index={0} catalog={catalog}/>:<p>此结果暂无可展示的可行阵容。</p>}</div>}
   <details><summary>不确定性与规则来源</summary><p>完整范围和下行损失仅在所有结果均证明最优时显示。期望值还要求规则内概率已验证；不以均匀分布代替未知概率。无解没有人为惩罚分数。固定顺序若存在无法继续的路径，则整条计划不可执行。</p><p>来源：{analysis.rule.source}。规则 {analysis.rule.id} · {analysis.rule.set}。保留锁定按原始槽位；结果中的纹章编号按该结果库存排序。</p></details>
  </div>}
 </section>
}
