import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Odds, labels, time, seriesKey } from './api';
echarts.use([LineChart,GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,CanvasRenderer]);
export function chartSeries(rows:Odds[]){
 const grouped=new Map<string,Odds[]>();
 for(const row of rows){const key=seriesKey(row);grouped.set(key,[...(grouped.get(key)??[]),row])}
 return [...grouped.entries()].map(([key,values])=>({id:key,name:`${labels[values[0].provider]??values[0].provider} / ${values[0].bookmaker}`,type:'line' as const,step:'end' as const,showSymbol:values.length<10,symbolSize:7,connectNulls:false,data:values.sort((a,b)=>Date.parse(a.collected_at)-Date.parse(b.collected_at)).map(o=>[Date.parse(o.collected_at),Number(o.decimal_odds)])}));
}
export default function OddsChart({rows}:{rows:Odds[]}){
 const ref=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(!ref.current)return;const chart=echarts.init(ref.current);chart.setOption({color:['#27674b','#728cc0','#dba55c','#9b83b2','#699c9b'],tooltip:{trigger:'axis'},legend:{type:'scroll',bottom:8,textStyle:{fontSize:11,color:'#6b7e70'}},grid:{left:54,right:30,top:30,bottom:88},xAxis:{type:'time',axisLabel:{formatter:(n:number)=>time(new Date(n).toISOString()),color:'#92a095',fontSize:10},axisLine:{lineStyle:{color:'#e4eae4'}},splitLine:{show:false}},yAxis:{type:'value',scale:true,name:'十进制赔率',nameTextStyle:{color:'#829487',fontSize:10},axisLabel:{color:'#92a095',fontSize:10},splitLine:{lineStyle:{color:'#eef2ec',type:'dashed'}}},dataZoom:[{type:'inside'},{type:'slider',height:15,bottom:42,borderColor:'transparent',backgroundColor:'#f4f7f2',fillerColor:'#dce9dc'}],series:chartSeries(rows)});const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);return()=>{observer.disconnect();chart.dispose()}},[rows]);
 return <div ref={ref} className="chart" aria-label="赔率历史折线图，横轴为北京时间采集时间，点击图例显示或隐藏公司"/>;
}
