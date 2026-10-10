import Link from 'next/link';
import {Catalog} from './lib';
const states:Record<string,string>={verified:'已验证',partially_verified:'部分验证',unverified:'未验证',synthetic:'开发合成数据',unsupported:'不支持'};
export default function DataSummary({catalog}:{catalog?:Catalog}){
 if(!catalog)return null;
 const d=catalog.data_readiness;
 return <section className="notice data-summary" aria-label="数据验证状态"><div className="row"><strong>{catalog.game} · {states[catalog.verification_status]} / {catalog.verification_status.toUpperCase()}</strong><Link href="/data">来源与校验 ↗</Link></div>{catalog.verification_status==='synthetic'?<p>开发用独立合成示例，不代表真实游戏版本。仅用于测试。</p>:<><p>赛季：{d?.set_name}（Set {catalog.set}） · 补丁：{catalog.patch} · 模式：{catalog.mode}<br/>资源版本：{d?.resource_patch} · 最后核查：{d?.last_verified_at?.slice(0,10)||'未核查'} · 棋子可用覆盖：{Math.round((d?.completeness||0)*100)}%</p><p>来源：{catalog.source}</p><p>{d?.scope}</p><details><summary>不支持或受限制的机制（{d?.unsupported_mechanics.length||0}）</summary><ul>{d?.unsupported_mechanics.map(m=><li key={m}>{m}</li>)}</ul></details>{!d?.optimization_enabled&&<strong>关键规则未经验证，真实游戏优化已禁用。</strong>}</>}</section>
}
