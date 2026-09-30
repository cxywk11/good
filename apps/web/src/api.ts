export type Envelope<T>={success:boolean;data:T;request_id:string;error?:{message:string}};
let accessToken:string|null=null;
let refreshToken:string|null=null;
let pendingRefresh:Promise<void>|null=null;
export type SessionData={access_token:string;refresh_token:string;user:{id:string;email:string;role:string}};
export function setSession(value:SessionData){accessToken=value.access_token;refreshToken=value.refresh_token}
export function clearSession(){accessToken=null;refreshToken=null}
export function setAccessToken(value:string|null){accessToken=value}
export async function api<T>(path:string,init:RequestInit={},retry=true):Promise<T>{
  const response=await fetch('/api/v1'+path,{...init,headers:{'Content-Type':'application/json',...(accessToken?{Authorization:`Bearer ${accessToken}`} : {}),...init.headers}});
  const body:Envelope<T>=await response.json();
  if(response.status===401&&refreshToken&&retry&&!path.startsWith('/auth/')){
    pendingRefresh??=fetch('/api/v1/auth/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token:refreshToken})}).then(async r=>{const b:Envelope<SessionData>=await r.json();if(!r.ok){clearSession();throw new Error('登录已过期，请重新登录')}setSession(b.data)}).finally(()=>{pendingRefresh=null});
    await pendingRefresh;return api<T>(path,init,false);
  }
  if(!response.ok||!body.success)throw new Error(typeof body.error?.message==='string'?body.error.message:`请求失败 (${response.status})`);
  return body.data;
}
export type Match={id:string;sporttery_match_id:string;match_num:string;sell_date:string;competition_name:string;home_team_name:string;away_team_name:string;kickoff_at:string;kickoff_beijing:string;sell_status:string;single_allowed:boolean|null;mock:boolean;collected_at:string;markets:Record<string,{available:boolean;single_allowed:boolean|null}>;sporttery_sp:Record<string,string>;provider_coverage:string[];home_team_id:string|null;away_team_id:string|null;competition_id:string|null};
export type MatchPage={items:Match[];total:number;page:number;page_size:number;sell_date:string;demo_mode:boolean};
export type ProviderState={provider:string;enabled:boolean;status:string;last_success_at:string|null;last_failure_at:string|null;latency:number|null;consecutive_failures:number;rate_limit_status:string;next_allowed_at:string|null};
export const time=(value:string|null,full=false)=>value?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',...(full?{month:'2-digit',day:'2-digit'}:{}),hour:'2-digit',minute:'2-digit',second:full?'2-digit':undefined,hour12:false}).format(new Date(value)):'—';
export const labels:Record<string,string>={sporttery:'中国竞彩',pinnacle:'Pinnacle',bet365:'Bet365',macau:'澳门',williamhill:'William Hill',the_odds_api:'The Odds API'};
export type Odds={id:string;match_id:string;provider:string;bookmaker:string;market_type:string;selection:string;line:string|null;raw_odds:string;decimal_odds:string;implied_probability:string;collected_at:string;effective_at:string|null;published_at:string|null;raw_payload_id:string;mock:boolean;mapping_id:string|null;mapping_version:number|null;change?:{previous_odds:string|null;current_odds:string;absolute_change:string|null;percentage_change:string|null;direction:string}};
export type KeySnapshot={id:string;snapshot_type:string;target_at:string;odds:Odds;observation_gap_seconds:number};
export const marketLabels:Record<string,string>={'1X2':'胜平负','ASIAN_HANDICAP':'亚洲盘','TOTALS':'大小球','CORRECT_SCORE':'比分','SPORTTERY_HAD':'竞彩胜平负','SPORTTERY_HHAD':'让球胜平负','SPORTTERY_CRS':'竞彩比分','SPORTTERY_TTG':'总进球','SPORTTERY_HAFU':'半全场'};
export const selectionLabels:Record<string,string>={HOME:'主胜',DRAW:'平',AWAY:'客胜',OVER:'大',UNDER:'小',HOME_OTHER:'胜其他',DRAW_OTHER:'平其他',AWAY_OTHER:'负其他'};
export const seriesKey=(o:Odds)=>[o.provider,o.bookmaker,o.market_type,o.selection,o.line??''].join('|');
