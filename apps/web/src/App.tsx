import { NavLink, Route, Routes, Link } from 'react-router-dom';
import { Empty, Tag } from 'antd';
import { BarChartOutlined, DatabaseOutlined, DeploymentUnitOutlined, HistoryOutlined, SettingOutlined, TeamOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import Today from './Today';
import Auth from './Auth';
import Mappings from './Mappings';
import MatchDetail from './MatchDetail';
import { Quality, Providers, Jobs, Users, Logs } from './AdminPages';
export default function App(){
 const system=useQuery({queryKey:['system'],queryFn:()=>api<{demo_mode:boolean}>('/system/info')});
 const nav=[['/','今日竞彩',<UnorderedListOutlined/>],['/quality','数据质量',<BarChartOutlined/>],['/mappings','比赛映射',<DeploymentUnitOutlined/>],['/providers','数据源管理',<DatabaseOutlined/>],['/jobs','同步任务',<HistoryOutlined/>],['/users','用户管理',<TeamOutlined/>],['/logs','审计日志',<SettingOutlined/>]] as const;
 return <div className="app-shell"><aside className="sidebar"><Link to="/" className="brand"><div className="brand-icon">JC<span/></div><div><b>竞彩智研</b><small>FOOTBALL INTELLIGENCE</small></div></Link><div className="workspace-label">研究工作台 <span>V1</span></div><nav>{nav.map(([path,label,icon])=><NavLink end={path==='/'} key={path} to={path}>{icon}<span>{label}</span></NavLink>)}</nav><div className="sidebar-bottom"><div className="source-icon"><DatabaseOutlined/></div><strong>可追溯的数据底座</strong><p>每一场比赛，每一次变化。<br/>始于来源，忠于记录。</p><span className="version">PHASE 0 – 3 · v0.1.0</span></div></aside><div className="main-shell"><header className="topbar"><span>数据研究 <span className="breadcrumb-sep">/</span> 工作台</span><div className="topbar-right"><Tag color={system.data?.demo_mode?'gold':'green'}>{!system.data?'数据模式读取中':system.data.demo_mode?'MOCK · 演示数据':'LIVE · 真实数据模式'}</Tag><span className="tz-label">北京时间 UTC+8</span><Link to="/login" className="avatar" aria-label="登录">JC</Link></div></header><main><Routes><Route path="/" element={<Today/>}/><Route path="/login" element={<Auth/>}/><Route path="/mappings" element={<Mappings/>}/><Route path="/matches/:id" element={<MatchDetail/>}/><Route path="/quality" element={<Quality/>}/><Route path="/providers" element={<Providers/>}/><Route path="/jobs" element={<Jobs/>}/><Route path="/users" element={<Users/>}/><Route path="/logs" element={<Logs/>}/><Route path="*" element={<Empty description="页面不存在"/>}/></Routes><footer><span>竞彩智研 / JC Football Intelligence</span><span>数据有来源 · 历史可追溯</span></footer></main></div></div>;
}



