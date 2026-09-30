import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Empty, Input, Select, Table, Tooltip } from 'antd';
import { ArrowRightOutlined, CheckCircleOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { api, labels, Match, MatchPage, ProviderState, time } from './api';
import { Metric, PageTitle, QueryError } from './ui';
export default function Today(){
 const [page,setPage]=useState(1),[search,setSearch]=useState(''),[league,setLeague]=useState<string>();
 const query=useQuery({queryKey:['matches',page],queryFn:()=>api<MatchPage>(`/matches/today?page=${page}&page_size=30`),refetchInterval:60000});
 const providers=useQuery({queryKey:['providers'],queryFn:()=>api<ProviderState[]>('/providers/status'),refetchInterval:30000});
 const matches=query.data?.items??[];
 const rows=matches.filter(m=>(!league||m.competition_name===league)&&`${m.home_team_name}${m.away_team_name}${m.match_num}`.includes(search));
 const healthy=providers.data?.filter(p=>p.status==='HEALTHY').length??0;
 const latest=providers.data?.filter(p=>p.last_success_at).map(p=>p.last_success_at!).sort().at(-1)??null;
 return <><PageTitle eyebrow="MATCH CENTER" title="今日竞彩" description="从中国体育彩票开售比赛出发，追踪每一份数据。" action={<Button icon={<ReloadOutlined/>} loading={query.isFetching} onClick={()=>{void query.refetch();void providers.refetch()}}>刷新数据</Button>}/>
  {query.data?.demo_mode&&<Alert className="mode-alert" type="warning" showIcon message="演示环境 · 全部比赛与赔率均为 Mock 样例，不是实际开售数据"/>}
  <QueryError error={query.error}/>
  <section className="metrics"><Metric label="当日比赛" value={query.data?.total??'—'} detail="以体彩销售日为准"/><Metric label="本页已映射" value={matches.filter(m=>m.provider_coverage.length).length} detail="已确认的跨源比赛关联"/><Metric label="健康数据源" value={`${healthy} / ${providers.data?.length??0}`} detail="最近一次采集状态"/><Metric label="最近同步 · 北京时间" value={<span className="time-value">{time(latest)}</span>} detail={latest?time(latest,true):'等待数据源首次同步'}/></section>
  <div className="panel"><div className="panel-toolbar"><div className="panel-title"><span className="green-dot"/> 比赛列表 <span className="count-pill">{query.data?.total??0}</span></div><div className="filters"><Input aria-label="搜索本页比赛" prefix={<SearchOutlined/>} placeholder="搜索本页球队 / 编号" value={search} onChange={e=>setSearch(e.target.value)}/><Select aria-label="联赛筛选" placeholder="全部联赛" allowClear value={league} onChange={setLeague} options={[...new Set(matches.map(m=>m.competition_name))].map(x=>({label:x,value:x}))}/></div></div>
  <div className="table-caption">{query.data?.sell_date??'今日'} <span>销售日 · 开球时间均为北京时间（UTC+8）</span></div>
  <Table<Match> rowKey="id" loading={query.isLoading} dataSource={rows} scroll={{x:1000}} pagination={{current:page,pageSize:30,total:query.data?.total??0,onChange:setPage,showSizeChanger:false}} locale={{emptyText:<Empty description="尚无当天开售数据，请查看数据质量中心了解同步状态。"/>}} columns={[
   {title:'比赛',dataIndex:'match_num',width:110,render:(v,m)=><div><strong>{v}</strong><small className="table-sub">{m.sell_status==='ON_SALE'?'已开售':m.sell_status==='SUSPENDED'?'暂停销售':'已停售'}</small></div>},
   {title:'联赛',dataIndex:'competition_name',width:95,render:v=><span className="league-label">{v}</span>},
   {title:'对阵',width:280,render:(_,m)=><Link to={`/matches/${m.id}`} className="match-teams"><span>{m.home_team_name}</span><small>VS</small><span>{m.away_team_name}</span></Link>},
   {title:'开球时间',dataIndex:'kickoff_at',width:130,render:v=><span className="mono">{time(v,true).slice(0,-3)}</span>},
   {title:<div className="odds-column-label">竞彩胜平负 <small>主胜 / 平 / 客胜</small></div>,width:210,render:(_,m)=><div className="odds-triplet">{['HOME','DRAW','AWAY'].map(k=><span key={k}>{m.sporttery_sp[k]?Number(m.sporttery_sp[k]).toFixed(2):'—'}</span>)}</div>},
   {title:'跨源映射',width:130,render:(_,m)=><div className="coverage">{['pinnacle','bet365','macau','williamhill'].map(p=><Tooltip title={`${labels[p]} · ${m.provider_coverage.includes(p)?'已确认映射':'未映射'}`} key={p}><span className={m.provider_coverage.includes(p)?'coverage-dot present':'coverage-dot'}/></Tooltip>)}</div>},
   {title:'',width:45,render:(_,m)=><Link aria-label={`查看${m.match_num}`} to={`/matches/${m.id}`}><ArrowRightOutlined/></Link>}
  ]}/></div>
  <div className="info-note"><CheckCircleOutlined/> 数据仅用于研究与追溯。缺失值显示为「—」，每条赔率保留来源与采集时间。</div>
 </>;
}

