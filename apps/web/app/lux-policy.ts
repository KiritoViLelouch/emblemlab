import type {Catalog,Unit} from './lib';

// This group is an explicit reviewed TFT Set 18 identity; never match JCC by name.
export function luxForms(catalog?:Catalog):Unit[]{
 return catalog?.game==='TFT'&&catalog.id==='tft_set18_18_4_standard'
  ?catalog.champions.filter(c=>c.exclusive_group==='DA_18_Lux'&&c.available!==false):[];
}
export function luxConstraints(catalog:Catalog|undefined,choice:string,locked:string[],banned:string[],maxCost:number){
 const forms=luxForms(catalog),ids=forms.map(c=>c.id);
 if(!ids.length)return {locked_units:locked,banned_units:banned,max_unit_cost:maxCost};
 if(choice!=='without'&&!ids.includes(choice))throw Error('请选择已核查的拉克丝羁绊形态。');
 if(choice!=='without'&&maxCost<5)throw Error('指定拉克丝是五费卡，请将最高单卡费用设为 5。');
 return {locked_units:[...locked.filter(id=>!ids.includes(id)),...(choice==='without'?[]:[choice])],
  banned_units:[...new Set([...banned.filter(id=>!ids.includes(id)),...ids.filter(id=>id!==choice)])],max_unit_cost:maxCost};
}
