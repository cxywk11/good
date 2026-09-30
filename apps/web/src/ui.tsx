import { Alert } from 'antd';
export function PageTitle({eyebrow,title,description,action}:{eyebrow:string;title:string;description:string;action?:React.ReactNode}){
 return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}
export function QueryError({error}:{error:Error|null}){return error?<Alert type="error" showIcon message="数据加载失败" description={error.message}/>:null}
export function Metric({label,value,detail}:{label:string;value:React.ReactNode;detail:string}){return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>}

