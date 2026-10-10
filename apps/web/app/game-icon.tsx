'use client';
import Image from 'next/image';
import {useState} from 'react';
export default function GameIcon({src,name,size=68}:{src?:string;name:string;size?:number}){
 const [failedSrc,setFailedSrc]=useState<string>();
 return src&&failedSrc!==src?<Image src={src} width={size} height={size} unoptimized alt={name} onError={()=>setFailedSrc(src)}/>:<span role="img" aria-label={name} title="官方图标暂时无法加载">{name[0]}</span>;
}
