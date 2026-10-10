import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';
import {PUBLIC_DEMO} from './lib';
export const metadata: Metadata = {title:'EmblemLab · 纹章实验室',description:'版本化真实静态数据 · 离线纹章羁绊优化'};
export default function Layout({children}:{children:React.ReactNode}) {
 return <html lang="zh-CN"><body><header><Link className="brand" href="/">⬡ <span>Emblem<span className="accent">Lab</span><small>纹章实验室</small></span></Link><nav aria-label="主导航"><Link href="/">阵容优化</Link><Link href="/catalog">数据图鉴</Link><Link href="/compare">阵容对比</Link>{!PUBLIC_DEMO&&<Link href="/guides">社区攻略</Link>}<Link href="/data">数据状态</Link><Link href="/about">方法说明</Link></nav><span className="online">● 离线策略实验室</span></header><main>{PUBLIC_DEMO&&<div className="notice" role="note"><strong>朋友测试版 · 已审核的固定版本</strong><p>游戏是否可用以独立审核的数据版本为准。结果为静态羁绊规则估分，不代表胜率；数据和特殊机制的限制见「数据状态」。共享求解服务忙时请稍后重试。</p></div>}{children}</main><footer>EmblemLab / 社区资料导入　·　仅供赛前假设分析、训练与复盘。固定版本静态数据与开发示例分别标识；规则估分不代表胜率，无官方背书。</footer></body></html>
}
