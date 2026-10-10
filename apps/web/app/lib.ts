export type Unit={id:string;zh_CN:string;en_US:string;traits:string[];cost:number;available?:boolean;board_slots?:number;icon_path?:string;verification_status?:string};
export type Trait={id:string;zh_CN:string;en_US:string;thresholds:{count:number;utility:number}[];supported?:boolean;icon_path?:string;verification_status?:string};
export type Emblem={id:string;zh_CN:string;en_US:string;aliases:string[];trait_id:string;available?:boolean;icon_path?:string;verification_status?:string};
export type Game={id:string;name:string;versions:{patch:string;ruleset_id:string;name:string;set:string;verification_state:string;optimization_enabled:boolean}[]};
export type Readiness={set_name:string;resource_patch:string;build_version:string;last_verified_at:string|null;live_as_of:string|null;optimization_enabled:boolean;scope:string;completeness:number;unsupported_mechanics:string[];snapshots:{filename:string;url:string;sha256:string}[];rule_checks:{id:string;status:string;essential:boolean;notes:string;evidence:string[]}[]};
export type Catalog={id:string;game:string;patch:string;zh_CN:string;champions:Unit[];traits:Trait[];emblems:Emblem[];allow_duplicate_emblems:boolean;set:string;mode:string;source:string;verification_status:string;data_readiness?:Readiness;license_status:string};
export type Candidate={id:string;champions:Unit[];assignments:{instance_index:number;emblem_id:string;champion_id:string;explanation:string}[];unused_emblem_indices:number[];traits:{id:string;name:string;count:number;active:boolean;level:number;utility:number;thresholds:number[]}[];score:{total:number;components:Record<string,{value:number;weight:number;contribution:number}>};solver_status:string;objective_value:number;best_bound:number};
export type Result={status:string;enumeration_status:string;candidates:Candidate[];elapsed_seconds:number;assumptions:string[]};
export const PUBLIC_DEMO=process.env.NEXT_PUBLIC_PUBLIC_DEMO==='true';
export const API=process.env.NEXT_PUBLIC_API_URL==='same-origin'?'':(process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000');
export async function api<T>(path:string,body?:unknown):Promise<T>{
 let r:Response;
 try{r=await fetch(API+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined})}catch{throw Error(PUBLIC_DEMO?'求解服务暂时无法连接，请稍后重试。':'无法连接后端 API，请确认后端已启动（'+API+'）。')}
 let data;try{data=await r.json()}catch{throw Error('求解服务尚未就绪或返回异常，请稍后重试。')} if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;
}
export function errorText(e:unknown){return e instanceof Error?e.message:'请求失败';}
export const zh={MAX_ACTIVE_TRAITS:'最多激活羁绊',MAX_BREAKPOINT:'最高羁绊档位价值',BALANCED:'均衡阵容估分',LOW_COST:'低成本阵容',LATE_GAME:'后期理论上限'};
export const componentNames:Record<string,string>={active_traits:'激活羁绊',breakpoint_utility:'档位效用',unit_cost:'棋子总费用',equipped_emblems:'已装备纹章'};
