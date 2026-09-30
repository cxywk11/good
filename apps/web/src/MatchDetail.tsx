import { lazy, Suspense, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Alert, Button, Descriptions, Empty, Select, Space, Spin, Table, Tabs, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { api, KeySnapshot, labels, marketLabels, Match, Odds, selectionLabels, seriesKey, time } from './api';
import { PageTitle, QueryError } from './ui';
const OddsChart=lazy(()=>import('./OddsChart'));
const pools:Record<string,string>={had:'胜平负',hhad:'让球胜平负',crs:'比分',ttg:'总进球',hafu:'半全场'};
export default function MatchDetail(){
 const {id}=useParams();const [market,setMarket]=useState('1X2'),[selection,setSelection]=useState('HOME'),[line,setLine]=useState<string>('');
 const match=useQuery({queryKey:['match',id],queryFn:()=>api<Match>(`/matches/${id}`)});
 const latest=useQuery({queryKey:['odds',id],queryFn:()=>api<{items:Odds[]}>(`/matches/${id}/odds`),refetchInterval:30000});
 const sporttery=useQuery({queryKey:['sporttery-odds',id],queryFn:()=>api<{markets:Record<string,{available:boolean;single_allowed:boolean|null;odds:Odds[]}>}>(`/matches/${id}/sporttery-odds`),refetchInterval:30000});
 const keys=useQuery({queryKey:['key-snapshots',id],queryFn:()=>api<KeySnapshot[]>(`/matches/${id}/odds/key-snapshots`),refetchInterval:30000});
 const history=useInfiniteQuery({queryKey:['history',id],initialPageParam:'',queryFn:({pageParam})=>api<{items:Odds[];next_cursor:string|null}>(`/matches/${id}/odds/history?limit=1000${pageParam?'&cursor='+encodeURIComponent(pageParam):''}`),getNextPageParam:p=>p.next_cursor??undefined,refetchInterval:30000});
 const historyRows=useMemo(()=>history.data?.pages.flatMap(p=>p.items)??[],[history.data]);
 const matchesMarket=(o:Odds)=>o.market_type===market||(market==='1X2'&&o.market_type==='SPORTTERY_HAD')||(market==='CORRECT_SCORE'&&o.market_type==='SPORTTERY_CRS');
 const matching=(latest.data?.items??[]).filter(matchesMarket);
 const selections=[...new Set(matching.map(o=>o.selection))];
 const lines=[...new Set(matching.filter(o=>o.selection===selection).map(o=>o.line??''))];
 const selectedLine=lines.includes(line)?line:lines[0]??'';
 const filtered=historyRows.filter(o=>matchesMarket(o)&&o.selection===selection&&(o.line??'')===selectedLine);
 const compare=matching.filter(o=>o.selection===selection&&(o.line??'')===selectedLine);
 function priceAt(o:Odds,type:string){const found=keys.data?.find(k=>k.snapshot_type===type&&seriesKey(k.odds)===seriesKey(o));return found?Number(found.odds.decimal_odds).toFixed(2):'—'}
 if(match.isLoading)return <Spin/>;
 if(match.error)return <QueryError error={match.error}/>;
 const m=match.data;if(!m)return null;
 return <><Link to="/" className="muted"><ArrowLeftOutlined/> 返回今日竞彩</Link><div className="section-gap"><PageTitle eyebrow={`${m.match_num} · ${m.competition_name}`} title={`${m.home_team_name}  VS  ${m.away_team_name}`} description={`${time(m.kickoff_at,true)} 北京时间 · ${m.sell_status==='ON_SALE'?'已开售':m.sell_status} · 体彩编号 ${m.sporttery_match_id}`}/></div>{m.mock&&<Alert type="warning" showIcon message="Mock 演示比赛 · 本页赔率为合成样例"/>}<div className="panel content-pad"><Descriptions size="small" column={{xs:1,md:3}} items={[{key:'sell',label:'销售日',children:m.sell_date},{key:'last',label:'最近采集',children:time(m.collected_at,true)},{key:'source',label:'比赛池来源',children:'中国体育彩票'}]}/></div>
 <div className="panel section-gap"><div className="panel-toolbar"><strong>中国竞彩 SP</strong><Tag color="green">体彩五类玩法</Tag></div><QueryError error={sporttery.error}/><Tabs className="odds-tabs" items={Object.entries(pools).map(([pool,label])=>{const data=sporttery.data?.markets[pool];return {key:pool,label:<>{label} {data?.available?<span className="green-dot inline-dot"/>:null}</>,children:<div className="content-pad">{!data?.available?<Empty description="该玩法当前未开售，玩法概念与已有历史仍保留"/>:<><div className="muted">{data.single_allowed?'支持单关':'未标记单关'} · 十进制赔率</div><div className="sp-grid">{data.odds.map(o=><div className="sp-cell" key={o.id}><small>{selectionLabels[o.selection]??o.selection}{o.line!==null?` (${o.line})`:''}</small><strong>{Number(o.decimal_odds).toFixed(2)}</strong></div>)}</div>{!data.odds.length&&<Empty description="已开售，尚无可用赔率"/>}</>}</div>}})}/></div>
 <div className="panel section-gap"><div className="panel-toolbar"><div><strong>赔率变化</strong><p className="muted small-copy">按采集时间追踪 · 点击图例隐藏或显示公司</p></div><Space wrap><Select value={market} onChange={v=>{setMarket(v);setSelection(v==='TOTALS'?'OVER':v==='CORRECT_SCORE'?'1:0':'HOME');setLine('')}} options={['1X2','ASIAN_HANDICAP','TOTALS','CORRECT_SCORE'].map(v=>({value:v,label:marketLabels[v]}))}/><Select aria-label="赔率选项" value={selection} onChange={setSelection} style={{minWidth:85}} options={selections.map(v=>({value:v,label:selectionLabels[v]??v}))}/>{lines.some(Boolean)&&<Select aria-label="盘口" value={selectedLine} onChange={setLine} options={lines.map(v=>({value:v,label:v||'无盘口'}))}/>}</Space></div><QueryError error={history.error}/>{filtered.length?<Suspense fallback={<Spin/>}><OddsChart rows={filtered}/></Suspense>:<Empty className="content-pad" description="当前市场与选项暂无可用历史"/>}<div className="content-pad muted small-copy">已载入 {historyRows.length} 条历史记录。{history.hasNextPage&&<Button size="small" loading={history.isFetchingNextPage} onClick={()=>void history.fetchNextPage()}>加载更多历史</Button>}</div></div>
 <div className="panel section-gap"><div className="panel-toolbar"><strong>公司报价对照</strong><span className="muted small-copy">{marketLabels[market]} · {selectionLabels[selection]??selection} {selectedLine}</span></div><QueryError error={latest.error}/><Table<Odds> rowKey="id" dataSource={compare} pagination={false} scroll={{x:900}} columns={[
 {title:'数据源 / 公司',render:(_,o)=><><strong>{o.bookmaker}</strong><small className="table-sub">{labels[o.provider]??o.provider}{o.mock?' · Mock':''}</small></>},
 {title:'供应商初盘',render:(_,o)=>priceAt(o,'PROVIDER_OPEN')},
 {title:'首次观察',render:(_,o)=>priceAt(o,'FIRST_OBSERVED')},
 {title:'当前赔率',dataIndex:'decimal_odds',render:v=><strong>{Number(v).toFixed(2)}</strong>},
 {title:'前值 → 变化',render:(_,o)=>o.change?.previous_odds?<span>{Number(o.change.previous_odds).toFixed(2)} → {Number(o.change.absolute_change).toFixed(2)} ({Number(o.change.percentage_change).toFixed(2)}%)</span>:'—'},
 {title:'开球前最后观察',render:(_,o)=>priceAt(o,'LAST_PREMATCH')},
 {title:'采集时间',dataIndex:'collected_at',render:v=>time(v,true)}]}/></div>
 <div className="info-note">首次观察不等同于供应商初盘。缺失初盘或收盘数据不会由系统推算。</div></>;
}
